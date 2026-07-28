import os

from google.adk.agents import Agent
from google.adk.tools import ToolContext

from src.services.adk.rag_graph import consultar_base_de_conhecimento
from src.services.adk.tools import encerrar_conversa, solicitar_atendimento_humano

BASE_INSTRUCTION = """
Você é {nome}, um assistente de atendimento via WhatsApp. Responda de forma
natural, clara e objetiva, sempre em português. Faça uma pergunta por vez
quando precisar de mais informação do cliente — nunca acumule várias perguntas
na mesma mensagem. Nunca invente informações que você não tenha certeza: se não
souber algo, diga que vai verificar ou ofereça encaminhar para um atendente
humano (chame solicitar_atendimento_humano).

{personality_block}
{rag_block}

Se o cliente se despedir ou confirmar que não precisa de mais nada, chame
encerrar_conversa.
"""

RAG_INSTRUCTION = """
Você tem uma base de conhecimento anexada. Sempre que a pergunta do cliente
puder envolver informações específicas dessa base (produtos, políticas,
procedimentos, preços, prazos etc.), chame consultar_conhecimento ANTES de
responder, e responda só com base no que a ferramenta retornar. Se a ferramenta
não retornar nada relevante, diga isso ao cliente em vez de inventar uma
resposta.
"""


def _build_rag_tool(agent_id: str):
    """A tool de RAG é montada como closure (capturando agent_id) em vez de uma
    função de módulo fixa — como o worker "max" atende agentes/organizações
    diferentes através da mesma fila genérica (task.agent.generic.create), não
    existe um agent_id fixo pra hardcodar num tools.py estático."""

    async def consultar_conhecimento(tool_context: ToolContext, pergunta: str) -> dict:
        """Busca na base de conhecimento anexada a este agente informações
        relevantes pra responder à pergunta do cliente."""
        contexto = await consultar_base_de_conhecimento(pergunta, agent_id)
        if not contexto:
            return {"contexto": "", "aviso": "Nada relevante encontrado na base de conhecimento."}
        return {"contexto": contexto}

    return consultar_conhecimento


def build_agent(agent_info: dict) -> Agent:
    """Monta o Agent do ADK do zero a cada mensagem (não é um root_agent fixo
    como no axel) — instrução e ferramentas variam por agent_info (personality/
    ragEnabled), que vem fresco no payload de cada mensagem da fila."""
    nome = agent_info.get("name") or "Assistente"
    personality = (agent_info.get("personality") or "").strip()
    rag_enabled = bool(agent_info.get("ragEnabled"))

    personality_block = f"Sua personalidade e forma de se comunicar: {personality}" if personality else ""
    rag_block = RAG_INSTRUCTION if rag_enabled else ""

    instruction = BASE_INSTRUCTION.format(nome=nome, personality_block=personality_block, rag_block=rag_block)

    tools = [solicitar_atendimento_humano, encerrar_conversa]
    if rag_enabled:
        tools.append(_build_rag_tool(agent_info["id"]))

    return Agent(
        # Nome interno do ADK — fixo, não é o nome de exibição do agente (que
        # pode ter espaços/acentos, ex: "Assistente Virtual"). O nome de
        # exibição só entra na instrução (`nome` acima).
        name="generic_agent",
        model=os.getenv("GOOGLE_ADK_MODEL", "gemini-flash-latest"),
        description=f"{nome}, agente genérico configurável via Agent Console.",
        instruction=instruction,
        tools=tools,
    )
