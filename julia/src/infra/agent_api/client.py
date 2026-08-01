import json
import os
import unicodedata

import httpx
from openai import OpenAI

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:7073")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")


def _normalize(text: str) -> str:
    """minúsculas, sem acento, só alfanumérico — pra casar 'Goioerê' com
    'Goioere', ou 'Venda de Novos — Toledo' com 'Venda de novos Toledo'."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return "".join(ch for ch in sem_acento.lower() if ch.isalnum())

_openai_client: OpenAI | None = None


def _get_openai_client() -> OpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


def get_service_island_queues(service_island_id: str) -> list[dict]:
    """Lista as filas da ilha de atendimento ligada ao WhatsApp Channel do
    contato — usada na hora do handoff pra decidir o destino do ticket."""
    response = httpx.get(
        f"{BASE_URL}/internal/service-islands/{service_island_id}/queues",
        headers={"x-internal-api-key": INTERNAL_API_KEY},
        timeout=10,
    )
    response.raise_for_status()
    return response.json().get("result", [])


def choose_handoff_queue(
    queues: list[dict],
    reason: str,
    default_queue_id: str | None,
    suggested_queue_name: str | None = None,
) -> str | None:
    """Decide para qual fila da ilha o ticket de handoff deve ir, dado o motivo
    do transbordo. Cai para a fila padrão do agente (ou a primeira disponível)
    se não conseguir decidir com segurança.

    Se o agente já souber exatamente o nome da fila (suggested_queue_name —
    ex: personalidades com fluxo próprio de setor+cidade), tenta um match
    exato (ignorando acento/maiúscula/pontuação) ANTES de cair pro
    classificador por IA — muito mais confiável que depender só do "motivo"
    livre quando há muitas filas parecidas."""
    if not queues:
        return default_queue_id
    if len(queues) == 1:
        return queues[0]["id"]

    fallback = default_queue_id or queues[0]["id"]

    if suggested_queue_name:
        normalized_suggestion = _normalize(suggested_queue_name)
        for q in queues:
            if _normalize(q.get("name", "")) == normalized_suggestion:
                return q["id"]
        # Sem match exato: aceita conter/ser contido (ex: sugestão sem a
        # cidade, ou fila com um sufixo a mais) — ainda mais confiável que a
        # classificação livre por IA quando o nome bate quase todo.
        for q in queues:
            normalized_name = _normalize(q.get("name", ""))
            if normalized_name and (normalized_name in normalized_suggestion or normalized_suggestion in normalized_name):
                return q["id"]

    try:
        options = [{"id": q["id"], "name": q.get("name", "")} for q in queues]
        response = _get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Escolha a fila de atendimento mais adequada para o motivo de "
                        "transbordo abaixo, entre as opções fornecidas. Responda só com "
                        'JSON no formato {"queue_id": "<id escolhido>"}.'
                    ),
                },
                {"role": "user", "content": json.dumps({"motivo": reason, "filas": options}, ensure_ascii=False)},
            ],
        )
        content = response.choices[0].message.content or "{}"
        chosen_id = json.loads(content).get("queue_id")
        valid_ids = {q["id"] for q in queues}
        return chosen_id if chosen_id in valid_ids else fallback
    except Exception as e:
        print(f"[julia] Falha ao escolher fila de handoff, usando fallback: {e}")
        return fallback


def generate_free_error_message(agent_name: str) -> str:
    """Usada quando a Mensagem de erro está DESATIVADA na config do agente —
    "a IA pode gerar qualquer resposta" nesse cenário."""
    try:
        response = _get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.5,
            max_tokens=80,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Você é {agent_name}, assistente de atendimento via WhatsApp. "
                        "Aconteceu um erro interno ao processar a última mensagem do "
                        "cliente. Gere uma mensagem curta, cordial, em português, "
                        "pedindo desculpas e sugerindo tentar novamente em instantes."
                    ),
                },
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        return text or "Desculpe, tivemos um problema para responder agora. Tente novamente em instantes."
    except Exception as e:
        print(f"[julia] Fallback de mensagem de erro também falhou: {e}")
        return "Desculpe, tivemos um problema para responder agora. Tente novamente em instantes."


def sincronizar_metadados_contato(target_id: str, metadata: dict) -> None:
    """Envia o snapshot acumulado do que o agente aprendeu do contato nesta
    conversa (nome, cidade etc.) pro Agent-Api, pra persistir entre sessões e
    aparecer no Agent Console (Target.metadata) — mesmo padrão que o axel já
    usa. Best-effort: uma falha aqui não deve derrubar a conversa."""
    try:
        httpx.patch(
            f"{BASE_URL}/internal/targets/{target_id}/metadata",
            json={"metadata": metadata},
            headers={"x-internal-api-key": INTERNAL_API_KEY},
            timeout=10,
        )
    except Exception as e:
        print(f"[julia] Falha ao sincronizar metadados do contato {target_id}: {e}")


def update_rag_document_status(
    rag_document_id: str,
    status: str,
    chunk_count: int | None = None,
    error_message: str | None = None,
) -> None:
    """Avisa o Agent-Api que a ingestão de um documento de RAG terminou (READY)
    ou falhou (FAILED) — pra tela mostrar o status certo. Best-effort: uma
    falha aqui só vira log, a ingestão em si já rodou."""
    body: dict = {"status": status}
    if chunk_count is not None:
        body["chunkCount"] = chunk_count
    if error_message is not None:
        body["errorMessage"] = error_message

    try:
        httpx.patch(
            f"{BASE_URL}/internal/rag-documents/{rag_document_id}/status",
            json=body,
            headers={"x-internal-api-key": INTERNAL_API_KEY},
            timeout=10,
        )
    except Exception as e:
        print(f"[julia] Falha ao atualizar status do RagDocument {rag_document_id}: {e}")
