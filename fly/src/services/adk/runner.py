import asyncio
import os

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.runners import Runner
from google.genai import types

from src.infra.adk.session_service import get_session_service
from src.infra.agent_api.client import sincronizar_metadados_contato
from src.services.adk.agent import build_agent
from src.services.adk.fluxy_auth import resolver_conta

APP_NAME = os.getenv("GOOGLE_ADK_APP_NAME", "fly")

# Única chave de state sincronizada de volta pro Agent-Api (Target.metadata):
# o telefone que o contato informa manualmente quando a Meta não entrega o
# wa_id automaticamente (ver tools.registrar_telefone_contato) — persiste
# entre sessões pra não pedir de novo, mesmo padrão que os outros agentes já
# usam pra dados coletados em conversa.
CHAVES_METADATA = ("telefone",)


class ResultadoResposta:
    def __init__(self, texto: str, handoff_requested: bool, handoff_reason: str | None, handoff_suggested_queue: str | None = None):
        self.texto = texto
        self.handoff_requested = handoff_requested
        self.handoff_reason = handoff_reason
        self.handoff_suggested_queue = handoff_suggested_queue


async def _abrir_sessao(session_service, user_id: str, session_id: str) -> None:
    """Abre a sessão do ADK usando o id da MessagingSession da plataforma como
    session_id — assim o histórico do ADK fica alinhado 1:1 com a janela de
    24h do produto."""
    sessao = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if sessao is not None:
        print(f"[fly] [session={session_id} user={user_id}] sessao ADK existente reutilizada")
        return

    try:
        await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        print(f"[fly] [session={session_id} user={user_id}] sessao ADK nova criada")
    except AlreadyExistsError:
        print(f"[fly] [session={session_id} user={user_id}] sessao ADK ja existia (race no create)")


async def _executar(pergunta: str, user_id: str, session_id: str, agent_config: dict, target_info: dict) -> ResultadoResposta:
    # session_service (e o pool asyncpg por trás dele) é criado e descartado
    # dentro do mesmo event loop desta chamada — cada mensagem roda num
    # asyncio.run() próprio, e um pool asyncpg não sobrevive entre loops.
    print(f"[fly] [session={session_id} user={user_id}] _executar: abrindo session_service")
    async with get_session_service() as session_service:
        await _abrir_sessao(session_service, user_id, session_id)

        conta = resolver_conta(target_info)
        print(
            f"[fly] [session={session_id} user={user_id}] montando agent "
            f"'{agent_config.get('name')}' conta_autorizada={conta.autorizado} "
            f"empresa={conta.company_name} "
            f"personality_len={len((agent_config.get('personality') or ''))}"
        )
        agent = build_agent(agent_config, conta)
        runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
        mensagem = types.Content(role="user", parts=[types.Part(text=pergunta)])

        resposta_final = ""

        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=mensagem):
            calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
            if calls:
                nomes = [c.name for c in calls]
                print(f"[fly] [session={session_id} user={user_id}] tool call: {nomes}")
            if event.is_final_response() and event.content and event.content.parts:
                resposta_final = event.content.parts[0].text or resposta_final

        print(
            f"[fly] [session={session_id} user={user_id}] loop do runner terminou, "
            f"resposta_final='{resposta_final[:200]}'"
        )

        sessao_final = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)

        handoff_requested = False
        handoff_reason = None
        handoff_suggested_queue = None
        closing_requested = False

        if sessao_final is not None:
            handoff_requested = bool(sessao_final.state.get("handoff_requested"))
            handoff_reason = sessao_final.state.get("handoff_reason")
            handoff_suggested_queue = sessao_final.state.get("handoff_suggested_queue")
            closing_requested = bool(sessao_final.state.get("closing_requested"))

            print(
                f"[fly] [session={session_id} user={user_id}] state final: "
                f"handoff={handoff_requested} closing={closing_requested}"
            )

            if closing_requested and agent_config.get("closingEnabled") and agent_config.get("closingMessage"):
                # Mensagem de finalização ativada: sobrepõe o texto gerado pela
                # IA. Desativada: mantém o texto que o próprio agente gerou.
                resposta_final = agent_config["closingMessage"]

            metadata = {chave: sessao_final.state[chave] for chave in CHAVES_METADATA if chave in sessao_final.state}
            if metadata:
                sincronizar_metadados_contato(user_id, metadata)

        # Sem isso, handoff_requested/closing_requested ficam GRUDADOS pra
        # sempre no state da sessão do ADK (nada os limpa depois de usados) —
        # o session_id é o mesmo enquanto a janela de 24h da MessagingSession
        # não expirar, então toda mensagem seguinte do cliente reacionava o
        # mesmo handoff (reabrindo ticket sem parar) ou repetia a mesma
        # closingMessage estática pra sempre, ignorando o que o cliente
        # realmente mandou depois. Apagar a sessão do ADK aqui começa uma
        # conversa nova do zero na próxima mensagem, mesmo dentro da mesma
        # janela de 24h — o handoff/encerramento marca o fim daquele
        # atendimento de IA, não só uma resposta qualquer.
        if handoff_requested or closing_requested:
            await session_service.delete_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
            print(f"[fly] [session={session_id} user={user_id}] sessao ADK apagada (handoff/closing)")

        print(f"[fly] [session={session_id} user={user_id}] _executar retornando")

        return ResultadoResposta(
            texto=resposta_final,
            handoff_requested=handoff_requested,
            handoff_reason=handoff_reason,
            handoff_suggested_queue=handoff_suggested_queue,
        )


def gerar_resposta_adk(pergunta: str, user_id: str, session_id: str, agent_config: dict, target_info: dict) -> ResultadoResposta:
    return asyncio.run(_executar(pergunta, user_id, session_id, agent_config, target_info))
