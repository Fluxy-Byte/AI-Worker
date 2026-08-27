"""Catálogo e disponibilidade da barbearia.

PLACEHOLDER da agenda real: enquanto o sistema de agendamento de verdade não
está plugado, serviços, profissionais, horário de funcionamento e ocupação
vivem aqui em memória, num formato parecido com o que uma API de agenda
devolveria. Quando a agenda real entrar, só as funções deste módulo mudam
(passam a bater na API/banco) — as tools de booking_tools.py e a instrução do
agente continuam iguais.
"""

import re
import unicodedata
from datetime import date, datetime, time, timedelta
from difflib import SequenceMatcher
from typing import Optional
from zoneinfo import ZoneInfo

TIMEZONE = ZoneInfo("America/Sao_Paulo")

# Grade de horários oferecida ao cliente (de 30 em 30 minutos).
PASSO_GRADE_MINUTOS = 30

# Quantos dias pra frente o cliente pode agendar.
JANELA_AGENDAMENTO_DIAS = 30

SERVICOS = [
    {"id": "corte", "nome": "Corte de cabelo", "duracao_min": 40, "preco": 45.0},
    {"id": "barba", "nome": "Barba", "duracao_min": 30, "preco": 35.0},
    {"id": "corte_barba", "nome": "Corte + Barba", "duracao_min": 70, "preco": 70.0},
    {"id": "pezinho", "nome": "Pezinho (acabamento)", "duracao_min": 20, "preco": 25.0},
    {"id": "sobrancelha", "nome": "Sobrancelha na navalha", "duracao_min": 15, "preco": 20.0},
    {"id": "platinado", "nome": "Platinado / descoloração", "duracao_min": 120, "preco": 180.0},
]

PROFISSIONAIS = [
    {"id": "ricardo", "nome": "Ricardo", "servicos": ["corte", "barba", "corte_barba", "pezinho", "sobrancelha", "platinado"]},
    {"id": "bruno", "nome": "Bruno", "servicos": ["corte", "barba", "corte_barba", "pezinho"]},
    {"id": "diego", "nome": "Diego", "servicos": ["corte", "corte_barba", "sobrancelha", "platinado"]},
]

# Funcionamento por dia da semana (0=segunda ... 6=domingo). Dia ausente = fechado.
EXPEDIENTE = {
    1: (time(9, 0), time(19, 0)),   # terça
    2: (time(9, 0), time(19, 0)),   # quarta
    3: (time(9, 0), time(19, 0)),   # quinta
    4: (time(9, 0), time(20, 0)),   # sexta
    5: (time(8, 0), time(17, 0)),   # sábado
}

DIAS_SEMANA = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]

# Ocupação da agenda — PLACEHOLDER. Chave: (profissional_id, data ISO);
# valor: lista de (início, fim) já comprometidos naquele dia.
# Existe só pra o fluxo de "esse horário já está ocupado" ter como acontecer
# num teste; quando a agenda real entrar, isto sai por inteiro.
HORARIOS_OCUPADOS: dict[tuple[str, str], list[tuple[time, time]]] = {}


def _normalizar(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")
    return sem_acento.lower().strip()


def hoje() -> date:
    return datetime.now(TIMEZONE).date()


def agora() -> datetime:
    return datetime.now(TIMEZONE)


def descrever_dia(data_obj: date) -> str:
    """'quinta-feira, 28/08' — como o agente se refere ao dia na conversa."""
    return f"{DIAS_SEMANA[data_obj.weekday()]}, {data_obj.strftime('%d/%m')}"


# Palavras que não ajudam a distinguir um serviço do outro ("corte E barba",
# "corte DE cabelo") e só atrapalham a comparação por palavra.
_IRRELEVANTES = {"de", "do", "da", "e", "com", "na", "no", "em", "a", "o", "um", "uma", "pra", "para"}


def _palavras(texto: str) -> set[str]:
    return {p for p in re.split(r"[^a-z0-9]+", _normalizar(texto)) if p and p not in _IRRELEVANTES}


def _parecidas(a: str, b: str) -> bool:
    """Tolera variação de flexão ('platinar'/'platinado', 'cortes'/'corte')."""
    if a == b:
        return True
    return SequenceMatcher(None, a, b).ratio() >= 0.8


def buscar_servico(texto: str) -> Optional[dict]:
    """Casa a resposta livre do cliente ('barba', 'corte e barba', 'platinar')
    com um serviço do catálogo. Retorna None se não der pra ter certeza.

    Compara por palavra e não por substring: 'corte e barba' precisa cair em
    'Corte + Barba', não em 'Barba' só porque a palavra aparece lá dentro.
    """
    alvo = _normalizar(texto)
    if not alvo:
        return None

    for servico in SERVICOS:
        if _normalizar(servico["nome"]) == alvo or servico["id"] == alvo:
            return servico

    palavras_cliente = _palavras(texto)
    melhor, melhor_nota = None, (0, 0.0)
    for servico in SERVICOS:
        palavras_servico = _palavras(servico["nome"])
        if not palavras_servico:
            continue
        acertos = sum(1 for p in palavras_servico if any(_parecidas(p, c) for c in palavras_cliente))
        if not acertos:
            continue
        # Mais palavras em comum vence; empate vai pra quem teve maior parte do
        # próprio nome coberta ('barba' -> "Barba", não "Corte + Barba").
        nota = (acertos, acertos / len(palavras_servico))
        if nota > melhor_nota:
            melhor, melhor_nota = servico, nota

    return melhor


def buscar_profissional(texto: str) -> Optional[dict]:
    alvo = _normalizar(texto)
    if not alvo:
        return None
    for profissional in PROFISSIONAIS:
        if _normalizar(profissional["nome"]) == alvo or profissional["id"] == alvo:
            return profissional
    for profissional in PROFISSIONAIS:
        if _normalizar(profissional["nome"]) in alvo:
            return profissional
    return None


def profissionais_do_servico(servico_id: Optional[str]) -> list[dict]:
    if not servico_id:
        return list(PROFISSIONAIS)
    return [p for p in PROFISSIONAIS if servico_id in p["servicos"]]


def expediente_do_dia(data_obj: date) -> Optional[tuple[time, time]]:
    return EXPEDIENTE.get(data_obj.weekday())


def _conflita(profissional_id: str, data_obj: date, inicio: time, fim: time) -> bool:
    ocupados = HORARIOS_OCUPADOS.get((profissional_id, data_obj.isoformat()), [])
    return any(inicio < fim_ocupado and fim > inicio_ocupado for inicio_ocupado, fim_ocupado in ocupados)


def _grade(data_obj: date, duracao_min: int) -> list[tuple[time, time]]:
    """Todos os encaixes possíveis do serviço dentro do expediente do dia."""
    faixa = expediente_do_dia(data_obj)
    if not faixa:
        return []

    abertura, fechamento = faixa
    cursor = datetime.combine(data_obj, abertura)
    limite = datetime.combine(data_obj, fechamento)
    duracao = timedelta(minutes=duracao_min)

    encaixes = []
    while cursor + duracao <= limite:
        encaixes.append((cursor.time(), (cursor + duracao).time()))
        cursor += timedelta(minutes=PASSO_GRADE_MINUTOS)
    return encaixes


def horarios_disponiveis(data_obj: date, servico_id: str, profissional_id: Optional[str] = None) -> list[str]:
    """Horários livres ("HH:MM") para o serviço no dia. Sem profissional
    definido, considera livre o horário em que QUALQUER profissional que faça
    o serviço esteja disponível."""
    servico = next((s for s in SERVICOS if s["id"] == servico_id), None)
    if not servico:
        return []

    if profissional_id:
        candidatos = [p for p in PROFISSIONAIS if p["id"] == profissional_id]
    else:
        candidatos = profissionais_do_servico(servico_id)
    if not candidatos:
        return []

    momento = agora()
    livres = []
    for inicio, fim in _grade(data_obj, servico["duracao_min"]):
        # Nunca oferecer horário que já passou no dia de hoje.
        if datetime.combine(data_obj, inicio, tzinfo=TIMEZONE) <= momento:
            continue
        if any(not _conflita(p["id"], data_obj, inicio, fim) for p in candidatos):
            livres.append(inicio.strftime("%H:%M"))
    return livres


def profissionais_disponiveis(data_obj: date, horario_obj: time, servico_id: str) -> list[dict]:
    """Quem faz esse serviço e está livre exatamente nesse horário."""
    servico = next((s for s in SERVICOS if s["id"] == servico_id), None)
    if not servico:
        return []

    fim = (datetime.combine(data_obj, horario_obj) + timedelta(minutes=servico["duracao_min"])).time()
    return [
        p for p in profissionais_do_servico(servico_id)
        if not _conflita(p["id"], data_obj, horario_obj, fim)
    ]


def reservar(profissional_id: str, data_obj: date, horario_obj: time, servico_id: str) -> None:
    """Marca o horário como ocupado.

    PLACEHOLDER: só bloqueia em memória, some quando o worker reinicia. É aqui
    que entra a escrita na agenda real (API/banco) na próxima etapa.
    """
    servico = next((s for s in SERVICOS if s["id"] == servico_id), None)
    if not servico:
        return
    fim = (datetime.combine(data_obj, horario_obj) + timedelta(minutes=servico["duracao_min"])).time()
    HORARIOS_OCUPADOS.setdefault((profissional_id, data_obj.isoformat()), []).append((horario_obj, fim))
