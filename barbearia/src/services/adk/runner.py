import asyncio
import os

from google.adk.errors.already_exists_error import AlreadyExistsError
from google.adk.runners import Runner
from google.genai import types

from src.infra.adk.session_service import get_session_service
from src.infra.agent_api.client import sincronizar_metadados_contato
from src.services.adk.agent import build_agent

APP_NAME = os.getenv("GOOGLE_ADK_APP_NAME", "generic")

# Chaves de state sincronizadas de volta pro Agent-Api (Target.metadata) a
# cada turno, pra aparecer no Agent Console e persistir entre sessões — nome
# do cliente + o agendamento em construção e os já confirmados.
CHAVES_METADATA = ("nome", "agendamento", "agendamento_confirmado", "agendamentos")


class ResultadoResposta:
    def __init__(self, partes: list[dict], handoff_requested: bool, handoff_reason: str | None, handoff_suggested_queue: str | None = None):
        self.partes = partes
        self.handoff_requested = handoff_requested
        self.handoff_reason = handoff_reason
        self.handoff_suggested_queue = handoff_suggested_queue


async def _abrir_sessao(session_service, user_id: str, session_id: str) -> None:
    """Abre a sessão do ADK usando o id da MessagingSession da plataforma como
    session_id — assim o histórico do ADK fica alinhado 1:1 com a janela de
    24h do produto."""
    sessao = await session_service.get_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
    if sessao is not None:
        print(f"[barbearia] [session={session_id} user={user_id}] sessao ADK existente reutilizada")
        return

    try:
        await session_service.create_session(app_name=APP_NAME, user_id=user_id, session_id=session_id)
        print(f"[barbearia] [session={session_id} user={user_id}] sessao ADK nova criada")
    except AlreadyExistsError:
        print(f"[barbearia] [session={session_id} user={user_id}] sessao ADK ja existia (race no create)")


async def _executar(pergunta: str, user_id: str, session_id: str, agent_config: dict, target_info: dict) -> ResultadoResposta:
    # session_service (e o pool asyncpg por trás dele) é criado e descartado
    # dentro do mesmo event loop desta chamada — cada mensagem roda num
    # asyncio.run() próprio, e um pool asyncpg não sobrevive entre loops.
    print(f"[barbearia] [session={session_id} user={user_id}] _executar: abrindo session_service")
    async with get_session_service() as session_service:
        await _abrir_sessao(session_service, user_id, session_id)

        rag_enabled = bool(agent_config.get("ragEnabled"))
        print(
            f"[barbearia] [session={session_id} user={user_id}] montando agent "
            f"'{agent_config.get('name')}' ragEnabled={rag_enabled} "
            f"personality_len={len((agent_config.get('personality') or ''))}"
        )
        agent = build_agent(agent_config, target_info)
        runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
        mensagem = types.Content(role="user", parts=[types.Part(text=pergunta)])

        resposta_final = ""

        async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=mensagem):
            calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
            if calls:
                nomes = [c.name for c in calls]
                print(f"[barbearia] [session={session_id} user={user_id}] tool call: {nomes}")

            if event.is_final_response() and event.content and event.content.parts:
                resposta_final = event.content.parts[0].text or resposta_final

        print(
            f"[barbearia] [session={session_id} user={user_id}] loop do runner terminou, "
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
                f"[barbearia] [session={session_id} user={user_id}] state final: "
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
            print(f"[barbearia] [session={session_id} user={user_id}] sessao ADK apagada (handoff/closing)")

        partes: list[dict] = []
        if resposta_final:
            partes.append({"texto": resposta_final})

        print(f"[barbearia] [session={session_id} user={user_id}] _executar retornando ({len(partes)} parte(s))")

        return ResultadoResposta(
            partes=partes or [{"texto": ""}],
            handoff_requested=handoff_requested,
            handoff_reason=handoff_reason,
            handoff_suggested_queue=handoff_suggested_queue,
        )


def gerar_resposta_adk(pergunta: str, user_id: str, session_id: str, agent_config: dict, target_info: dict) -> ResultadoResposta:
    # O SDK google-adk/google-genai lê GOOGLE_API_KEY do processo sozinho (não
    # existe parâmetro explícito pra passar a key na hora de montar o Agent) —
    # sobrescrever aqui é seguro porque este worker processa 1 mensagem por
    # vez (prefetch_count=1, consumer síncrono) e atende sempre o MESMO agente
    # por processo, então o valor nunca varia entre mensagens concorrentes.
    # Token ausente/vazio no payload = não mexe no que já está no env.
    if agent_config.get("geminiToken"):
        os.environ["GOOGLE_API_KEY"] = agent_config["geminiToken"]

    return asyncio.run(_executar(pergunta, user_id, session_id, agent_config, target_info))
