import os

from google.adk.agents import Agent
from google.adk.tools import ToolContext

from src.services.adk.rag_graph import consultar_base_de_conhecimento
from src.services.adk.tools import (
    atualizar_cidade_cliente,
    atualizar_nome_cliente,
    encerrar_conversa,
    solicitar_atendimento_humano,
)

BASE_INSTRUCTION = """
Você é {nome}, um assistente de atendimento via WhatsApp. Responda de forma
natural, clara e objetiva, sempre em português. Faça uma pergunta por vez
quando precisar de mais informação do cliente — nunca acumule várias perguntas
na mesma mensagem. Nunca invente informações que você não tenha certeza.

{dados_conhecidos_block}
{personality_block}
{rag_block}

## Ferramentas disponíveis

- atualizar_nome_cliente / atualizar_cidade_cliente: chame assim que o
  cliente informar ou confirmar esse dado (não precisa perguntar de novo o
  que já estiver na seção "Dados já registrados" acima).
- solicitar_atendimento_humano: chame sempre que for apropriado encaminhar
  o atendimento a um humano. **Siga primeiro as regras específicas de
  quando e para onde encaminhar descritas na sua personalidade acima, se
  ela definir isso** — essa instrução geral só vale na ausência de uma
  regra mais específica: nesse caso, chame quando o cliente pedir
  explicitamente para falar com uma pessoa, ou quando a dúvida estiver fora
  do que você consegue resolver com segurança. Se você souber exatamente
  qual fila/departamento é o destino certo, preencha o parâmetro
  fila_sugerida com o nome dela.
- encerrar_conversa: chame quando o cliente se despedir ou confirmar que
  não precisa de mais nada.
"""

RAG_INSTRUCTION = """
Você tem uma base de conhecimento anexada. Sempre que a pergunta do cliente
puder envolver informações específicas dessa base (produtos, políticas,
procedimentos, preços, prazos etc.), chame consultar_conhecimento ANTES de
responder, e responda só com base no que a ferramenta retornar. Se a ferramenta
não retornar nada relevante, diga isso ao cliente em vez de inventar uma
resposta.
"""


def _build_known_data_block(target_info: dict) -> str:
    """Dados que já existem no cadastro do contato (nome vindo do perfil do
    WhatsApp ou já registrado em conversa anterior via atualizar_nome_cliente/
    atualizar_cidade_cliente) — evita que o agente pergunte de novo algo que
    já sabe, mesmo numa sessão nova."""
    metadata = target_info.get("metadata") or {}
    nome = target_info.get("name") or metadata.get("nome")
    cidade = metadata.get("cidade")

    if not nome and not cidade:
        return ""

    linhas = ["Dados já registrados deste contato — não pergunte de novo o que já está aqui:"]
    if nome:
        linhas.append(f"- Nome: {nome}")
    if cidade:
        linhas.append(f"- Cidade: {cidade}")
    return "\n".join(linhas)


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


def build_agent(agent_info: dict, target_info: dict | None = None) -> Agent:
    """Monta o Agent do ADK do zero a cada mensagem (não é um root_agent fixo
    como no axel) — instrução e ferramentas variam por agent_info (personality/
    ragEnabled) e target_info (nome/cidade já conhecidos), que vêm frescos no
    payload de cada mensagem da fila."""
    nome = agent_info.get("name") or "Assistente"
    personality = (agent_info.get("personality") or "").strip()
    rag_enabled = bool(agent_info.get("ragEnabled"))

    dados_conhecidos_block = _build_known_data_block(target_info or {})
    personality_block = f"Sua personalidade e forma de se comunicar: {personality}" if personality else ""
    rag_block = RAG_INSTRUCTION if rag_enabled else ""

    instruction = BASE_INSTRUCTION.format(
        nome=nome,
        dados_conhecidos_block=dados_conhecidos_block,
        personality_block=personality_block,
        rag_block=rag_block,
    )

    tools = [atualizar_nome_cliente, atualizar_cidade_cliente, solicitar_atendimento_humano, encerrar_conversa]
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
