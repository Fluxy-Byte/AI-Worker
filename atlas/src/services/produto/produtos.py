import os

from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from src.services.job.consultar_base_vetorial import (
    job_consultar_embedding_por_categoria
)

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")

modelo = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.5,
    api_key=api_key
)

prompt_produtos = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
Você é um consultor especializado em produtos de tecnologia.

Sua função é responder às dúvidas dos clientes de forma profissional, clara, objetiva e cordial, utilizando exclusivamente as informações fornecidas no contexto.

Regras de atendimento:

* Utilize apenas as informações presentes no contexto.
* Nunca invente produtos, funcionalidades, características, preços, prazos ou qualquer outra informação que não esteja disponível.
* Não faça suposições nem complemente respostas com conhecimento externo.
* Sempre mantenha uma linguagem formal, educada e objetiva.
* Quando apropriado, organize as informações em tópicos para facilitar a compreensão.

Caso a informação solicitada não esteja disponível no contexto, responda exatamente:

"Não encontrei essa informação em nossa base de conhecimento sobre esse produto ou seus detalhes. No momento, posso auxiliá-lo apenas com informações relacionadas aos nossos produtos, suporte ou oportunidades de renda extra."

"""
        ),
        (
            "human",
            """
Pergunta:
{query}

Contexto:
{contexto}

Resposta:
"""
        )
    ]
)

cadeia_de_produtos = (
    prompt_produtos
    | modelo
    | StrOutputParser()
)


def gerar_resposta_sobre_produtos(
    pergunta: str,
    agent_id: str,
    agent_name: str,
    categoria: str = "produto"
):

    trechos = job_consultar_embedding_por_categoria(
        pergunta=pergunta,
        categoria=categoria,
        agent_id=agent_id,
        agent_name=agent_name
    )

    contexto = "\n\n".join(trechos)

    return cadeia_de_produtos.invoke(
        {
            "query": pergunta,
            "contexto": contexto
        }
    )