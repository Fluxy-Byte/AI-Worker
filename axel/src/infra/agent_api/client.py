import json
import os

import httpx
from openai import OpenAI

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:7073")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")

# Cacheado por api_key (não um singleton fixo) — cada instância deste worker
# atende só um agente, então normalmente há só 1 entrada, mas cachear por key
# evita reconstruir o client à toa e permite que o token venha do payload de
# cada mensagem (Agent Console, criptografado no banco) em vez de fixo no env.
_openai_clients: dict[str | None, OpenAI] = {}


def _get_openai_client(api_key: str | None = None) -> OpenAI:
    key = api_key or os.getenv("OPENAI_API_KEY")
    if key not in _openai_clients:
        _openai_clients[key] = OpenAI(api_key=key)
    return _openai_clients[key]


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
    queues: list[dict], reason: str, default_queue_id: str | None, openai_api_key: str | None = None
) -> str | None:
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
        response = _get_openai_client(openai_api_key).chat.completions.create(
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
        print(f"[axel] Falha ao escolher fila de handoff, usando fallback: {e}")
        return fallback


def generate_free_error_message(agent_name: str, openai_api_key: str | None = None) -> str:
    """Usada quando a Mensagem de erro está DESATIVADA na config do agente —
    "a IA pode gerar qualquer resposta" nesse cenário."""
    try:
        response = _get_openai_client(openai_api_key).chat.completions.create(
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
        print(f"[axel] Fallback de mensagem de erro também falhou: {e}")
        return "Desculpe, tivemos um problema para responder agora. Tente novamente em instantes."
