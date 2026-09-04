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


def atualizar_empresa_cliente(tool_context: ToolContext, nome_empresa: str) -> dict:
    """Registra o nome da empresa do contato assim que ele informar ou
    confirmar — só pergunte se ainda não estiver nos dados já conhecidos
    deste contato."""
    tool_context.state["nome_empresa"] = nome_empresa
    return {"nome_empresa": nome_empresa}


def atualizar_cargo_cliente(tool_context: ToolContext, cargo: str) -> dict:
    """Registra o cargo/função do contato na empresa dele assim que ele
    informar ou confirmar — só pergunte se ainda não estiver nos dados já
    conhecidos deste contato."""
    tool_context.state["cargo"] = cargo
    return {"cargo": cargo}


def atualizar_quantidade_funcionarios_cliente(
    tool_context: ToolContext, quantidade_de_funcionarios: str
) -> dict:
    """Registra a quantidade de funcionários da empresa do contato, exatamente
    como ele informar (pode ser um número aproximado, ex: 'cerca de 50') — só
    pergunte se ainda não estiver nos dados já conhecidos deste contato."""
    tool_context.state["quantidade_de_funcionarios"] = quantidade_de_funcionarios
    return {"quantidade_de_funcionarios": quantidade_de_funcionarios}


def registrar_disponibilidade_contato(tool_context: ToolContext, dia: str, horario: str) -> dict:
    """Registra o melhor dia e horário que o cliente informou para vocês
    conversarem — chame assim que ele responder isso, no roteiro de primeiro
    contato (depois de dizer que não pode falar agora)."""
    tool_context.state["dia_preferido"] = dia
    tool_context.state["horario_preferido"] = horario
    return {"dia": dia, "horario": horario}
