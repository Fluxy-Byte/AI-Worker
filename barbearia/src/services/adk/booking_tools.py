"""Tools de agendamento da barbearia.

Nesta etapa o objetivo é só a CONVERSA: coletar serviço, horário e
profissional e devolver o resumo do agendamento. A gravação numa agenda real
ainda não existe — o ponto exato onde ela entra está marcado em
catalogo.reservar() e em confirmar_agendamento() abaixo.
"""

from datetime import date, datetime, time, timedelta
from typing import Optional

from google.adk.tools import ToolContext

from src.services.adk import catalogo

# Faixas usadas pra agrupar os horários livres do dia. Devolver a lista
# inteira crua faria o agente despejar 20 opções no WhatsApp; devolver só as
# N primeiras seria pior ainda — ele passa a tratar o corte como "só tem
# isso" e nega horário que existe. Agrupado, ele vê o dia todo e oferece por
# período ("tenho de tarde a partir das 14h").
PERIODOS = (("manha", time(0, 0), time(11, 59)), ("tarde", time(12, 0), time(17, 59)), ("noite", time(18, 0), time(23, 59)))


def _parse_data(data: str) -> tuple[Optional[date], Optional[str]]:
    """Aceita 'AAAA-MM-DD' (formato que a instrução pede ao agente) e, por
    tolerância, 'DD/MM' e 'DD/MM/AAAA'."""
    texto = (data or "").strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m"):
        try:
            parsed = datetime.strptime(texto, formato).date()
        except ValueError:
            continue
        if formato == "%d/%m":
            parsed = parsed.replace(year=catalogo.hoje().year)
        return parsed, None
    return None, "Data em formato inválido — use AAAA-MM-DD."


def _parse_horario(horario: str) -> tuple[Optional[time], Optional[str]]:
    texto = (horario or "").strip().replace("h", ":").rstrip(":")
    for formato in ("%H:%M", "%H"):
        try:
            return datetime.strptime(texto, formato).time(), None
        except ValueError:
            continue
    return None, "Horário em formato inválido — use HH:MM."


def _validar_dia(data_obj: date) -> Optional[str]:
    hoje = catalogo.hoje()
    if data_obj < hoje:
        return f"Essa data já passou (hoje é {hoje.isoformat()})."
    if data_obj > hoje + timedelta(days=catalogo.JANELA_AGENDAMENTO_DIAS):
        return f"A agenda só está aberta até {catalogo.JANELA_AGENDAMENTO_DIAS} dias à frente."
    if not catalogo.expediente_do_dia(data_obj):
        return f"A barbearia não abre {catalogo.DIAS_SEMANA[data_obj.weekday()]}."
    return None


def _dias_abertos_proximos(quantidade: int = 5) -> list[dict]:
    """Próximos dias em que a barbearia abre — pra sugerir alternativa quando o
    cliente pede um dia fechado."""
    dias, cursor = [], catalogo.hoje()
    limite = cursor + timedelta(days=catalogo.JANELA_AGENDAMENTO_DIAS)
    while cursor <= limite and len(dias) < quantidade:
        if catalogo.expediente_do_dia(cursor):
            dias.append({"data": cursor.isoformat(), "dia": catalogo.descrever_dia(cursor)})
        cursor += timedelta(days=1)
    return dias


def _por_periodo(horarios: list[str]) -> dict:
    """{'manha': [...], 'tarde': [...]} — períodos vazios ficam de fora."""
    agrupado: dict[str, list[str]] = {}
    for horario in horarios:
        hora = datetime.strptime(horario, "%H:%M").time()
        for nome, inicio, fim in PERIODOS:
            if inicio <= hora <= fim:
                agrupado.setdefault(nome, []).append(horario)
                break
    return agrupado


def _agendamento(tool_context: ToolContext) -> dict:
    return dict(tool_context.state.get("agendamento") or {})


def _salvar(tool_context: ToolContext, agendamento: dict) -> dict:
    tool_context.state["agendamento"] = agendamento
    return agendamento


def listar_servicos(tool_context: ToolContext) -> dict:
    """Lista os serviços que a barbearia realmente oferece, com duração e
    preço. Chame ANTES de perguntar o que o cliente quer fazer — nunca cite um
    serviço ou preço que não tenha vindo daqui."""
    return {
        "servicos": [
            {"nome": s["nome"], "duracao_min": s["duracao_min"], "preco": s["preco"]}
            for s in catalogo.SERVICOS
        ]
    }


def escolher_servico(tool_context: ToolContext, servico: str) -> dict:
    """Registra o serviço escolhido pelo cliente ('servico' é a resposta livre
    dele, ex: 'corte e barba'). Se não casar com nenhum serviço do catálogo,
    a ferramenta avisa e devolve as opções válidas pra você confirmar com ele."""
    encontrado = catalogo.buscar_servico(servico)
    if not encontrado:
        return {
            "ok": False,
            "aviso": f"Não existe um serviço chamado '{servico}' no catálogo.",
            "servicos": [s["nome"] for s in catalogo.SERVICOS],
        }

    atual = _agendamento(tool_context)
    # Trocar de serviço invalida o horário/profissional já escolhidos (duração
    # e quem atende mudam) — recomeça essa parte em vez de confirmar algo
    # incoerente depois.
    if atual.get("servico_id") and atual["servico_id"] != encontrado["id"]:
        atual.pop("horario", None)
        atual.pop("profissional_id", None)
        atual.pop("profissional", None)

    atual.update({
        "servico_id": encontrado["id"],
        "servico": encontrado["nome"],
        "duracao_min": encontrado["duracao_min"],
        "preco": encontrado["preco"],
    })
    return {"ok": True, **_salvar(tool_context, atual)}


def consultar_horarios(tool_context: ToolContext, data: str) -> dict:
    """Horários realmente livres para o serviço já escolhido, num dia
    ('data' no formato AAAA-MM-DD). O retorno traz TODOS os livres do dia,
    agrupados em 'horarios_por_periodo' (manha/tarde/noite) — use isso pra
    responder no período que o cliente pediu, sem despejar a lista inteira e
    sem dizer que não existe horário num período que está aí. NUNCA ofereça um
    horário que não tenha vindo daqui. Se o dia estiver fechado ou lotado, a
    ferramenta devolve dias alternativos."""
    agendamento = _agendamento(tool_context)
    if not agendamento.get("servico_id"):
        return {"ok": False, "aviso": "Descubra primeiro qual serviço o cliente quer (escolher_servico)."}

    data_obj, erro = _parse_data(data)
    if erro:
        return {"ok": False, "aviso": erro}

    motivo = _validar_dia(data_obj)
    if motivo:
        return {"ok": False, "aviso": motivo, "dias_alternativos": _dias_abertos_proximos()}

    livres = catalogo.horarios_disponiveis(data_obj, agendamento["servico_id"])
    if not livres:
        return {
            "ok": False,
            "dia": catalogo.descrever_dia(data_obj),
            "aviso": "Nenhum horário livre nesse dia para esse serviço.",
            "dias_alternativos": _dias_abertos_proximos(),
        }

    faixa = catalogo.expediente_do_dia(data_obj)
    return {
        "ok": True,
        "data": data_obj.isoformat(),
        "dia": catalogo.descrever_dia(data_obj),
        "expediente": f"{faixa[0].strftime('%H:%M')} às {faixa[1].strftime('%H:%M')}",
        "horarios_por_periodo": _por_periodo(livres),
        "total_livres": len(livres),
    }


def escolher_horario(tool_context: ToolContext, data: str, horario: str) -> dict:
    """Registra dia e hora escolhidos ('data' AAAA-MM-DD, 'horario' HH:MM),
    depois de confirmar que estavam entre os livres de consultar_horarios.
    Retorna também quem atende nesse horário, pra você já perguntar a
    preferência de profissional."""
    agendamento = _agendamento(tool_context)
    if not agendamento.get("servico_id"):
        return {"ok": False, "aviso": "Descubra primeiro qual serviço o cliente quer (escolher_servico)."}

    data_obj, erro = _parse_data(data)
    if erro:
        return {"ok": False, "aviso": erro}
    horario_obj, erro = _parse_horario(horario)
    if erro:
        return {"ok": False, "aviso": erro}

    motivo = _validar_dia(data_obj)
    if motivo:
        return {"ok": False, "aviso": motivo, "dias_alternativos": _dias_abertos_proximos()}

    livres = catalogo.horarios_disponiveis(data_obj, agendamento["servico_id"])
    if horario_obj.strftime("%H:%M") not in livres:
        return {
            "ok": False,
            "aviso": f"{horario_obj.strftime('%H:%M')} não está livre nesse dia para esse serviço.",
            "horarios_por_periodo": _por_periodo(livres),
        }

    disponiveis = catalogo.profissionais_disponiveis(data_obj, horario_obj, agendamento["servico_id"])

    agendamento["data"] = data_obj.isoformat()
    agendamento["dia"] = catalogo.descrever_dia(data_obj)
    agendamento["horario"] = horario_obj.strftime("%H:%M")

    # Profissional já escolhido antes que não atende mais nesse horário: cai
    # fora aqui pra ser perguntado de novo, em vez de furar na confirmação.
    if agendamento.get("profissional_id") and agendamento["profissional_id"] not in {p["id"] for p in disponiveis}:
        agendamento.pop("profissional_id", None)
        agendamento.pop("profissional", None)

    _salvar(tool_context, agendamento)
    return {"ok": True, "profissionais_disponiveis": [p["nome"] for p in disponiveis], **agendamento}


def listar_profissionais(tool_context: ToolContext) -> dict:
    """Profissionais que atendem o serviço escolhido — e, se dia e horário já
    estiverem definidos, só os que estão livres neles. Chame antes de
    perguntar a preferência de profissional; nunca invente um nome."""
    agendamento = _agendamento(tool_context)
    servico_id = agendamento.get("servico_id")

    if servico_id and agendamento.get("data") and agendamento.get("horario"):
        data_obj, _ = _parse_data(agendamento["data"])
        horario_obj, _ = _parse_horario(agendamento["horario"])
        disponiveis = catalogo.profissionais_disponiveis(data_obj, horario_obj, servico_id)
    else:
        disponiveis = catalogo.profissionais_do_servico(servico_id)

    if not disponiveis:
        return {"ok": False, "aviso": "Nenhum profissional disponível para esse serviço nesse horário."}
    return {"ok": True, "profissionais": [p["nome"] for p in disponiveis]}


def escolher_profissional(tool_context: ToolContext, profissional: str) -> dict:
    """Registra o profissional escolhido. Aceite também 'tanto faz' /
    'qualquer um': nesse caso passe profissional='qualquer' e a ferramenta
    escolhe um que esteja disponível."""
    agendamento = _agendamento(tool_context)
    servico_id = agendamento.get("servico_id")
    if not servico_id:
        return {"ok": False, "aviso": "Descubra primeiro qual serviço o cliente quer (escolher_servico)."}

    if agendamento.get("data") and agendamento.get("horario"):
        data_obj, _ = _parse_data(agendamento["data"])
        horario_obj, _ = _parse_horario(agendamento["horario"])
        disponiveis = catalogo.profissionais_disponiveis(data_obj, horario_obj, servico_id)
    else:
        disponiveis = catalogo.profissionais_do_servico(servico_id)

    if not disponiveis:
        return {"ok": False, "aviso": "Nenhum profissional disponível para esse serviço nesse horário."}

    if profissional.strip().lower() in ("qualquer", "qualquer um", "tanto faz", "indiferente", ""):
        escolhido = disponiveis[0]
    else:
        escolhido = catalogo.buscar_profissional(profissional)
        if not escolhido:
            return {
                "ok": False,
                "aviso": f"Não temos um profissional chamado '{profissional}'.",
                "profissionais": [p["nome"] for p in disponiveis],
            }
        if escolhido["id"] not in {p["id"] for p in disponiveis}:
            return {
                "ok": False,
                "aviso": f"{escolhido['nome']} não atende esse serviço nesse horário.",
                "profissionais": [p["nome"] for p in disponiveis],
            }

    agendamento["profissional_id"] = escolhido["id"]
    agendamento["profissional"] = escolhido["nome"]
    return {"ok": True, **_salvar(tool_context, agendamento)}


def confirmar_agendamento(tool_context: ToolContext) -> dict:
    """Fecha o agendamento com o que já foi coletado (serviço + dia/horário +
    profissional) e devolve os dados do resumo. Só chame depois de ter os
    três; a ferramenta avisa se faltar algum. Use EXATAMENTE os campos
    retornados pra escrever o resumo — não recalcule nem reescreva data,
    horário ou preço por conta própria.

    ATENÇÃO: nesta etapa a reserva ainda não é gravada numa agenda real —
    'agenda_real' vem False. Ainda assim, confirme normalmente com o cliente.
    """
    agendamento = _agendamento(tool_context)

    faltando = [campo for campo in ("servico", "data", "horario", "profissional") if not agendamento.get(campo)]
    if faltando:
        return {"ok": False, "faltando": faltando, "aviso": "Ainda falta coletar esses dados antes de confirmar."}

    data_obj, _ = _parse_data(agendamento["data"])
    horario_obj, _ = _parse_horario(agendamento["horario"])

    # Bloqueia o horário (hoje só em memória). Ponto de entrada da agenda real.
    catalogo.reservar(agendamento["profissional_id"], data_obj, horario_obj, agendamento["servico_id"])

    confirmado = {
        "servico": agendamento["servico"],
        "profissional": agendamento["profissional"],
        "data": agendamento["data"],
        "dia": catalogo.descrever_dia(data_obj),
        "horario": agendamento["horario"],
        "duracao_min": agendamento["duracao_min"],
        "preco": agendamento["preco"],
    }

    tool_context.state["agendamento_confirmado"] = confirmado
    tool_context.state["agendamentos"] = [*tool_context.state.get("agendamentos", []), confirmado]
    _salvar(tool_context, agendamento)

    return {"ok": True, "agenda_real": False, **confirmado}


TOOLS = [
    listar_servicos,
    escolher_servico,
    consultar_horarios,
    escolher_horario,
    listar_profissionais,
    escolher_profissional,
    confirmar_agendamento,
]
