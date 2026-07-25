import os

from dotenv import load_dotenv
from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector

load_dotenv()

# Corrigido: a connection string (incluindo senha em texto puro) estava
# hardcoded aqui. Agora vem 100% de URL_PGVECTOR.
DATABASE_URL = os.getenv("URL_PGVECTOR")

embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    api_key=os.getenv("OPENAI_API_KEY"),
)


def get_vector_store(collection_name: str):
    return PGVector(
        embeddings=embeddings,
        collection_name=collection_name,
        connection=DATABASE_URL,
        use_jsonb=True
    )
