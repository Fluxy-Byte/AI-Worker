from src.services.adk.runner import gerar_resposta_adk, resetar_jornada_contato, ResultadoResposta


def gerar_resposta(pergunta: str, target: dict, agent_config: dict, session: dict = None) -> ResultadoResposta:
    session = session or {}
    target = target or {}

    session_id = session.get("id")
    user_id = target.get("id")

    if not session_id or not user_id:
        raise ValueError("Sessão sem 'id'/target sem 'id' — não é possível abrir a sessão no ADK.")

    return gerar_resposta_adk(pergunta, user_id=user_id, session_id=session_id, agent_config=agent_config, target_info=target)


def resetar_jornada(target: dict) -> int:
    """Reset de jornada por palavra-chave (WhatsappChannel.wordsToReset) —
    apaga todas as sessões do ADK e os metadados salvos do contato. Retorna
    quantas sessões foram apagadas."""
    target = target or {}
    user_id = target.get("id")
    if not user_id:
        raise ValueError("Target sem 'id' — não é possível resetar a jornada.")

    return resetar_jornada_contato(user_id)
