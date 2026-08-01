import re
import traceback

from src.infra.fluxy_api.client import find_user_by_phone


def _normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone or "")


class ContaFluxy:
    """Resultado da resolução de conta por telefone — a chave de acesso a
    clientes/OS/serviços nesta conversa."""

    def __init__(
        self,
        phone: str | None,
        autorizado: bool,
        user_id: str | None = None,
        company_name: str | None = None,
        plan: str | None = None,
    ):
        self.phone = phone
        self.autorizado = autorizado
        self.user_id = user_id
        self.company_name = company_name
        self.plan = plan

    @property
    def telefone_ausente(self) -> bool:
        return not self.phone


def resolver_conta(target_info: dict) -> ContaFluxy:
    """Resolve a conta Fluxy Gestão dona da conversa a partir do telefone do
    contato — requisito de isolamento: cada contato só pode ver os próprios
    dados, e o telefone é a única chave usada pra isso.

    Prioridade do telefone: o wa_id entregue pela Meta (identidade real do
    canal, quase sempre presente) e, na ausência dele, o telefone que o
    próprio contato já informou numa conversa anterior (persistido em
    metadata.telefone pela tool registrar_telefone_contato) — cobre o caso
    raro em que a Meta não entrega o telefone do contato."""
    metadata = target_info.get("metadata") or {}
    phone_bruto = target_info.get("waId") or metadata.get("telefone")
    phone = _normalize_phone(phone_bruto) if phone_bruto else None

    if not phone:
        return ContaFluxy(phone=None, autorizado=False)

    try:
        user = find_user_by_phone(phone)
    except Exception as e:
        # Best-effort: uma falha ao consultar o fluxy-gestao-be não pode
        # derrubar a conversa inteira — degrada pra "sem conta encontrada"
        # (só perguntas gerais sobre a plataforma) em vez de erro.
        print(f"[fly] Falha ao resolver conta pelo telefone {phone}: {e}")
        print(traceback.format_exc())
        return ContaFluxy(phone=phone, autorizado=False)

    if not user:
        return ContaFluxy(phone=phone, autorizado=False)

    return ContaFluxy(
        phone=phone,
        autorizado=True,
        user_id=user.get("id"),
        company_name=user.get("companyName") or user.get("name"),
        plan=user.get("plan"),
    )
