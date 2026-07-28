from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from src.infra.pgvector.connection import get_vector_store


class RagState(TypedDict):
    pergunta: str
    agent_id: str
    trechos: list[str]
    contexto: str


def _retrieve(state: RagState) -> dict:
    vector_store = get_vector_store()
    resultados = vector_store.similarity_search(
        query=state["pergunta"],
        k=4,
        filter={"agent_id": state["agent_id"]},
    )
    return {"trechos": [doc.page_content for doc in resultados]}


def _compile_context(state: RagState) -> dict:
    contexto = "\n\n---\n\n".join(state["trechos"]) if state["trechos"] else ""
    return {"contexto": contexto}


# Grafo pequeno de propósito — retrieve (busca vetorial no pgvector, filtrada
# por agent_id) → compile_context (junta os trechos num texto só). Compilado
# uma vez no import, reaproveitado a cada chamada da tool consultar_conhecimento.
_graph = (
    StateGraph(RagState)
    .add_node("retrieve", _retrieve)
    .add_node("compile_context", _compile_context)
    .add_edge(START, "retrieve")
    .add_edge("retrieve", "compile_context")
    .add_edge("compile_context", END)
    .compile()
)


async def consultar_base_de_conhecimento(pergunta: str, agent_id: str) -> str:
    resultado = await _graph.ainvoke({"pergunta": pergunta, "agent_id": agent_id, "trechos": [], "contexto": ""})
    return resultado.get("contexto", "")
