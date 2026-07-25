import json
import os

import httpx
from openai import OpenAI

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:7073")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

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


def choose_handoff_queue(queues: list[dict], reason: str, default_queue_id: str | None) -> str | None:
    """Decide para qual fila da ilha o ticket de handoff deve ir, dado o motivo
    do transbordo. Cai para a fila padrão do agente (ou a primeira disponível)
    se não conseguir decidir com segurança."""
    if not queues:
        return default_queue_id
    if len(queues) == 1:
        return queues[0]["id"]

    fallback = default_queue_id or queues[0]["id"]

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
        print(f"[atlas] Falha ao escolher fila de handoff, usando fallback: {e}")
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
        print(f"[atlas] Fallback de mensagem de erro também falhou: {e}")
        return "Desculpe, tivemos um problema para responder agora. Tente novamente em instantes."
