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


def atualizar_cidade_cliente(tool_context: ToolContext, cidade: str) -> dict:
    """Registra a cidade do cliente assim que ele informar ou confirmar — só
    pergunte a cidade se ela ainda não estiver nos dados já conhecidos deste
    contato."""
    tool_context.state["cidade"] = cidade
    return {"cidade": cidade}
