import asyncio
import os

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.runners import Runner
from google.genai import types

from src.infra.adk.session_service import get_session_service
from src.services.adk.agent import build_agent

APP_NAME = os.getenv("GOOGLE_ADK_APP_NAME", "generic")


class ResultadoResposta:
    def __init__(self, texto: str, handoff_requested: bool, handoff_reason: str | None):
        self.texto = texto
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
    # session_service (e o pool asyncpg por trás dele) é criado e descartado
    # dentro do mesmo event loop desta chamada — cada mensagem roda num
    # asyncio.run() próprio, e um pool asyncpg não sobrevive entre loops.
    async with get_session_service() as session_service:
        await _abrir_sessao(session_service, user_id, session_id)

        agent = build_agent(agent_config)
        runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
        mensagem = types.Content(role="user", parts=[types.Part(text=pergunta)])

        resposta_final = ""

        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=mensagem):
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

        return ResultadoResposta(
            texto=resposta_final,
            handoff_requested=handoff_requested,
            handoff_reason=handoff_reason,
        )


def gerar_resposta_adk(pergunta: str, user_id: str, session_id: str, agent_config: dict) -> ResultadoResposta:
    return asyncio.run(_executar(pergunta, user_id, session_id, agent_config))
