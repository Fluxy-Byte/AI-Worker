import os

import httpx

BASE_URL = os.getenv("AGENT_API_BASE_URL", "http://localhost:7073")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY")


def sincronizar_metadados_contato(target_id: str, metadata: dict) -> None:
    """Envia o snapshot acumulado do lead (nome, perfil_imovel, perfil_financeiro,
    recomendacoes, imoveis_interesse, agendamento) pro Agent-Api, pra aparecer na
    interface do Agent Console (Target.metadata). Best-effort: uma falha aqui não deve
    derrubar a conversa com o cliente."""
    try:
        httpx.patch(
            f"{BASE_URL}/internal/targets/{target_id}/metadata",
            json={"metadata": metadata},
            headers={"x-internal-api-key": INTERNAL_API_KEY},
            timeout=10,
        )
    except Exception as e:
        print(f"[axel] Falha ao sincronizar metadados do contato {target_id}: {e}")
