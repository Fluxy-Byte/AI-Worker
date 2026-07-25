from src.services.adk.runner import gerar_resposta_adk, ResultadoResposta


def gerar_resposta(pergunta: str, target: dict, agent_config: dict, session: dict = None) -> ResultadoResposta:
    session = session or {}
    target = target or {}

    session_id = session.get("id")
    user_id = target.get("id")

    if not session_id or not user_id:
        raise ValueError("Sessão sem 'id'/target sem 'id' — não é possível abrir a sessão no ADK.")

    return gerar_resposta_adk(pergunta, user_id=user_id, session_id=session_id, agent_config=agent_config)
