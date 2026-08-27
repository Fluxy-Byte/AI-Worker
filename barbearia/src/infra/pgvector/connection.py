import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

load_dotenv()

DATABASE_URL = os.getenv("URL_PGVECTOR")

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.getenv("OPENAI_API_KEY"),
)

# Coleção única compartilhada por TODOS os agentes genéricos (diferente do
# atlas, que tem uma coleção por agente) — como o mesmo processo "max" atende
# qualquer agente/organização através da fila task.agent.generic.create
# (nenhum worker dedicado por nome), não dá pra nomear a coleção pelo nome do
# agente (colidiria entre organizações). Todo chunk carrega "agent_id" no
# metadata e toda busca filtra por ele.
GENERIC_AGENTS_COLLECTION = "documentos_agentes_generic"


def get_vector_store(collection_name: str = GENERIC_AGENTS_COLLECTION) -> PGVector:
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=DATABASE_URL,
        use_jsonb=True,
    )
