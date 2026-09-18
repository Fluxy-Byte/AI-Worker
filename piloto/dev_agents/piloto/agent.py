"""Agente de desenvolvimento para uso com `adk web`.

O agent.py real (src/services/adk/agent.py) não expõe um root_agent fixo —
ele é montado a cada mensagem via build_agent(agent_info, target_info), com
dados que vêm da fila (Agent Console + contato). Para poder testar o agente
interativamente no `adk web`, montamos aqui um root_agent com dados de
exemplo. Ajuste os dicts abaixo para simular outros cenários (ragEnabled,
dados já registrados do contato, etc.).
"""

from src.services.adk.agent import build_agent

AGENT_INFO_TESTE = {
    "id": "dev-teste",
    "personality": "",
    "ragEnabled": False,
    "openaiToken": None,
}

TARGET_INFO_TESTE = {
    "id": "dev-contato",
    "name": "Contato de Teste",
    "metadata": {},
}

root_agent = build_agent(AGENT_INFO_TESTE, TARGET_INFO_TESTE)
