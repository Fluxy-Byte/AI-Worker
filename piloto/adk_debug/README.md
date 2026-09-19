# adk_debug — testar o agente do piloto sem RabbitMQ/Postgres/Agent-Api

Esta pasta existe só para testar a instrução e as tools do agente ADK do
`piloto` (`src/services/adk/agent.py:build_agent`) isoladamente, sem precisar
subir RabbitMQ, o banco de sessões do ADK nem o Agent-Api.

`piloto_agent/agent.py` monta um `root_agent` fixo usando um `agent_config` e
um `target_info` fake — a mesma função `build_agent` que o worker de produção
usa em `runner.py`, só que com dados de teste no lugar do payload real da
fila.

## Passo a passo

### 1. Criar o venv (uma vez só, se ainda não existir)

Na raiz do `piloto` (`AI-Worker/piloto`):

```powershell
python -m venv .venv
```

### 2. Instalar as dependências

```powershell
.\.venv\Scripts\pip.exe install -r requirements.txt
```

Pode demorar alguns minutos (langchain, spacy, google-adk etc).

### 3. Conferir o `.env`

O `.env` da raiz do `piloto` precisa ter `GOOGLE_API_KEY` preenchido (é lido
automaticamente pelo `piloto_agent/agent.py` via `load_dotenv`). As demais
variáveis (RabbitMQ, Postgres, Agent-Api) **não são necessárias** pra esse
teste — só o `agent.py` é carregado, não o `runner.py`/`worker.py`.

### 4. Rodar o `adk web`

Entre na pasta `adk_debug` (a pasta **pai** de `piloto_agent`, não a de
dentro) e rode o `adk.exe` do venv:

```powershell
cd adk_debug
..\.venv\Scripts\adk.exe web
```

Abra `http://localhost:8000` no navegador, selecione **`piloto_agent`** no
dropdown e converse no chat.

Alternativa só de terminal, sem UI:

```powershell
..\.venv\Scripts\adk.exe run piloto_agent
```

Pra encerrar, `Ctrl+C` no terminal onde o servidor está rodando.

## O que esse teste cobre (e o que não cobre)

Cobre:
- A instrução (prompt) montada em `build_agent`, incluindo os blocos de
  primeiro contato / dados já conhecidos / RAG.
- As tools chamadas pelo modelo (`atualizar_nome_cliente`,
  `solicitar_atendimento_humano`, `encerrar_conversa`, etc.) — todas elas só
  mexem em `tool_context.state`, sem chamar nada externo.

Não cobre (fica em `src/services/adk/runner.py:_executar`, não testado
aqui):
- Persistência da sessão ADK no Postgres.
- Sincronização de metadados com o Agent-Api (`sincronizar_metadados_contato`).
- A tool de RAG (`consultar_conhecimento`), que só é adicionada quando
  `ragEnabled=True` no `agent_config` — hoje o `_agent_config` de teste está
  com `ragEnabled: False`. Pra testar RAG, também precisa do Postgres com
  pgvector rodando (ver `src/infra/pgvector/connection.py`).

## Simular outros cenários

Edite `piloto_agent/agent.py`:

- **Contato com histórico**: em `_target_info_teste`, adicione
  `"metadata": {"contato_iniciado": True, "nome": "...", ...}` pra pular a
  saudação de primeiro contato (ver `_tem_historico` em
  `src/services/adk/agent.py`).
- **Personalidade diferente**: mude o campo `personality` em
  `_agent_config`.
- **RAG ligado**: mude `ragEnabled` para `True` e preencha `id`/
  `openaiToken` em `_agent_config` (precisa do Postgres/pgvector no ar).
