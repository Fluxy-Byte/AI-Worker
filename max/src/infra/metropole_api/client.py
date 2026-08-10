import os

import httpx

BASE_URL = os.getenv("METROPOLE_API_BASE_URL", "https://metropoleudi.egnehl.easypanel.host")
API_KEY = os.getenv("METROPOLE_AXEL_API_KEY")


def _auth_headers() -> dict:
    return {"Authorization": f"Bearer {API_KEY}"}


def listar_categorias() -> list[dict]:
    """Categorias de imóvel cadastradas na Metrópole (ex: casa, apartamento,
    cobertura...) — usada pra mapear a resposta livre do cliente ("casa ou
    apartamento?") pro categorySlug real esperado por buscar_imoveis."""
    response = httpx.get(f"{BASE_URL}/api/categories", timeout=15)
    response.raise_for_status()
    return response.json().get("items", [])


def listar_bairros(cidade: str | None = "Uberlândia") -> list[str]:
    """Bairros com pelo menos um imóvel publicado disponível, na cidade informada."""
    params = {"city": cidade} if cidade else {}
    response = httpx.get(f"{BASE_URL}/api/houses/neighborhoods", params=params, timeout=15)
    response.raise_for_status()
    return response.json().get("items", [])


def buscar_imoveis(
    neighborhood: str | None = None,
    category_slugs: list[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    bedrooms: int | None = None,
    listing_type: str | None = None,
    page_size: int = 20,
) -> list[dict]:
    """Lista imóveis publicados e disponíveis (endpoint público do site) já
    filtrados pelo que for informado. Retorna HouseListItemDto (sem descrição
    completa nem galeria — use detalhar_imovel pros imóveis que forem
    efetivamente apresentados ao cliente)."""
    params: dict = {"page": 1, "pageSize": page_size}
    if neighborhood:
        params["neighborhood"] = neighborhood
    if category_slugs:
        params["categorySlugs"] = ",".join(category_slugs)
    if min_price is not None:
        params["minPrice"] = min_price
    if max_price is not None:
        params["maxPrice"] = max_price
    if bedrooms is not None:
        params["bedrooms"] = bedrooms
    if listing_type:
        params["listingType"] = listing_type

    response = httpx.get(f"{BASE_URL}/api/houses", params=params, timeout=15)
    response.raise_for_status()
    return response.json().get("items", [])


def detalhar_imovel(slug: str) -> dict | None:
    """Detalhe completo de um imóvel (descrição real, condomínio, IPTU, tags e
    galeria de fotos) — chame pra cada imóvel que for efetivamente apresentado
    ao cliente, nunca invente/complete o que faltar."""
    response = httpx.get(f"{BASE_URL}/api/houses/{slug}", timeout=15)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("house")


def atualizar_metadados(phone: str, name: str | None, metadata: dict) -> dict:
    """Grava/atualiza o perfil do lead (Client + Metadata) na Metrópole —
    campos de 1ª classe (desiredPropertyType, desiredNeighborhood,
    observations, funnelStage) ou dentro de 'preferences' (json livre, ex:
    finalidade e faixa de valor)."""
    body: dict = {"phone": phone, **metadata}
    if name:
        body["name"] = name
    response = httpx.post(
        f"{BASE_URL}/api/whatsapp/metadata",
        json=body,
        headers=_auth_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("metadata", {})


def registrar_interesse(phone: str, name: str | None, house_id: str, notes: str | None = None) -> dict:
    """Registra o interesse do lead num imóvel específico (source=WHATSAPP)."""
    body: dict = {"phone": phone, "houseId": house_id}
    if name:
        body["name"] = name
    if notes:
        body["notes"] = notes
    response = httpx.post(
        f"{BASE_URL}/api/whatsapp/interest",
        json=body,
        headers=_auth_headers(),
        timeout=15,
    )
    response.raise_for_status()
    return response.json().get("interest", {})


def buscar_historico(phone: str) -> dict | None:
    """Histórico já conhecido do lead (perfil, interesses, atividades) — usado
    pra não repetir perguntas cuja resposta já temos de uma conversa anterior."""
    response = httpx.get(
        f"{BASE_URL}/api/whatsapp/history",
        params={"phone": phone},
        headers=_auth_headers(),
        timeout=15,
    )
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json().get("history")
