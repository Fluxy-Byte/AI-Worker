"""Adaptador só para `adk web` — o worker de produção monta o Agent do zero a
cada mensagem (ver src/services/adk/agent.py:build_agent), com a conta
resolvida pelo telefone do contato. Aqui expomos um root_agent fixo com uma
conta fake, pra poder testar a instrução/tools no `adk web` sem depender do
RabbitMQ nem do fluxy-gestao-be rodando local.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

from src.services.adk.agent import build_agent
from src.services.adk.fluxy_auth import ContaFluxy

_agent_config = {
    "name": "Fly",
    "personality": "Simpática, objetiva e prestativa. Trate o cliente pelo nome quando souber.",
}

# Troque autorizado=False pra testar o fluxo de conta não encontrada/telefone
# ausente (ver _build_account_block em agent.py).
_conta_teste = ContaFluxy(
    phone="5511999999999",
    autorizado=True,
    user_id="user-teste-local",
    company_name="Laboratório Teste",
    plan="Diamante",
)

root_agent = build_agent(_agent_config, _conta_teste)
