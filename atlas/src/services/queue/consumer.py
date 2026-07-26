"""
Consumidor da fila própria deste agente (`task.agent.atlas.create`).

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
  },
  "messagingSession": {"id", "startedAt"},
  # Lote agrupado, em ordem de recebimento — cada uma também já foi gravada
  # individualmente no Mongo pelo Inbound-Service.
  "messages": [{"mongoMessageId", "externalMessageId", "type", "text", "timestamp"}, ...]
}

Publica em `outbound.message.send` (resposta normal / erro / formato não
suportado) ou `desk.ticket.create` (handoff para atendimento humano).
"""

import json
import os
import socket

from main import gerar_resposta
from src.infra.agent_api.client import choose_handoff_queue, generate_free_error_message, get_service_island_queues
from src.infra.rabbitmq.connection import RabbitMQ
from src.services.queue.publisher import (
    QUEUE_DESK_TICKET_CREATE,
    publish_desk_ticket_create,
    publish_outbound_message,
)

AGENT_NAME = "atlas"
QUEUE = f"task.agent.{AGENT_NAME}.create"
DLQ = f"{QUEUE}.dlq"

# Identifica qual processo físico atendeu cada mensagem — usado pra investigar
# se existe mais de um consumidor (ex.: container órfão) disputando a mesma
# fila em produção (RabbitMQ é compartilhado entre dev e prod).
INSTANCE_ID = f"{socket.gethostname()}:{os.getpid()}"


def _base_outbound_payload(payload: dict) -> dict:
    return {
        "target": payload.get("target"),
        "whatsappChannel": payload.get("whatsappChannel"),
        "messagingSession": payload.get("messagingSession"),
        "origin": "AI",
    }


def _handle_unsupported_format(channel, payload: dict, agent: dict) -> None:
    outbound = _base_outbound_payload(payload)
    outbound["answer"] = {"text": agent.get("unsupportedFormatMessage", ""), "audio": "", "image": ""}
    outbound["finishesProcessing"] = True
    publish_outbound_message(channel, outbound)


def _handle_generation_error(channel, payload: dict, agent: dict, error: Exception) -> None:
    print(f"ERRO: Erro ao gerar resposta do agente {AGENT_NAME}: {error}")

    if agent.get("errorEnabled") and agent.get("errorMessage"):
        text = agent["errorMessage"]
    else:
        text = generate_free_error_message(agent.get("name", AGENT_NAME))

    outbound = _base_outbound_payload(payload)
    outbound["answer"] = {"text": text, "audio": "", "image": ""}
    outbound["finishesProcessing"] = True
    publish_outbound_message(channel, outbound)


def _handle_handoff(channel, payload: dict, agent: dict, reason: str | None) -> None:
    whatsapp_channel = payload.get("whatsappChannel") or {}
    service_island_id = whatsapp_channel.get("serviceIslandId")

    queues: list[dict] = []
    if service_island_id:
        try:
            queues = get_service_island_queues(service_island_id)
        except Exception as e:
            print(f"[atlas] Falha ao buscar filas da ilha {service_island_id}: {e}")

    queue_id = choose_handoff_queue(queues, reason or "", agent.get("defaultQueueId"))

    desk_payload = _base_outbound_payload(payload)
    desk_payload["agent"] = {"id": agent.get("id"), "name": agent.get("name")}
    desk_payload["queueId"] = queue_id
    desk_payload["handoffReason"] = reason

    publish_desk_ticket_create(channel, desk_payload)


def _on_message(channel, method, properties, body):
    try:
        payload = json.loads(body)
        agent_info = payload.get("agent") or {}
        messages = payload.get("messages") or []
        messaging_session = payload.get("messagingSession") or {}

        print(
            f"[{AGENT_NAME}] instance={INSTANCE_ID} recebida mensagem "
            f"session={messaging_session.get('id')} messages={messages!r}"
        )

        non_text = [m for m in messages if m.get("type") != "TEXT"]
        if non_text or not messages:
            print(f"[{AGENT_NAME}] instance={INSTANCE_ID} Formato não suportado — messages={messages!r}")
            _handle_unsupported_format(channel, payload, agent_info)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Mensagens agrupadas viram uma única pergunta, respeitando a ordem de
        # recebimento (regra de agrupamento do Inbound-Service).
        pergunta = "\n".join(m.get("text", "") for m in messages).strip()

        try:
            resultado = gerar_resposta(pergunta, agent_info.get("id"), agent_info.get("name")) if pergunta else None
        except Exception as e:
            _handle_generation_error(channel, payload, agent_info, e)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        if resultado is None:
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        if resultado.handoff_requested:
            _handle_handoff(channel, payload, agent_info, resultado.handoff_reason)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        outbound = _base_outbound_payload(payload)
        outbound["answer"] = {"text": resultado.texto, "audio": "", "image": ""}
        outbound["finishesProcessing"] = True
        publish_outbound_message(channel, outbound)

        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"ERRO: Erro ao processar mensagem do agente {AGENT_NAME}: {e}")
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

    print(f"[{AGENT_NAME}] instance={INSTANCE_ID} aguardando mensagens na fila {QUEUE}")
    channel.start_consuming()
