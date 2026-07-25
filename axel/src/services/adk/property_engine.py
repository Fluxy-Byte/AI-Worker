import json
import os
from pathlib import Path
from typing import Optional

IMOVEIS_PATH = Path(__file__).resolve().parents[2] / "services" / "imoveis.json"

# Configurável no backend (spec item 11) — quanto acima do orçamento máximo informado
# ainda vale mostrar um imóvel como "possivelmente compatível".
TOLERANCIA_ORCAMENTO_PCT = float(os.getenv("TOLERANCIA_ORCAMENTO_PCT", "0.05"))


def _carregar_imoveis() -> list[dict]:
    with open(IMOVEIS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _classificar(valor: float, orcamento_maximo: Optional[float]) -> str:
    if not orcamento_maximo:
        return "INFORMACOES_INSUFICIENTES"

    limite_tolerancia = orcamento_maximo * (1 + TOLERANCIA_ORCAMENTO_PCT)

    if valor <= orcamento_maximo:
        return "COMPATIVEL"
    if valor <= limite_tolerancia:
        return "POSSIVELMENTE_COMPATIVEL"
    return "ACIMA_DO_ORCAMENTO"


def _score(imovel: dict, perfil_imovel: dict, perfil_financeiro: dict) -> float:
    pontos = 0.0
    peso_total = 0.0

    # Obrigatórios
    orcamento_maximo = perfil_financeiro.get("orcamento_maximo")
    if orcamento_maximo:
        peso_total += 40
        if imovel["valor"] <= orcamento_maximo:
            pontos += 40
        elif imovel["valor"] <= orcamento_maximo * (1 + TOLERANCIA_ORCAMENTO_PCT):
            pontos += 25

    tipo = perfil_imovel.get("tipo")
    if tipo:
        peso_total += 20
        if imovel["tipo"] == tipo:
            pontos += 20

    cidade = perfil_imovel.get("cidade")
    if cidade:
        peso_total += 15
        if imovel["cidade"].lower() == cidade.lower():
            pontos += 15

    # Importantes
    bairros = perfil_imovel.get("bairros") or []
    if bairros:
        peso_total += 10
        if imovel["bairro"] in bairros:
            pontos += 10

    quartos_minimos = perfil_imovel.get("quartos_minimos")
    if quartos_minimos:
        peso_total += 8
        if imovel["quartos"] >= quartos_minimos:
            pontos += 8

    vagas_minimas = perfil_imovel.get("vagas_minimas")
    if vagas_minimas:
        peso_total += 7
        if imovel["vagas_garagem"] >= vagas_minimas:
            pontos += 7

    # Desejáveis
    caracteristicas_desejadas = [c.lower() for c in (perfil_imovel.get("caracteristicas") or [])]
    if caracteristicas_desejadas:
        peso_total += 10
        caracteristicas_imovel = [c.lower() for c in imovel.get("caracteristicas", [])]
        atendidas = sum(
            1 for desejada in caracteristicas_desejadas
            if any(desejada in disponivel for disponivel in caracteristicas_imovel)
        )
        pontos += 10 * (atendidas / len(caracteristicas_desejadas))

    if peso_total == 0:
        return 0.0

    return round((pontos / peso_total) * 100, 1)


def buscar_e_selecionar(perfil_imovel: dict, perfil_financeiro: dict) -> list[dict]:
    """Filtra, pontua, classifica e seleciona até 3 imóveis compatíveis. Nunca retorna mais
    que 3 — busca diversidade (melhor compatibilidade, melhor custo-benefício, alternativa),
    não simplesmente os 3 mais baratos."""
    imoveis = [i for i in _carregar_imoveis() if i.get("status") == "disponivel"]

    orcamento_maximo = perfil_financeiro.get("orcamento_maximo")
    tolerancia_sanidade = 1 + TOLERANCIA_ORCAMENTO_PCT + 0.10  # corte final, nunca mostra algo muito acima

    candidatos = []
    for imovel in imoveis:
        if perfil_imovel.get("tipo") and imovel["tipo"] != perfil_imovel["tipo"]:
            continue
        if perfil_imovel.get("cidade") and imovel["cidade"].lower() != perfil_imovel["cidade"].lower():
            continue
        if orcamento_maximo and imovel["valor"] > orcamento_maximo * tolerancia_sanidade:
            continue
        candidatos.append(imovel)

    ranqueados = [
        {**imovel, "compatibilidade": _score(imovel, perfil_imovel, perfil_financeiro),
         "qualificacao": _classificar(imovel["valor"], orcamento_maximo)}
        for imovel in candidatos
    ]
    ranqueados.sort(key=lambda i: i["compatibilidade"], reverse=True)

    if not ranqueados:
        return []

    selecionados = [ranqueados[0]]  # Opção 1: melhor compatibilidade
    restantes = ranqueados[1:]

    # Opção 2: melhor custo-benefício (menor valor entre os que ainda têm score razoável)
    custo_beneficio = sorted(
        (r for r in restantes if r["compatibilidade"] >= 50),
        key=lambda i: i["valor"],
    )
    if custo_beneficio:
        escolhido = custo_beneficio[0]
        selecionados.append(escolhido)
        restantes = [r for r in restantes if r["id"] != escolhido["id"]]

    # Opção 3: alternativa (próximo melhor score, diversidade de bairro/tipo quando possível)
    if restantes:
        selecionados.append(restantes[0])

    return selecionados[:3]
