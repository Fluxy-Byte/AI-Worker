import os

# Metadados que a IA pode armazenar
CHAVES_METADATA = ("nome", "nome_empresa", "quantidade_de_funcionarios", "cargo")

# Nome do agente
APP_NAME = os.getenv("GOOGLE_ADK_APP_NAME", "piloto")