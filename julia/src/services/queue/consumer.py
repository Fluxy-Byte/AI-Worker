"""
Consumidor de UMA fila dedicada por agente (`task.agent.<nome>.create`) —
cada instância implantada deste worker atende um único Agent, escolhido pela
env `AGENT_NAME` (mesmo valor do `Agent.name` cadastrado no Agent Console).
O código continua genérico (personalidade/RAG vêm sempre frescos do payload,
nada fixo aqui) — só a fila que essa instância consome é fixa. Ver
Inbound-Service/src/infrastructure/queue/rabbitmq/publisher.ts
(resolveAgentQueueName) pra a sanitização do nome, que precisa bater com a
usada aqui (`_sanitize_agent_name`).

Contrato do payload (publicado pelo Inbound-Service, já deduplicado e
agrupado/debounced por sessão em janelas de 10s):

{
  "target": {"id", "waId", "name", "metadata"},
  "whatsappChannel": {"id", "phoneNumberId", "wabaId", "serviceIslandId"},
  "agent": {
    "id", "name", "defaultQueueId",
    "processingMessage",           # não usado aqui — enviado pelo Inbound-Service
    "transferMessage",              # não usado aqui — enviado pelo Desk-Worker
    "unsupportedFormatMessage",
    "outOfHoursMessage", "outOfHoursEnabled",
    "closingMessage", "closingEnabled",
    "errorMessage", "errorEnabled",
    "personality", "ragEnabled",    # só usados aqui (worker genérico)
  },
  "messagingSession": {"id", "startedAt"},
  "messages": [{"mongoMessageId", "externalMessageId", "type", "text", "timestamp"}, ...]
}

Publica em `outbound.message.send` (resposta normal / erro / formato não
suportado) ou `desk.ticket.create` (handoff para atendimento humano).
"""

import json
import os
import re
import traceback

from main import gerar_resposta
from src.infra.agent_api.client import choose_handoff_queue, generate_free_error_message, get_service_island_queues
from src.infra.rabbitmq.connection import RabbitMQ
from src.services.queue.publisher import (
    QUEUE_DESK_TICKET_CREATE,
    publish_desk_ticket_create,
    publish_outbound_message,
)


def _sanitize_agent_name(name: str) -> str:
    """Espelha resolveAgentQueueName do Inbound-Service (minúsculas, sem
    acento/pontuação/espaço) — tem que bater exatamente, senão a fila que
    este worker declara diverge da que o Inbound-Service publica."""
    return re.sub(r"[^a-z0-9]+", "", name.strip().lower())


_RAW_AGENT_NAME = os.getenv("AGENT_NAME")
if not _RAW_AGENT_NAME:
    raise RuntimeError(
        "AGENT_NAME não definida — cada instância do worker max atende um único "
        "agente e precisa saber qual (mesmo nome cadastrado no Agent Console)."
    )

AGENT_NAME = _sanitize_agent_name(_RAW_AGENT_NAME)
QUEUE = f"task.agent.{AGENT_NAME}.create"
DLQ = f"{QUEUE}.dlq"


def _log(payload: dict, msg: str) -> None:
    """Log com correlação por sessão/contato — todo log de uma mesma mensagem
    carrega o mesmo prefixo, pra dar pra rastrear com grep no stdout do
    worker (ex: `docker logs max | grep <session_id>`)."""
    target = payload.get("target") or {}
    session = payload.get("messagingSession") or {}
    print(f"[julia] [session={session.get('id')} wa={target.get('waId')}] {msg}")


def _base_outbound_payload(payload: dict) -> dict:
    return {
        "target": payload.get("target"),
        "whatsappChannel": payload.get("whatsappChannel"),
        "messagingSession": payload.get("messagingSession"),
        "origin": "AI",
    }


def _handle_unsupported_format(channel, payload: dict, agent: dict) -> None:
    _log(payload, "formato nao suportado -> outbound com unsupportedFormatMessage")
    outbound = _base_outbound_payload(payload)
    outbound["answer"] = {"text": agent.get("unsupportedFormatMessage", ""), "audio": "", "image": ""}
    outbound["finishesProcessing"] = True
    publish_outbound_message(channel, outbound)


def _handle_generation_error(channel, payload: dict, agent: dict, error: Exception) -> None:
    _log(payload, f"ERRO ao gerar resposta do agente {agent.get('name', AGENT_NAME)}: {error}")
    print(traceback.format_exc())

    if agent.get("errorEnabled") and agent.get("errorMessage"):
        text = agent["errorMessage"]
    else:
        text = generate_free_error_message(agent.get("name", "Assistente"), openai_api_key=agent.get("openaiToken"))

    outbound = _base_outbound_payload(payload)
    outbound["answer"] = {"text": text, "audio": "", "image": ""}
    outbound["finishesProcessing"] = True
    publish_outbound_message(channel, outbound)


def _handle_handoff(channel, payload: dict, agent: dict, reason: str | None, suggested_queue: str | None = None) -> None:
    whatsapp_channel = payload.get("whatsappChannel") or {}
    service_island_id = whatsapp_channel.get("serviceIslandId")
    _log(payload, f"handoff solicitado, motivo='{reason}' fila_sugerida='{suggested_queue}' ilha={service_island_id}")

    queues: list[dict] = []
    if service_island_id:
        try:
            queues = get_service_island_queues(service_island_id)
        except Exception as e:
            _log(payload, f"Falha ao buscar filas da ilha {service_island_id}: {e}")

    queue_id = choose_handoff_queue(
        queues, reason or "", agent.get("defaultQueueId"), suggested_queue, openai_api_key=agent.get("openaiToken")
    )
    _log(payload, f"handoff -> desk.ticket.create, queueId={queue_id}")

    desk_payload = _base_outbound_payload(payload)
    desk_payload["agent"] = {"id": agent.get("id"), "name": agent.get("name")}
    desk_payload["queueId"] = queue_id
    desk_payload["handoffReason"] = reason

    publish_desk_ticket_create(channel, desk_payload)


def _on_message(channel, method, properties, body):
    payload = {}
    try:
        payload = json.loads(body)
        agent = payload.get("agent") or {}
        messages = payload.get("messages") or []
        target = payload.get("target") or {}
        messaging_session = payload.get("messagingSession") or {}

        _log(
            payload,
            f"RECEBIDA de {QUEUE}: agent={agent.get('name')} ({agent.get('id')}) "
            f"{len(messages)} msg(s) tipos={[m.get('type') for m in messages]}",
        )

        non_text = [m for m in messages if (m.get("type") or "").upper() != "TEXT"]
        if non_text or not messages:
            _handle_unsupported_format(channel, payload, agent)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            _log(payload, "ACK (formato nao suportado)")
            return

        # Mensagens agrupadas viram uma única pergunta, respeitando a ordem de
        # recebimento (regra de agrupamento do Inbound-Service).
        pergunta = "\n".join(m.get("text", "") for m in messages).strip()
        _log(payload, f"pergunta='{pergunta[:200]}' -> chamando ADK")

        try:
            resultado = gerar_resposta(pergunta, target, agent, session=messaging_session)
        except Exception as e:
            _log(payload, f"ADK falhou: {e}")
            print(traceback.format_exc())
            _handle_generation_error(channel, payload, agent, e)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            _log(payload, "ACK (erro na geracao)")
            return

        _log(
            payload,
            f"ADK respondeu: handoff={resultado.handoff_requested} "
            f"texto='{(resultado.texto or '')[:200]}'",
        )

        if resultado.handoff_requested:
            _handle_handoff(channel, payload, agent, resultado.handoff_reason, resultado.handoff_suggested_queue)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            _log(payload, "ACK (handoff)")
            return

        outbound = _base_outbound_payload(payload)
        outbound["answer"] = {"text": resultado.texto or "", "audio": "", "image": ""}
        outbound["finishesProcessing"] = True
        publish_outbound_message(channel, outbound)

        channel.basic_ack(delivery_tag=method.delivery_tag)
        _log(payload, "ACK (resposta normal publicada em outbound.message.send)")
    except Exception as e:
        _log(payload, f"ERRO NAO TRATADO ao processar mensagem do agente generico: {e}")
        print(traceback.format_exc())
        channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)


def start_consumer() -> None:
    rabbitmq = RabbitMQ()
    channel = rabbitmq.connect()

    channel.queue_declare(queue=DLQ, durable=True)
    channel.queue_declare(
        queue=QUEUE,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": DLQ,
        },
    )

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=QUEUE, on_message_callback=_on_message)

    print(f"Aguardando mensagens na fila {QUEUE}")
    channel.start_consuming()
