import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.document_loaders import TextLoader, PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from typing import TypedDict, Literal

load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

modelo = ChatOpenAI(
    model="gpt-4o-mini",
    temperature="0.5",
    api_key=api_key
)


class Rota(TypedDict):
    tipo: Literal["produto", "suporte", "renda-extra", "atendimento_humano"]


prompt_root = ChatPromptTemplate(
    [
        (
            "system",
            "Responda apenas com as categorias a seguir: produto caso o interesse seja "
            "comprar, suporte caso o cliente precise de ajuda com qualquer coisa, "
            "renda-extra caso sua duvida seja sobre ganhar dinheiro ou renda, ou "
            "atendimento_humano caso o cliente peça explicitamente para falar com uma "
            "pessoa/atendente/humano, ou demonstre claramente frustração/reclamação que "
            "uma resposta automática não resolveria.",
        ),
        ("human", "{query}"),
    ]
)

roteador = prompt_root | modelo.with_structured_output(Rota)

def definir_categoria_da_pergunta(pergunta :str):
    return roteador.invoke({"query": pergunta})['tipo']
