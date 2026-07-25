from typing import Literal, Optional

from google.adk.tools import ToolContext

from src.services.adk.property_engine import buscar_e_selecionar
from src.services.adk.scheduling import tentar_agendar


def _merge_dict_state(tool_context: ToolContext, chave: str, novos_valores: dict) -> dict:
    atual = dict(tool_context.state.get(chave, {}))
    atual.update({k: v for k, v in novos_valores.items() if v is not None})
    tool_context.state[chave] = atual
    return atual


def atualizar_perfil_imovel(
    tool_context: ToolContext,
    finalidade: Optional[str] = None,
    tipo: Optional[str] = None,
    cidade: Optional[str] = None,
    bairros: Optional[list[str]] = None,
    quartos_minimos: Optional[int] = None,
    vagas_minimas: Optional[int] = None,
    caracteristicas: Optional[list[str]] = None,
    motivo_compra: Optional[str] = None,
) -> dict:
    """Registra/atualiza o que o cliente procura assim que ele informar (não precisa
    esperar ter tudo preenchido — chame a cada novo detalhe aprendido)."""
    return _merge_dict_state(tool_context, "perfil_imovel", {
        "finalidade": finalidade,
        "tipo": tipo,
        "cidade": cidade,
        "bairros": bairros,
        "quartos_minimos": quartos_minimos,
        "vagas_minimas": vagas_minimas,
        "caracteristicas": caracteristicas,
        "motivo_compra": motivo_compra,
    })


def atualizar_perfil_financeiro(
    tool_context: ToolContext,
    orcamento_minimo: Optional[float] = None,
    orcamento_maximo: Optional[float] = None,
    forma_pagamento: Optional[Literal["avista", "financiamento", "consorcio", "misto", "nao_definido"]] = None,
    entrada_disponivel: Optional[float] = None,
    parcela_maxima_desejada: Optional[float] = None,
) -> dict:
    """Registra/atualiza a qualificação financeira do cliente assim que ele informar.
    NUNCA representa aprovação de crédito — é só uma estimativa de compatibilidade."""
    return _merge_dict_state(tool_context, "perfil_financeiro", {
        "orcamento_minimo": orcamento_minimo,
        "orcamento_maximo": orcamento_maximo,
        "forma_pagamento": forma_pagamento,
        "entrada_disponivel": entrada_disponivel,
        "parcela_maxima_desejada": parcela_maxima_desejada,
    })


def atualizar_nome_cliente(tool_context: ToolContext, nome: str) -> dict:
    """Registra o nome do cliente assim que ele informar (só pergunte se ainda não souber)."""
    tool_context.state["nome"] = nome
    return {"nome": nome}


def buscar_imoveis(tool_context: ToolContext) -> dict:
    """Busca até 3 imóveis compatíveis com o perfil já registrado (chame
    atualizar_perfil_imovel/atualizar_perfil_financeiro antes, com o que o cliente já
    informou). NUNCA invente imóveis, preços ou disponibilidade — use exclusivamente o
    retorno desta ferramenta ao apresentar opções. Cada imóvel retornado já vem com
    'compatibilidade' (0-100) e 'qualificacao' — nunca exponha esses nomes técnicos ao
    cliente, use-os só para explicar o motivo da recomendação."""
    perfil_imovel = tool_context.state.get("perfil_imovel", {})
    perfil_financeiro = tool_context.state.get("perfil_financeiro", {})

    selecionados = buscar_e_selecionar(perfil_imovel, perfil_financeiro)

    tool_context.state["recomendacoes"] = [
        {"imovel_id": i["id"], "compatibilidade": i["compatibilidade"]} for i in selecionados
    ]
    tool_context.state["imoveis_apresentados"] = list(set(
        tool_context.state.get("imoveis_apresentados", []) + [i["id"] for i in selecionados]
    ))

    if not selecionados:
        return {"imoveis": [], "aviso": "Nenhum imóvel disponível compatível foi encontrado com os critérios informados até agora."}

    return {
        "imoveis": [
            {
                "id": i["id"],
                "titulo": i["titulo"],
                "tipo": i["tipo"],
                "valor": i["valor"],
                "condominio": i["condominio"],
                "iptu_anual": i["iptu_anual"],
                "area_m2": i["area_m2"],
                "quartos": i["quartos"],
                "suites": i["suites"],
                "banheiros": i["banheiros"],
                "vagas_garagem": i["vagas_garagem"],
                "bairro": i["bairro"],
                "cidade": i["cidade"],
                "aceita_financiamento": i["aceita_financiamento"],
                "valor_entrada_sugerida": i["valor_entrada_sugerida"],
                "caracteristicas": i["caracteristicas"],
                "descricao": i["descricao"],
                "imagem_url": i["imagem_url"],
                "compatibilidade": i["compatibilidade"],
                "qualificacao": i["qualificacao"],
            }
            for i in selecionados
        ]
    }


def registrar_interesse(tool_context: ToolContext, imovel_ids: list[str]) -> dict:
    """Chame assim que o cliente demonstrar interesse em um ou mais imóveis apresentados."""
    existentes = set(tool_context.state.get("imoveis_interesse", []))
    existentes.update(imovel_ids)
    tool_context.state["imoveis_interesse"] = sorted(existentes)
    return {"imoveis_interesse": sorted(existentes)}


async def agendar_visita(
    tool_context: ToolContext,
    data: str,
    horario: str,
    tipo_encontro: Literal["visita_imovel", "reuniao_escritorio", "especialista"],
    imovel_id: Optional[str] = None,
) -> dict:
    """Verifica horário comercial e disponibilidade real na agenda e, se estiver tudo ok,
    confirma o agendamento. NUNCA confirme uma visita/reunião ao cliente sem chamar essa
    ferramenta primeiro. data no formato AAAA-MM-DD, horario no formato HH:MM (24h)."""
    contact_id = tool_context.session.user_id
    resultado = await tentar_agendar(
        contact_id=contact_id,
        data=data,
        horario=horario,
        tipo_encontro=tipo_encontro,
        imovel_id=imovel_id,
    )

    if resultado.get("confirmado"):
        tool_context.state["agendamento"] = {
            "status": "confirmado",
            "tipo": tipo_encontro,
            "imovel_id": imovel_id,
            "data": data,
            "horario": horario,
        }

    return resultado


def solicitar_atendimento_humano(tool_context: ToolContext, motivo: str) -> dict:
    """Marca a conversa para encaminhamento a um atendente humano. Use quando o
    cliente pedir explicitamente para falar com uma pessoa, ou quando a dúvida
    estiver fora do que você consegue resolver com segurança (ex: negociação
    de condições fora do padrão, reclamação, problema jurídico do imóvel)."""
    tool_context.state["handoff_requested"] = True
    tool_context.state["handoff_reason"] = motivo
    return {"ok": True, "mensagem": "Encaminhamento para atendimento humano registrado."}


def encerrar_conversa(tool_context: ToolContext) -> dict:
    """Marca a conversa como encerrada. Use quando o assunto foi resolvido e o
    cliente se despediu ou confirmou que não precisa de mais nada."""
    tool_context.state["closing_requested"] = True
    return {"ok": True}
