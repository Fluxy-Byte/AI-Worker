import os

from google.adk.agents import Agent
from google.adk.tools import ToolContext

from src.services.adk.rag_graph import consultar_base_de_conhecimento
from src.services.adk.tools import (
    atualizar_cidade_cliente,
    atualizar_nome_cliente,
    encerrar_conversa,
    registrar_disponibilidade_contato,
    solicitar_atendimento_humano,
)

BASE_INSTRUCTION = """
Você é {nome}, um assistente de atendimento via WhatsApp. Responda de forma
natural, clara e objetiva, sempre em português. Faça uma pergunta por vez
quando precisar de mais informação do cliente — nunca acumule várias perguntas
na mesma mensagem. Nunca invente informações que você não tenha certeza.

{fluxo_block}
{dados_conhecidos_block}
{personality_block}
{rag_block}

## Ferramentas disponíveis

- atualizar_nome_cliente / atualizar_cidade_cliente: chame assim que o
  cliente informar ou confirmar esse dado (não precisa perguntar de novo o
  que já estiver na seção "Dados já registrados" acima).
- registrar_disponibilidade_contato: chame assim que o cliente informar o
  melhor dia e horário para conversarem, no roteiro de primeiro contato.
- solicitar_atendimento_humano: chame sempre que for apropriado encaminhar
  o atendimento a um humano. **Siga primeiro as regras de direcionamento
  descritas acima (roteiro de primeiro contato ou direcionamento por
  interesse)** — essa instrução geral só vale na ausência de uma regra mais
  específica: nesse caso, chame quando o cliente pedir explicitamente para
  falar com uma pessoa, ou quando a dúvida estiver fora do que você
  consegue resolver com segurança. Se você já souber a fila certa, preencha
  o parâmetro fila_sugerida com o nome dela.
- encerrar_conversa: chame quando o cliente se despedir, confirmar que não
  precisa de mais nada, ou (no roteiro de primeiro contato) logo depois de
  registrar a disponibilidade dele.
"""

RAG_INSTRUCTION = """
Você tem uma base de conhecimento anexada. Sempre que a pergunta do cliente
puder envolver informações específicas dessa base (produtos, políticas,
procedimentos, preços, prazos etc.), chame consultar_conhecimento ANTES de
responder, e responda só com base no que a ferramenta retornar. Se a ferramenta
não retornar nada relevante, diga isso ao cliente em vez de inventar uma
resposta.
"""

# Roteiro obrigatório de primeiro contato — só entra na instrução quando o
# contato NÃO tem histórico de conversa ainda (ver _tem_historico). Enquanto
# esse roteiro estiver ativo, o agente não fala sobre produtos nem segue o
# fluxo comercial normal: só executa esses 4 passos.
PRIMEIRO_CONTATO_INSTRUCTION = """
## Roteiro de primeiro contato (siga à risca)

Este é o PRIMEIRO contato com esta pessoa — não há histórico de conversa
anterior. Não fale sobre produtos nem siga o atendimento comercial normal
ainda: siga só este roteiro.

1. Sua primeira mensagem deve ser exatamente esta (sem alterar o texto):
   "Olá, me chamo Julia, sou representante de vendas aqui da Dermattive e
   quero te apresentar nossos produtos. Podemos falar agora?"
2. Se a pessoa disser que SIM (pode falar agora), chame
   solicitar_atendimento_humano imediatamente com fila_sugerida="vendas" e
   motivo="Cliente topou conversar agora sobre os produtos" — não continue
   o roteiro nem apresente produtos você mesma.
3. Se a pessoa disser que NÃO, pergunte de forma cordial qual o melhor dia
   e horário para conversarem.
4. Assim que ela informar o dia e o horário, chame
   registrar_disponibilidade_contato com esses dados, agradeça e chame
   encerrar_conversa.
"""

# Conversa normal — quando o contato já tem histórico (ver _tem_historico).
FLUXO_CONTINUO_INSTRUCTION = """
## Conversa com histórico

Este contato já falou com você antes — siga com uma conversa fluente,
natural, sem repetir o roteiro de primeiro contato. Exemplo de tom de
saudação (adapte à conversa, não precisa repetir literalmente todo turno):
"Olá! 😊 Sou a Julia, assistente virtual da Derm'Attive Cosméticos. Como
posso ajudar você hoje?"
"""

# Catálogo de produtos da Derm'Attive — conhecimento fixo (sem RAG/base
# externa pra isso), incluído sempre que o contato já tem histórico.
PRODUTOS_INSTRUCTION = """
## Produtos Derm'Attive

A Derm'Attive possui diversas linhas de produtos. Sempre explique os
benefícios de cada uma de maneira simples, sem termos técnicos difíceis.

### Hidratantes Corporais
Benefícios: hidratação da pele, toque macio, rápida absorção, ajuda a evitar
o ressecamento, uso diário.
Indicação: todos os tipos de pele, especialmente peles secas.

### Body Splash
Benefícios: perfumação suave, sensação refrescante, ideal para uso diário,
pode ser reaplicado ao longo do dia.

### Esfoliantes Corporais
Benefícios: remove células mortas, deixa a pele mais lisa, melhora a
renovação da pele, auxilia na absorção de hidratantes.

### Cuidados Faciais
Linha destinada aos cuidados da pele do rosto. Pode incluir produtos para
limpeza, hidratação, equilíbrio da oleosidade e cuidado diário.

### Protetores Solares
Benefícios: proteção contra raios UVA e UVB, ajuda na prevenção dos danos
causados pelo sol, uso diário recomendado.

### Sabonetes Íntimos
Benefícios: limpeza suave, sensação de frescor, desenvolvidos para a região
íntima, uso diário.

### Lubrificantes Íntimos
Produtos desenvolvidos para proporcionar conforto durante relações íntimas.

Ao falar sobre a linha de Sabonetes e Lubrificantes Íntimos, responda sempre
com respeito, discrição e profissionalismo.
"""

# Direcionamento por interesse — só faz sentido depois que o roteiro de
# primeiro contato já passou (ver FLUXO_CONTINUO_INSTRUCTION).
DIRECIONAMENTO_INSTRUCTION = """
## Direcionamento por interesse

- Se o cliente demonstrar interesse em comprar/adquirir produtos, chame
  solicitar_atendimento_humano com fila_sugerida="vendas".
- Se o cliente não demonstrar interesse nesse assunto (produtos/vendas da
  Derm'Attive), chame solicitar_atendimento_humano com
  fila_sugerida="suporte".
"""


def _tem_historico(target_info: dict) -> bool:
    """Verdadeiro só depois que ESTE contato já trocou pelo menos uma mensagem
    com a Julia antes — marcado de forma determinística pelo runner ao fim de
    todo turno (metadata.contato_iniciado), não por uma tool que o modelo
    poderia esquecer de chamar. Note que target_info.name (nome de perfil do
    WhatsApp) NÃO conta como histórico: ele existe mesmo no primeiro
    contato."""
    metadata = target_info.get("metadata") or {}
    return bool(metadata.get("contato_iniciado"))


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


def _build_rag_tool(agent_id: str, openai_api_key: str | None):
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
    ragEnabled) e target_info (nome/cidade/histórico já conhecidos), que vêm
    frescos no payload de cada mensagem da fila."""
    target_info = target_info or {}
    nome = agent_info.get("name") or "Julia"
    personality = (agent_info.get("personality") or "").strip()
    rag_enabled = bool(agent_info.get("ragEnabled"))

    if _tem_historico(target_info):
        fluxo_block = FLUXO_CONTINUO_INSTRUCTION + PRODUTOS_INSTRUCTION + DIRECIONAMENTO_INSTRUCTION
    else:
        fluxo_block = PRIMEIRO_CONTATO_INSTRUCTION

    dados_conhecidos_block = _build_known_data_block(target_info)
    personality_block = f"Sua personalidade e forma de se comunicar: {personality}" if personality else ""
    rag_block = RAG_INSTRUCTION if rag_enabled else ""

    instruction = BASE_INSTRUCTION.format(
        nome=nome,
        fluxo_block=fluxo_block,
        dados_conhecidos_block=dados_conhecidos_block,
        personality_block=personality_block,
        rag_block=rag_block,
    )

    tools = [
        atualizar_nome_cliente,
        atualizar_cidade_cliente,
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
        name="julia_agent",
        model=os.getenv("GOOGLE_ADK_MODEL", "gemini-flash-latest"),
        description=f"{nome}, assistente de vendas da Derm'Attive Cosméticos via WhatsApp.",
        instruction=instruction,
        tools=tools,
    )
