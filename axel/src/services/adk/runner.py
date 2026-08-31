import asyncio
import os

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.runners import Runner
from google.genai import types

from src.infra.adk.session_service import get_session_service
from src.services.adk.agent import root_agent
from src.services.adk.metadata_sync import sincronizar_metadados_contato

APP_NAME = os.getenv("GOOGLE_ADK_APP_NAME", "axel")

# Chaves do state que compõem o perfil do lead (spec item 20) — sincronizadas com os
# metadados do contato no Agent-Api a cada turno.
CHAVES_METADATA = (
    "nome",
    "perfil_imovel",
    "perfil_financeiro",
    "recomendacoes",
    "imoveis_apresentados",
    "imoveis_interesse",
    "agendamento",
)


class ResultadoResposta:
    def __init__(self, partes: list[dict], handoff_requested: bool, handoff_reason: str | None):
        self.partes = partes
        self.handoff_requested = handoff_requested
        self.handoff_reason = handoff_reason


async def _abrir_sessao(session_service, user_id: str, session_id: str) -> None:
    """Abre a sessão do ADK usando o id da MessagingSession da plataforma como
    session_id — assim o histórico do ADK fica alinhado 1:1 com a janela de
    24h do produto."""
    sessao = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if sessao is not None:
        return

    try:
        await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    except AlreadyExistsError:
        pass


async def _executar(pergunta: str, user_id: str, session_id: str, agent_config: dict) -> ResultadoResposta:
    # session_service (e o engine/pool do asyncpg por trás dele) é criado e descartado
    # dentro do mesmo event loop desta chamada — cada mensagem roda num asyncio.run()
    # próprio, e um pool asyncpg não sobrevive entre loops diferentes.
    async with get_session_service() as session_service:
        await _abrir_sessao(session_service, user_id, session_id)

        runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
        mensagem = types.Content(role="user", parts=[types.Part(text=pergunta)])

        resposta_final = ""
        imagens_para_enviar: list[dict] = []

        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=mensagem):
            for func_response in event.get_function_responses():
                if func_response.name == "buscar_imoveis":
                    resposta_tool = func_response.response or {}
                    for imovel in resposta_tool.get("imoveis", []):
                        if imovel.get("imagem_url"):
                            imagens_para_enviar.append({
                                "titulo": imovel.get("titulo", ""),
                                "imagem_url": imovel["imagem_url"],
                            })

            if event.is_final_response() and event.content and event.content.parts:
                resposta_final = event.content.parts[0].text or resposta_final

        sessao_final = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)

        handoff_requested = False
        handoff_reason = None

        if sessao_final is not None:
            handoff_requested = bool(sessao_final.state.get("handoff_requested"))
            handoff_reason = sessao_final.state.get("handoff_reason")

            closing_requested = bool(sessao_final.state.get("closing_requested"))
            if closing_requested and agent_config.get("closingEnabled") and agent_config.get("closingMessage"):
                # Mensagem de finalização ativada: sobrepõe o texto gerado pela
                # IA. Desativada: mantém o texto que o próprio agente gerou.
                resposta_final = agent_config["closingMessage"]

            # Sincroniza o perfil acumulado do lead com o Agent-Api (metadados do
            # contato) — best-effort, não deve travar a resposta ao cliente.
            metadata = {chave: sessao_final.state[chave] for chave in CHAVES_METADATA if chave in sessao_final.state}
            if metadata:
                sincronizar_metadados_contato(user_id, metadata)

        partes: list[dict] = []
        if resposta_final:
            partes.append({"texto": resposta_final})
        for imagem in imagens_para_enviar:
            partes.append({"texto": imagem["titulo"], "imagem_url": imagem["imagem_url"]})

        return ResultadoResposta(
            partes=partes or [{"texto": ""}],
            handoff_requested=handoff_requested,
            handoff_reason=handoff_reason,
        )


def gerar_resposta_adk(pergunta: str, user_id: str, session_id: str, agent_config: dict) -> ResultadoResposta:
    # O SDK google-adk/google-genai lê GOOGLE_API_KEY do processo sozinho (não
    # existe parâmetro explícito pra passar a key na hora de montar o Agent) —
    # sobrescrever aqui é seguro porque este worker processa 1 mensagem por
    # vez (prefetch_count=1, consumer síncrono) e atende sempre o MESMO agente
    # por processo, então o valor nunca varia entre mensagens concorrentes.
    # Token ausente/vazio no payload = não mexe no que já está no env.
    if agent_config.get("geminiToken"):
        os.environ["GOOGLE_API_KEY"] = agent_config["geminiToken"]

    return asyncio.run(_executar(pergunta, user_id, session_id, agent_config))
