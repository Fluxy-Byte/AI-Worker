
### Lembrando que para o projeto e necessário estar com o python na versão 12


# Inciar seu ambiente virtual
python -m venv .venv

# Ativar seu ambiente
.venv\Scripts\activate

# Instalar as dependências
pip install -r requirements.txt

# Quando terminar, congele as versões que funcionaram:
pip freeze > requirements.txt



# Node.js como Gateway

Responsabilidades:

- Receber webhooks da Meta.
- Validar assinatura (x-hub-signature-256).
- Gerenciar autenticação.
- Salvar sessões e mensagens.
- Aplicar rate limits.
- Publicar eventos no RabbitMQ.
- Enviar respostas para a Meta.

# Python como Motor de IA

Responsabilidades:

- LangChain.
- LangGraph.
- PGVector.
- RAG.
- Ferramentas (tools).
- Memória.
- Classificação de intenção.
- Orquestração entre agentes.