import os

import httpx

# API interna do fluxy-gestao-be (produto de gestão de OS, distinto do
# Agent-Api que hospeda a configuração deste agente) — exposta só em
# /api/internal/assistant, protegida por x-internal-api-key. Ver
# fluxy-gestao-be/src/presentation/routes/assistant.routes.ts.
BASE_URL = os.getenv("FLUXY_GESTAO_API_BASE_URL", "http://localhost:6501")
INTERNAL_API_KEY = os.getenv("FLUXY_GESTAO_INTERNAL_API_KEY")

_HEADERS = {"x-internal-api-key": INTERNAL_API_KEY or ""}


def _get(path: str, params: dict | None = None):
    """GET simples contra /api/internal/assistant — sem envelope {result: ...}
    (diferente do Agent-Api): o fluxy-gestao-be devolve o JSON puro em todo
    endpoint desse controller."""
    response = httpx.get(
        f"{BASE_URL}/api/internal/assistant{path}",
        params=params,
        headers=_HEADERS,
        timeout=10,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()


def find_user_by_phone(phone: str) -> dict | None:
    """Resolve qual conta Fluxy Gestão é dona deste número de WhatsApp — é a
    ÚNICA chave usada para autorizar acesso a clientes/OS/serviços de uma
    conta (nunca um id informado pelo próprio contato)."""
    return _get("/users/by-phone", params={"phone": phone})


def list_clients(user_id: str) -> list[dict]:
    return _get(f"/users/{user_id}/clients/all") or []


def search_clients(user_id: str, name: str) -> list[dict]:
    return _get(f"/users/{user_id}/clients", params={"name": name}) or []


def list_orders_by_client(user_id: str, client_id: str) -> list[dict]:
    return _get(f"/users/{user_id}/clients/{client_id}/orders") or []


def get_client_catalog_link(user_id: str, client_id: str) -> str | None:
    result = _get(f"/users/{user_id}/clients/{client_id}/link")
    return (result or {}).get("url")


def list_services(user_id: str) -> list[dict]:
    return _get(f"/users/{user_id}/services") or []


def get_order_by_number(user_id: str, number_order: int) -> dict | None:
    return _get(f"/users/{user_id}/orders/{number_order}")


def get_dashboard(user_id: str) -> dict:
    return _get(f"/users/{user_id}/dashboard") or {}


def get_report(user_id: str, start: str, end: str, status: str | None = None) -> dict:
    params = {"start": start, "end": end}
    if status:
        params["status"] = status
    return _get(f"/users/{user_id}/report", params=params) or {}
