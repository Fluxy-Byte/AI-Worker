import os

# Metadados que a IA pode armazenar
CHAVES_METADATA = (
    "nome",
    "restricao_no_nome",
    "imovel_de_garantia",
    "tem_um_avalista",
    "condicoes_de_pagar_parcelas_remanescentes",
)

# Nome do agente
APP_NAME = os.getenv("GOOGLE_ADK_APP_NAME", "piloto")

# Modelo Gemini usado pelo agente ADK — GOOGLE_ADK_MODEL sobrescreve o default
# fixado aqui. Se a env estiver setada em produção com um modelo descontinuado
# (ex: gemini-1.5-pro, removido pelo Google), esse default NÃO se aplica — a
# env sempre vence. Centralizado aqui (em vez de hardcoded em agent.py) pra
# não haver dois lugares pra manter em sincronia quando o modelo mudar de novo.
GOOGLE_ADK_MODEL = os.getenv("GOOGLE_ADK_MODEL", "gemini-3.8-flash")