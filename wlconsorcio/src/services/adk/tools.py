from typing import Optional

from google.adk.tools import ToolContext


def solicitar_atendimento_humano(
    tool_context: ToolContext,
    motivo: str,
    fila_sugerida: Optional[str] = None,
) -> dict:
    """Marca a conversa para encaminhamento a um atendente humano — siga as
    regras de quando e para onde encaminhar descritas na sua personalidade,
    se houver.

    Se você já souber exatamente o nome/departamento da fila certa pra esse
    caso (ex: seu fluxo define um setor e uma cidade específicos), preencha
    fila_sugerida com esse nome o mais parecido possível de como a fila
    realmente se chama — isso torna o direcionamento muito mais preciso do
    que depender só do motivo em texto livre."""
    tool_context.state["handoff_requested"] = True
    tool_context.state["handoff_reason"] = motivo
    if fila_sugerida:
        tool_context.state["handoff_suggested_queue"] = fila_sugerida
    return {"ok": True, "mensagem": "Encaminhamento para atendimento humano registrado."}


def encerrar_conversa(tool_context: ToolContext) -> dict:
    """Marca a conversa como encerrada. Use quando o assunto foi resolvido e o
    cliente se despediu ou confirmou que não precisa de mais nada."""
    tool_context.state["closing_requested"] = True
    return {"ok": True}


def atualizar_nome_cliente(tool_context: ToolContext, nome: str) -> dict:
    """Registra o nome do cliente assim que ele informar ou confirmar — só
    pergunte o nome se ele ainda não estiver nos dados já conhecidos deste
    contato (ver o início da sua instrução)."""
    tool_context.state["nome"] = nome
    return {"nome": nome}


def atualizar_restricao_no_nome_cliente(tool_context: ToolContext, restricao_no_nome: str) -> dict:
    """Registra se o contato tem alguma restrição no nome (CPF negativado em
    SPC/Serasa, por exemplo) assim que ele informar ou confirmar — só
    pergunte se ainda não estiver nos dados já conhecidos deste contato."""
    tool_context.state["restricao_no_nome"] = restricao_no_nome
    return {"restricao_no_nome": restricao_no_nome}


def atualizar_imovel_de_garantia_cliente(tool_context: ToolContext, imovel_de_garantia: str) -> dict:
    """Registra os dados do imóvel que o contato pretende oferecer como
    garantia (tipo, cidade, valor aproximado etc.) assim que ele informar ou
    confirmar — só pergunte se ainda não estiver nos dados já conhecidos
    deste contato."""
    tool_context.state["imovel_de_garantia"] = imovel_de_garantia
    return {"imovel_de_garantia": imovel_de_garantia}


def atualizar_tem_um_avalista_cliente(tool_context: ToolContext, tem_um_avalista: str) -> dict:
    """Registra se o contato tem um avalista disponível para essa operação
    assim que ele informar ou confirmar — só pergunte se ainda não estiver
    nos dados já conhecidos deste contato."""
    tool_context.state["tem_um_avalista"] = tem_um_avalista
    return {"tem_um_avalista": tem_um_avalista}


def atualizar_condicoes_de_pagar_parcelas_remanescentes_cliente(
    tool_context: ToolContext, condicoes_de_pagar_parcelas_remanescentes: str
) -> dict:
    """Registra as condições do contato para pagar as parcelas remanescentes
    do consórcio (à vista, parcelado, financiado etc.) assim que ele informar
    ou confirmar — só pergunte se ainda não estiver nos dados já conhecidos
    deste contato."""
    tool_context.state["condicoes_de_pagar_parcelas_remanescentes"] = condicoes_de_pagar_parcelas_remanescentes
    return {"condicoes_de_pagar_parcelas_remanescentes": condicoes_de_pagar_parcelas_remanescentes}


def parar_envio_campanhas(tool_context: ToolContext) -> dict:
    """Chame assim que o contato pedir explicitamente para não receber mais
    campanhas/mensagens em massa (ex: "não quero mais receber", "pare de me
    mandar mensagem", "me remova da lista") — marca o contato para ser
    excluído dos próximos disparos de campanha."""
    tool_context.state["block_campaigns_requested"] = True
    return {"ok": True, "mensagem": "Contato marcado para não receber mais campanhas."}


def registrar_disponibilidade_contato(tool_context: ToolContext, dia: str, horario: str) -> dict:
    """Registra o melhor dia e horário que o cliente informou para vocês
    conversarem — chame assim que ele responder isso, no roteiro de primeiro
    contato (depois de dizer que não pode falar agora)."""
    tool_context.state["dia_preferido"] = dia
    tool_context.state["horario_preferido"] = horario
    return {"dia": dia, "horario": horario}
