import os

from google.adk.agents import Agent
from google.adk.tools import ToolContext

from src.services.adk.infos import CHAVES_METADATA
from src.services.adk.rag_graph import consultar_base_de_conhecimento
from src.services.adk.tools import (
    atualizar_cargo_cliente,
    atualizar_empresa_cliente,
    atualizar_nome_cliente,
    atualizar_quantidade_funcionarios_cliente,
    encerrar_conversa,
    registrar_disponibilidade_contato,
    solicitar_atendimento_humano,
)

BASE_INSTRUCTION = """
Você é {nome}, recepcionista virtual da Fluxy Agentes, atendendo via WhatsApp.
Responda de forma natural, clara e objetiva, sempre em português. Faça uma
pergunta por vez quando precisar de mais informação do contato — nunca
acumule várias perguntas na mesma mensagem. Nunca invente informações que
você não tenha certeza.

{fluxo_block} # Fluxo de instrução do primeiro contato ou apos o primeiro contato
{coleta_dados_block} # Roteiro obrigatório de coleta de dados do contato
{dados_conhecidos_block} # Dados salvos no contato no campo do metadado
{personality_block} # Personalidade vinda da interface agent consoloe
{rag_block} # Dados coletados no Rag

## Ferramentas disponíveis

- atualizar_nome_cliente / atualizar_empresa_cliente / atualizar_cargo_cliente
  / atualizar_quantidade_funcionarios_cliente: chame cada uma assim que o
  contato informar ou confirmar o dado correspondente (não precisa
  perguntar de novo o que já estiver na seção "Dados já registrados" acima).
- registrar_disponibilidade_contato: chame se o contato informar o melhor
  dia e horário para conversarem, caso isso seja pedido a ele.
- solicitar_atendimento_humano: chame assim que os 4 dados obrigatórios
  estiverem confirmados, para encaminhar o atendimento. Se você já souber a
  fila certa, preencha o parâmetro fila_sugerida com o nome dela. Também
  chame sempre que o contato pedir explicitamente para falar com uma
  pessoa, ou quando a dúvida estiver fora do que você consegue resolver com
  segurança.
- encerrar_conversa: chame quando o contato se despedir, confirmar que não
  precisa de mais nada, ou logo depois de encaminhar o atendimento humano.
"""

RAG_INSTRUCTION = """
Você tem uma base de conhecimento anexada. Sempre que a pergunta do cliente
puder envolver informações específicas dessa base chame consultar_conhecimento ANTES de
responder, e responda só com base no que a ferramenta retornar. Se a ferramenta
não retornar nada relevante, diga isso ao cliente em vez de inventar uma
resposta.
"""

# Saudação obrigatória — só entra na instrução quando o contato NÃO tem
# histórico de conversa ainda (ver _tem_historico).
PRIMEIRO_CONTATO_INSTRUCTION = """
## Primeiro contato

Este é o PRIMEIRO contato com esta pessoa — não há histórico de conversa
anterior. Apresente-se de forma breve e cordial como a recepcionista virtual
da empresa, explique que precisa confirmar alguns dados rápidos antes de
encaminhar o atendimento, e comece a coleta de dados descrita abaixo.
"""

# Conversa normal — quando o contato já tem histórico (ver _tem_historico).
FLUXO_CONTINUO_INSTRUCTION = """
## Conversa com histórico

Este contato já falou com você antes — continue de forma fluida e natural,
sem repetir a apresentação inicial. Siga direto para a coleta de dados
descrita abaixo, pulando o que já estiver em "Dados já registrados".
"""

# Roteiro de coleta de dados — sempre presente, independente de já ter
# histórico ou não. Dirigido pelo bloco "Dados já registrados"
# (_build_known_data_block), não por qual turno da conversa está.
COLETA_DADOS_INSTRUCTION = """
## Coleta de dados obrigatória

Antes de encaminhar o atendimento, confirme estes 4 dados sobre o contato,
um de cada vez (pule qualquer um que já esteja em "Dados já registrados"
acima):

1. Nome da pessoa
2. Nome da empresa em que trabalha
3. Cargo/função que ocupa na empresa
4. Quantidade de funcionários da empresa

Assim que o contato informar cada dado, chame a ferramenta correspondente
imediatamente (atualizar_nome_cliente, atualizar_empresa_cliente,
atualizar_cargo_cliente, atualizar_quantidade_funcionarios_cliente).

Assim que TODOS os 4 dados estiverem confirmados (já registrados ou
coletados nesta conversa), chame solicitar_atendimento_humano para
encaminhar o atendimento e, em seguida, encerrar_conversa. Não continue
fazendo perguntas depois disso.
"""


"""
------------------------------------

Abaixo temos funções de funcionamento padrão de agentes

------------------------------------
"""

def _tem_historico(target_info: dict) -> bool: # Checar o metadado para ver se a variavel existe de contato iniciado
    """Verdadeiro só depois que ESTE contato já trocou pelo menos uma mensagem
    com o agente antes — marcado de forma determinística pelo runner ao fim de
    todo turno (metadata.contato_iniciado), não por uma tool que o modelo
    poderia esquecer de chamar. Note que target_info.name (nome de perfil do
    WhatsApp) NÃO conta como histórico: ele existe mesmo no primeiro
    contato."""
    metadata = target_info.get("metadata") or {}
    return bool(metadata.get("contato_iniciado"))


LABELS_METADATA = {
    "nome": "Nome",
    "nome_empresa": "Empresa",
    "cargo": "Cargo",
    "quantidade_de_funcionarios": "Quantidade de funcionários",
}


def _build_known_data_block(target_info: dict) -> str: # Função de coletar os metadados e passar para o agente
    """Dados que já existem no cadastro do contato (nome vindo do perfil do
    WhatsApp ou qualquer um dos CHAVES_METADATA já registrado em conversa
    anterior via atualizar_*_cliente) — evita que o agente pergunte de novo
    algo que já sabe, mesmo numa sessão nova."""
    metadata = target_info.get("metadata") or {}
    nome = target_info.get("name") or metadata.get("nome")

    dados: dict[str, str] = {}
    if nome:
        dados["nome"] = nome
    for chave in CHAVES_METADATA:
        if chave == "nome":
            continue
        valor = metadata.get(chave)
        if valor:
            dados[chave] = valor

    if not dados:
        return "Nenhum dado deste contato foi registrado ainda."

    linhas = ["Dados já registrados deste contato — não pergunte de novo o que já está aqui:"]
    for chave, valor in dados.items():
        linhas.append(f"- {LABELS_METADATA.get(chave, chave)}: {valor}")
    return "\n".join(linhas)


def _build_rag_tool(agent_id: str, openai_api_key: str | None): # Retorna os chunks encontratos de acordo com a pergunta do usuario
    """A tool de RAG é montada como closure (capturando agent_id/openai_api_key)
    em vez de uma função de módulo fixa — como o worker atende agentes/
    organizações diferentes através da mesma fila genérica, não existe um
    agent_id fixo pra hardcodar num tools.py estático. openai_api_key vem do
    Agent Console (token por agente, criptografado no banco); None cai no
    fallback do env em get_embeddings (ver infra/pgvector/connection.py)."""

    async def consultar_conhecimento(tool_context: ToolContext, pergunta: str) -> dict:
        """Busca na base de conhecimento anexada a este agente informações
        relevantes pra responder à pergunta do cliente."""
        contexto = await consultar_base_de_conhecimento(pergunta, agent_id, openai_api_key)
        if not contexto:
            return {"contexto": "", "aviso": "Nada relevante encontrado na base de conhecimento."}
        return {"contexto": contexto}

    return consultar_conhecimento


def build_agent(agent_info: dict, target_info: dict | None = None) -> Agent:
    """Monta o Agent do ADK do zero a cada mensagem (não é um root_agent fixo
    como no axel) — instrução e ferramentas variam por agent_info (personality/
    ragEnabled) e target_info (nome/histórico já conhecidos), que vêm
    frescos no payload de cada mensagem da fila."""
    target_info = target_info or {}
    # nome = agent_info.get("name") or "piloto"
    nome = "Fly" # Esta manual para testes
    personality = (agent_info.get("personality") or "").strip()
    rag_enabled = bool(agent_info.get("ragEnabled"))

    if _tem_historico(target_info):
        fluxo_block = FLUXO_CONTINUO_INSTRUCTION
    else:
        fluxo_block = PRIMEIRO_CONTATO_INSTRUCTION

    dados_conhecidos_block = _build_known_data_block(target_info)
    personality_block = f"Sua personalidade e forma de se comunicar: {personality}" if personality else ""
    rag_block = RAG_INSTRUCTION if rag_enabled else ""

    instruction = BASE_INSTRUCTION.format(
        nome=nome,
        fluxo_block=fluxo_block,
        coleta_dados_block=COLETA_DADOS_INSTRUCTION,
        dados_conhecidos_block=dados_conhecidos_block,
        personality_block=personality_block,
        rag_block=rag_block,
    )

    tools = [
        atualizar_nome_cliente,
        atualizar_empresa_cliente,
        atualizar_cargo_cliente,
        atualizar_quantidade_funcionarios_cliente,
        registrar_disponibilidade_contato,
        solicitar_atendimento_humano,
        encerrar_conversa,
    ]

    if rag_enabled:
        tools.append(_build_rag_tool(agent_info["id"], agent_info.get("openaiToken")))

    return Agent(
        # Nome interno do ADK — fixo, não é o nome de exibição do agente (que
        # pode ter espaços/acentos, ex: "Assistente Virtual"). O nome de
        # exibição só entra na instrução (`nome` acima).
        name="recepcionista_agent",
        model=os.getenv("GOOGLE_ADK_MODEL", "gemini-flash-latest"),
        description=f"Fly recepcionista virtual via WhatsApp.",
        instruction=instruction,
        tools=tools,
    )
