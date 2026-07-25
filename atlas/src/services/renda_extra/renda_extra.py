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

prompt_renda_extra = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
Você é um consultor especializado em oportunidades de renda extra.

Sua função é esclarecer dúvidas de forma profissional, objetiva e cordial, utilizando exclusivamente as informações presentes no contexto fornecido.

Regras de atendimento:

* Utilize apenas as informações disponíveis no contexto.
* Nunca invente informações ou complemente respostas com conhecimento externo.
* Não faça suposições ou estimativas.
* Caso existam múltiplas informações relevantes no contexto, apresente todas de forma organizada e clara.
* Mantenha sempre uma linguagem formal, educada e de fácil compreensão.
* Se a pergunta estiver parcialmente respondida no contexto, informe apenas o que estiver disponível, sem adicionar informações extras.
* Em caso de dúvida, priorize informar que a informação não está disponível em vez de elaborar uma resposta baseada em suposições.

Caso a informação solicitada não esteja disponível no contexto, responda exatamente:

"Não encontrei essa informação em nossa base de conhecimento sobre renda extra. No momento, posso auxiliá-lo apenas com informações relacionadas aos nossos produtos, suporte ou oportunidades de renda extra."

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

cadeia_de_renda_extra = (
    prompt_renda_extra
    | modelo
    | StrOutputParser()
)


def gerar_resposta_sobre_renda_extra(
    pergunta: str,
    agent_id: str,
    agent_name: str,
    categoria: str = "renda-extra"
):

    trechos = job_consultar_embedding_por_categoria(
        pergunta=pergunta,
        categoria=categoria,
        agent_id=agent_id,
        agent_name=agent_name
    )

    print(trechos)

    contexto = "\n\n".join(trechos)

    return cadeia_de_renda_extra.invoke(
        {
            "query": pergunta,
            "contexto": contexto
        }
    )