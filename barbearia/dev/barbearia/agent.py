"""Ponte entre este worker e a dev UI do ADK (`adk web dev`).

Só pra testar a conversa na mão, sem RabbitMQ/Agent-Api/Postgres no meio.
Nada aqui roda em produção — em produção quem monta o agente é o
consumer.py, com o agent_config e o target vindos do payload da fila.

Como usar (da raiz deste worker, com o venv ativo):

    adk web dev

Depois abra a URL que o comando imprime e escolha o agente "barbearia".
"""

import sys
from pathlib import Path

# Raiz do worker no sys.path — o `adk web` só coloca a pasta de agentes (dev/)
# lá, e daqui a gente importa `src.*` do projeto.
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(RAIZ / ".env")

from src.services.adk.agent import build_agent  # noqa: E402

# Simula o que o consumer receberia da fila: a config do Agent Console e o
# contato do WhatsApp. Troque o "name" pra testar como o agente trata um
# cliente cujo nome ele já conhece (ou deixe None pra ele perguntar).
AGENT_CONFIG = {"id": "dev", "name": "Nina"}
TARGET = {"id": "dev-user", "waId": "5534999999999", "name": "Thiago", "metadata": {}}

root_agent = build_agent(AGENT_CONFIG, TARGET)
