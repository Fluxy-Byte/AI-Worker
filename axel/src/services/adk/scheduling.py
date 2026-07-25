import os
from datetime import date, datetime, time
from typing import Optional

import asyncpg

# Segunda a sexta: 08h-19h. Sábado: 08h-14h. Domingo: indisponível (spec item 18).
HORARIOS_PERMITIDOS = {
    0: (time(8, 0), time(19, 0)),
    1: (time(8, 0), time(19, 0)),
    2: (time(8, 0), time(19, 0)),
    3: (time(8, 0), time(19, 0)),
    4: (time(8, 0), time(19, 0)),
    5: (time(8, 0), time(14, 0)),
}


def _validar_horario_comercial(data_obj: date, horario_obj: time) -> Optional[str]:
    faixa = HORARIOS_PERMITIDOS.get(data_obj.weekday())
    if faixa is None:
        return "Não realizamos agendamentos aos domingos."

    inicio, fim = faixa
    if not (inicio <= horario_obj <= fim):
        return f"Nesse dia os horários disponíveis são das {inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')}."

    return None


def _db_url() -> str:
    # asyncpg puro (sem SQLAlchemy) — reaproveita a mesma URL_ADK_SESSIONS, só troca o
    # dialect prefix que é específico do SQLAlchemy.
    url = os.getenv("URL_ADK_SESSIONS", "")
    return url.replace("postgresql+asyncpg://", "postgresql://")


async def _garantir_tabela(conn: asyncpg.Connection) -> None:
    await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS axel_agendamentos (
            id SERIAL PRIMARY KEY,
            contact_id TEXT NOT NULL,
            imovel_id TEXT,
            tipo_encontro TEXT NOT NULL,
            data DATE NOT NULL,
            horario TIME NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


async def tentar_agendar(
    contact_id: str,
    data: str,
    horario: str,
    tipo_encontro: str,
    imovel_id: Optional[str],
) -> dict:
    """Valida horário comercial, checa conflito na agenda real e, se tudo ok, confirma o
    agendamento (persistido no Postgres). Nunca confirma sem essa validação."""
    try:
        data_obj = date.fromisoformat(data)
        horario_obj = datetime.strptime(horario, "%H:%M").time()
    except ValueError:
        return {"confirmado": False, "motivo": "Data ou horário em formato inválido."}

    motivo_invalido = _validar_horario_comercial(data_obj, horario_obj)
    if motivo_invalido:
        return {"confirmado": False, "motivo": motivo_invalido}

    conn = await asyncpg.connect(_db_url())
    try:
        await _garantir_tabela(conn)

        conflito = await conn.fetchrow(
            "SELECT id FROM axel_agendamentos WHERE data = $1 AND horario = $2",
            data_obj, horario_obj,
        )
        if conflito:
            return {"confirmado": False, "motivo": "Esse horário já está reservado. Escolha outro horário próximo."}

        await conn.execute(
            """
            INSERT INTO axel_agendamentos (contact_id, imovel_id, tipo_encontro, data, horario)
            VALUES ($1, $2, $3, $4, $5)
            """,
            contact_id, imovel_id, tipo_encontro, data_obj, horario_obj,
        )

        return {
            "confirmado": True,
            "data": data,
            "horario": horario,
            "tipo_encontro": tipo_encontro,
            "imovel_id": imovel_id,
        }
    finally:
        await conn.close()
