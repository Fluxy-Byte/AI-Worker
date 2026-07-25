from src.infra.pgvector.conection import (
    get_vector_store
)

def job_consultar_embedding_por_categoria(
    pergunta: str,
    categoria: str,
    agent_id: str,
    agent_name: str
):

    vector_store = get_vector_store(f"documentos_{agent_name}")

    resultado = vector_store.similarity_search(
        query=pergunta,
        k=3,
        filter={
            "categoria": categoria,
            "agent_id": agent_id
        }
    )

    return [
        doc.page_content
        for doc in resultado
    ]