from google.adk.tools import ToolContext

from src.infra.fluxy_api import client as fluxy_api


def build_data_tools(user_id: str) -> list:
    """Monta as tools de consulta (somente leitura) de clientes/OS/serviços,
    todas fechadas sobre o user_id JÁ AUTORIZADO pelo telefone do contato
    (ver fluxy_auth.resolver_conta) — o modelo nunca escolhe/recebe esse id,
    então não tem como um contato consultar dados de outra conta."""

    def buscar_cliente_por_nome(tool_context: ToolContext, nome: str) -> dict:
        """Busca clientes desta conta pelo nome (ou parte dele) — use para
        achar o client_id antes de consultar as OS de um cliente específico
        ou gerar o link do catálogo dele."""
        return {"clientes": fluxy_api.search_clients(user_id, nome)}

    def listar_clientes(tool_context: ToolContext) -> dict:
        """Lista todos os clientes ativos cadastrados nesta conta."""
        return {"clientes": fluxy_api.list_clients(user_id)}

    def listar_servicos(tool_context: ToolContext) -> dict:
        """Lista o catálogo de serviços cadastrados nesta conta: nome,
        categoria, preço de custo/venda, se aparece na criação de OS (active)
        e se aparece no catálogo público do cliente (showInCatalog)."""
        return {"servicos": fluxy_api.list_services(user_id)}

    def consultar_os_do_cliente(tool_context: ToolContext, client_id: str) -> dict:
        """Lista as ordens de serviço de um cliente específico desta conta.
        Peça o client_id retornado por buscar_cliente_por_nome ou
        listar_clientes antes de chamar esta tool."""
        return {"ordens": fluxy_api.list_orders_by_client(user_id, client_id)}

    def consultar_os_por_numero(tool_context: ToolContext, numero_os: int) -> dict:
        """Busca uma ordem de serviço específica desta conta pelo número
        dela (o número que aparece no sistema, ex: OS 42)."""
        ordem = fluxy_api.get_order_by_number(user_id, numero_os)
        if not ordem:
            return {"encontrada": False}
        return {"encontrada": True, "ordem": ordem}

    def resumo_do_dia(tool_context: ToolContext) -> dict:
        """Resumo das OS de hoje desta conta: quantidade de OS, faturamento,
        custo e margem bruta do dia — use para 'como estou hoje',
        'faturei quanto hoje' etc."""
        return fluxy_api.get_dashboard(user_id)

    def gerar_relatorio_periodo(
        tool_context: ToolContext,
        data_inicio: str,
        data_fim: str,
        status: str | None = None,
    ) -> dict:
        """Relatório consolidado das OS desta conta num período (datas no
        formato AAAA-MM-DD). status é opcional: PENDING, COMPLETED ou
        CANCELED, para filtrar só um tipo. Traz total de OS por status,
        faturamento, custo, margem, valor a receber e os serviços mais
        vendidos no período — use sempre que o cliente pedir um 'relatório',
        'resumo do mês/semana' ou similar."""
        return fluxy_api.get_report(user_id, data_inicio, data_fim, status)

    def link_catalogo_cliente(tool_context: ToolContext, client_id: str) -> dict:
        """Gera o link do catálogo público de um cliente desta conta — a
        página onde ELE vê os próprios preços, sem precisar de login."""
        return {"url": fluxy_api.get_client_catalog_link(user_id, client_id)}

    return [
        buscar_cliente_por_nome,
        listar_clientes,
        listar_servicos,
        consultar_os_do_cliente,
        consultar_os_por_numero,
        resumo_do_dia,
        gerar_relatorio_periodo,
        link_catalogo_cliente,
    ]
