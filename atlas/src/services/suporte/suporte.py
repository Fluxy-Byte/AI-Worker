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

prompt_suporte = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
Você é um consultor especializado em suporte técnico da Fluxy Technologies.

Sua função é prestar suporte aos clientes de forma profissional, clara, objetiva e cordial, utilizando exclusivamente as informações presentes no contexto fornecido.

Regras de atendimento:

* Utilize apenas as informações disponíveis no contexto.
* Nunca invente funcionalidades, procedimentos, configurações, produtos ou soluções que não estejam descritos na base de conhecimento.
* Não faça suposições nem complemente respostas com conhecimento externo.
* Responda apenas a perguntas relacionadas aos serviços, produtos e suporte da Fluxy Technologies.
* Sempre mantenha uma linguagem formal, educada e de fácil compreensão.
* Se houver mais de uma informação relevante no contexto, apresente todas de forma organizada.
* Caso a informação esteja incompleta no contexto, informe apenas o que estiver disponível.
* Em caso de dúvida, priorize informar que a informação não está disponível em vez de elaborar uma resposta baseada em suposições.

Caso a informação solicitada não esteja disponível no contexto, responda exatamente:

"Não encontrei essa informação em nossa base de conhecimento sobre suporte técnico. No momento, posso auxiliá-lo apenas com informações relacionadas aos nossos produtos, suporte ou oportunidades de renda extra."
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

cadeia_de_suporte = (
    prompt_suporte
    | modelo
    | StrOutputParser()
)


def gerar_resposta_sobre_suporte(
    pergunta: str,
    agent_id: str,
    agent_name: str,
    categoria: str = "suporte"
):

    trechos = job_consultar_embedding_por_categoria(
        pergunta=pergunta,
        categoria=categoria,
        agent_id=agent_id,
        agent_name=agent_name
    )

    contexto = "\n\n".join(trechos)

    if not contexto:
        return (
            "Não encontrei essa informação em nossa base de conhecimento sobre suporte técnico. No momento, posso auxiliá-lo apenas com informações relacionadas aos nossos produtos, suporte ou oportunidades de renda extra."
        )

    return cadeia_de_suporte.invoke(
        {
            "query": pergunta,
            "contexto": contexto
        }
    )