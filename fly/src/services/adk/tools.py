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


def registrar_telefone_contato(tool_context: ToolContext, telefone: str) -> dict:
    """Registra o telefone que o cliente acabou de informar, para os casos
    raros em que a Meta não entregou automaticamente o telefone deste
    contato — é a chave usada para localizar a conta Fluxy Gestão dele e
    liberar consulta a clientes/OS/serviços. Chame assim que o cliente
    informar o número (com DDD), mesmo que em outro formato (com espaços,
    traço, parênteses etc.)."""
    tool_context.state["telefone"] = telefone
    return {"ok": True}
