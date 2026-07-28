from google.adk.tools import ToolContext


def solicitar_atendimento_humano(tool_context: ToolContext, motivo: str) -> dict:
    """Marca a conversa para encaminhamento a um atendente humano. Use quando o
    cliente pedir explicitamente para falar com uma pessoa, ou quando a dúvida
    estiver fora do que você consegue resolver com segurança."""
    tool_context.state["handoff_requested"] = True
    tool_context.state["handoff_reason"] = motivo
    return {"ok": True, "mensagem": "Encaminhamento para atendimento humano registrado."}


def encerrar_conversa(tool_context: ToolContext) -> dict:
    """Marca a conversa como encerrada. Use quando o assunto foi resolvido e o
    cliente se despediu ou confirmou que não precisa de mais nada."""
    tool_context.state["closing_requested"] = True
    return {"ok": True}
