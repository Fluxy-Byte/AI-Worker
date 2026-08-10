import unicodedata
from typing import Literal, Optional

from google.adk.tools import ToolContext

from src.infra.metropole_api import client as metropole_api

# Sem bairro escolhido: só os 3 mais aderentes ao perfil (regra do pedido —
# "apresente 3 imóveis que se encaixa"). Com bairro escolhido: todos os
# disponíveis nele, até este teto (só pra não estourar o WhatsApp de fotos).
MAX_RESULTADOS_SEM_BAIRRO = 3
MAX_RESULTADOS_COM_BAIRRO = 5

# Quanto acima do valor máximo informado ainda vale mostrar um imóvel como
# "possivelmente compatível" em vez de descartar de cara.
TOLERANCIA_ORCAMENTO_PCT = 0.10


def _normalizar(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return sem_acento.lower().strip()


def _resolver_categoria_slug(tipo_texto: str) -> Optional[str]:
    """Casa a resposta livre do cliente ('apartamento', 'casas', 'cobertura'
    duplex'...) com o categorySlug real cadastrado na Metrópole — nunca
    assume um slug fixo, porque as categorias são administráveis lá."""
    tipo_normalizado = _normalizar(tipo_texto)
    try:
        categorias = metropole_api.listar_categorias()
    except Exception as e:
        print(f"[max] Falha ao listar categorias da Metrópole: {e}")
        return None

    for categoria in categorias:
        if _normalizar(categoria.get("name", "")) == tipo_normalizado:
            return categoria.get("slug")
    for categoria in categorias:
        nome_normalizado = _normalizar(categoria.get("name", ""))
        if nome_normalizado and (tipo_normalizado in nome_normalizado or nome_normalizado in tipo_normalizado):
            return categoria.get("slug")
    return None


def _score(imovel: dict, perfil: dict) -> float:
    pontos = 0.0
    peso_total = 0.0

    valor_maximo = perfil.get("valor_maximo")
    if valor_maximo:
        peso_total += 50
        if imovel["price"] <= valor_maximo:
            pontos += 50
        elif imovel["price"] <= valor_maximo * (1 + TOLERANCIA_ORCAMENTO_PCT):
            pontos += 25

    valor_minimo = perfil.get("valor_minimo")
    if valor_minimo:
        peso_total += 10
        if imovel["price"] >= valor_minimo:
            pontos += 10

    tipo_slug = perfil.get("tipo_slug")
    if tipo_slug:
        peso_total += 30
        if (imovel.get("category") or {}).get("slug") == tipo_slug:
            pontos += 30

    bairro = perfil.get("bairro_escolhido")
    if bairro:
        peso_total += 10
        if _normalizar(imovel.get("neighborhood", "")) == _normalizar(bairro):
            pontos += 10

    if peso_total == 0:
        return 0.0
    return round((pontos / peso_total) * 100, 1)


def _selecionar(imoveis: list[dict], perfil: dict, limite: int) -> list[dict]:
    """Ranqueia por compatibilidade e escolhe com diversidade (melhor
    compatibilidade, melhor custo-benefício, alternativa) em vez de só pegar
    os N primeiros do ranking — mesma regra do protótipo do axel."""
    ranqueados = sorted(
        ({**i, "compatibilidade": _score(i, perfil)} for i in imoveis),
        key=lambda i: i["compatibilidade"],
        reverse=True,
    )
    if not ranqueados or limite <= 1:
        return ranqueados[:limite]

    selecionados = [ranqueados[0]]
    restantes = [i for i in ranqueados[1:] if i["id"] != ranqueados[0]["id"]]

    custo_beneficio = sorted(
        (r for r in restantes if r["compatibilidade"] >= 50),
        key=lambda i: i["price"],
    )
    if custo_beneficio:
        escolhido = custo_beneficio[0]
        selecionados.append(escolhido)
        restantes = [r for r in restantes if r["id"] != escolhido["id"]]

    for imovel in restantes:
        if len(selecionados) >= limite:
            break
        selecionados.append(imovel)

    return selecionados[:limite]


def _formatar_imovel(imovel_lista: dict) -> dict:
    """Busca o detalhe real (descrição, condomínio, IPTU, tags, fotos) — a
    listagem sozinha não tem isso, e a regra é nunca inventar/completar o que
    faltar."""
    try:
        detalhe = metropole_api.detalhar_imovel(imovel_lista["slug"]) or {}
    except Exception as e:
        print(f"[max] Falha ao detalhar imóvel {imovel_lista.get('slug')}: {e}")
        detalhe = {}

    return {
        "id": imovel_lista["id"],
        "titulo": imovel_lista["title"],
        "tipo": (imovel_lista.get("category") or {}).get("name"),
        "finalidade_anuncio": "aluguel" if imovel_lista.get("listingType") == "RENT" else "venda",
        "valor": imovel_lista["price"],
        "condominio": detalhe.get("condoFee"),
        "iptu_anual": detalhe.get("iptu"),
        "area_construida_m2": imovel_lista.get("builtArea"),
        "area_total_m2": imovel_lista.get("totalArea"),
        "quartos": imovel_lista.get("bedrooms"),
        "banheiros": imovel_lista.get("bathrooms"),
        "vagas_garagem": imovel_lista.get("garageSpaces"),
        "piscina": imovel_lista.get("hasPool"),
        "churrasqueira": detalhe.get("hasBarbecue"),
        "bairro": imovel_lista["neighborhood"],
        "cidade": imovel_lista["city"],
        "caracteristicas": detalhe.get("tags", []),
        "descricao_completa": detalhe.get("description", ""),
        "imagem_url": imovel_lista.get("coverImageUrl"),
        "compatibilidade": imovel_lista.get("compatibilidade", 0.0),
    }


def carregar_historico(phone: str) -> Optional[dict]:
    """Usado só na montagem da instrução (fora de uma tool do ADK) — perfil e
    interesses já conhecidos deste lead de uma conversa anterior, pra não
    repetir pergunta cuja resposta já temos."""
    try:
        return metropole_api.buscar_historico(phone)
    except Exception as e:
        print(f"[max] Falha ao buscar histórico da Metrópole para {phone}: {e}")
        return None


def build_property_tools(phone: str, name: Optional[str]) -> list:
    """Monta as tools de imóveis como closures (capturando phone/name do
    contato) — mesmo padrão do _build_rag_tool no agent.py genérico, porque o
    telefone real do lead (waId) é quem identifica o Client na Metrópole, e só
    está disponível no target_info de cada mensagem, não dá pra fixar num
    tools.py estático."""

    def atualizar_perfil_imovel(
        tool_context: ToolContext,
        finalidade: Optional[Literal["moradia", "investimento"]] = None,
        tipo: Optional[str] = None,
        valor_minimo: Optional[float] = None,
        valor_maximo: Optional[float] = None,
        bairro_escolhido: Optional[str] = None,
    ) -> dict:
        """Registra/atualiza o que o cliente já informou sobre o que procura —
        chame a cada novo detalhe aprendido, não precisa esperar ter tudo.
        'tipo' é a resposta livre do cliente (ex: 'apartamento'); é resolvido
        automaticamente pro categorySlug real da Metrópole."""
        atual = dict(tool_context.state.get("perfil", {}))
        novos_valores = {
            "finalidade": finalidade,
            "valor_minimo": valor_minimo,
            "valor_maximo": valor_maximo,
            "bairro_escolhido": bairro_escolhido,
        }
        if tipo:
            novos_valores["tipo"] = tipo
            novos_valores["tipo_slug"] = _resolver_categoria_slug(tipo)
        atual.update({k: v for k, v in novos_valores.items() if v is not None})
        tool_context.state["perfil"] = atual
        return atual

    def listar_bairros_disponiveis(tool_context: ToolContext) -> dict:
        """Lista os bairros com imóveis disponíveis que já batem com o perfil
        coletado até agora (tipo e/ou faixa de valor, se já informados).
        Chame ANTES de perguntar a preferência de bairro ao cliente — a regra
        é sempre mostrar os bairros reais com estoque disponível, nunca
        perguntar "qual bairro" no vácuo."""
        perfil = tool_context.state.get("perfil", {})
        imoveis = metropole_api.buscar_imoveis(
            category_slugs=[perfil["tipo_slug"]] if perfil.get("tipo_slug") else None,
            min_price=perfil.get("valor_minimo"),
            max_price=perfil.get("valor_maximo"),
            page_size=100,
        )
        bairros = sorted({i["neighborhood"] for i in imoveis if i.get("neighborhood")})
        tool_context.state["bairros_apresentados"] = bairros
        if not bairros:
            return {"bairros": [], "aviso": "Nenhum imóvel disponível encontrado com o perfil informado até agora."}
        return {"bairros": bairros}

    def buscar_imoveis_compativeis(tool_context: ToolContext) -> dict:
        """Busca imóveis reais compatíveis com o perfil coletado. Se o
        cliente já escolheu um bairro (perfil.bairro_escolhido), filtra e
        mostra os disponíveis nele (até 5). Sem bairro escolhido, mostra os 3
        mais aderentes ao perfil. NUNCA invente imóveis, preços,
        características ou disponibilidade — use exclusivamente o retorno
        desta ferramenta. Cada imóvel já vem com 'compatibilidade' (0-100) —
        nunca exponha esse número ao cliente, use só pra explicar o motivo da
        recomendação."""
        perfil = tool_context.state.get("perfil", {})
        bairro = perfil.get("bairro_escolhido")

        imoveis = metropole_api.buscar_imoveis(
            neighborhood=bairro,
            category_slugs=[perfil["tipo_slug"]] if perfil.get("tipo_slug") else None,
            min_price=perfil.get("valor_minimo"),
            max_price=perfil.get("valor_maximo"),
            page_size=100,
        )

        limite = MAX_RESULTADOS_COM_BAIRRO if bairro else MAX_RESULTADOS_SEM_BAIRRO
        selecionados = _selecionar(imoveis, perfil, limite)

        tool_context.state["imoveis_apresentados"] = list(set(
            tool_context.state.get("imoveis_apresentados", []) + [i["id"] for i in selecionados]
        ))

        if not selecionados:
            return {"imoveis": [], "aviso": "Nenhum imóvel disponível compatível com o perfil informado até agora."}

        resultado = {"imoveis": [_formatar_imovel(i) for i in selecionados]}
        if bairro and len(imoveis) > limite:
            resultado["aviso"] = f"Há mais {len(imoveis) - limite} imóvel(is) disponível(is) nesse bairro além dos mostrados."
        return resultado

    def registrar_interesse_imovel(tool_context: ToolContext, imovel_id: str, imovel_titulo: str) -> dict:
        """Chame assim que o cliente demonstrar interesse claro em um imóvel
        já apresentado (o 'imovel_id' vem do campo 'id' de
        buscar_imoveis_compativeis). Depois de chamar isso, encaminhe SEMPRE
        para atendimento humano (solicitar_atendimento_humano) — só o
        consultor humano fecha negócio."""
        try:
            metropole_api.registrar_interesse(phone, name, imovel_id, notes=imovel_titulo)
        except Exception as e:
            print(f"[max] Falha ao registrar interesse do lead {phone} no imóvel {imovel_id}: {e}")

        existentes = set(tool_context.state.get("imoveis_interesse", []))
        existentes.add(imovel_id)
        tool_context.state["imoveis_interesse"] = sorted(existentes)
        return {"imoveis_interesse": sorted(existentes)}

    return [
        atualizar_perfil_imovel,
        listar_bairros_disponiveis,
        buscar_imoveis_compativeis,
        registrar_interesse_imovel,
    ]
