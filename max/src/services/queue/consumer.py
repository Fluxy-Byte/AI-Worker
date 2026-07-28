"""
Consumidor da fila genérica (`task.agent.generic.create`) — atende QUALQUER
Agent que não seja atlas/axel (os dois únicos com persona fixa em código),
não importa o nome nem a organização. Ver
Inbound-Service/src/infrastructure/queue/rabbitmq/publisher.ts
(resolveAgentQueueName) pra onde essa regra é decidida.

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

from main import gerar_resposta
from src.infra.agent_api.client import choose_handoff_queue, generate_free_error_message, get_service_island_queues
from src.infra.rabbitmq.connection import RabbitMQ
from src.services.queue.publisher import (
    QUEUE_DESK_TICKET_CREATE,
    publish_desk_ticket_create,
    publish_outbound_message,
)

AGENT_NAME = "generic"
QUEUE = f"task.agent.{AGENT_NAME}.create"
DLQ = f"{QUEUE}.dlq"


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
    print(f"ERRO: Erro ao gerar resposta do agente {agent.get('name', AGENT_NAME)}: {error}")

    if agent.get("errorEnabled") and agent.get("errorMessage"):
        text = agent["errorMessage"]
    else:
        text = generate_free_error_message(agent.get("name", "Assistente"))

    outbound = _base_outbound_payload(payload)
    outbound["answer"] = {"text": text, "audio": "", "image": ""}
    outbound["finishesProcessing"] = True
    publish_outbound_message(channel, outbound)


def _handle_handoff(channel, payload: dict, agent: dict, reason: str | None, suggested_queue: str | None = None) -> None:
    whatsapp_channel = payload.get("whatsappChannel") or {}
    service_island_id = whatsapp_channel.get("serviceIslandId")

    queues: list[dict] = []
    if service_island_id:
        try:
            queues = get_service_island_queues(service_island_id)
        except Exception as e:
            print(f"[max] Falha ao buscar filas da ilha {service_island_id}: {e}")

    queue_id = choose_handoff_queue(queues, reason or "", agent.get("defaultQueueId"), suggested_queue)

    desk_payload = _base_outbound_payload(payload)
    desk_payload["agent"] = {"id": agent.get("id"), "name": agent.get("name")}
    desk_payload["queueId"] = queue_id
    desk_payload["handoffReason"] = reason

    publish_desk_ticket_create(channel, desk_payload)


def _on_message(channel, method, properties, body):
    try:
        payload = json.loads(body)
        agent = payload.get("agent") or {}
        messages = payload.get("messages") or []
        target = payload.get("target") or {}
        messaging_session = payload.get("messagingSession") or {}

        non_text = [m for m in messages if (m.get("type") or "").upper() != "TEXT"]
        if non_text or not messages:
            _handle_unsupported_format(channel, payload, agent)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Mensagens agrupadas viram uma única pergunta, respeitando a ordem de
        # recebimento (regra de agrupamento do Inbound-Service).
        pergunta = "\n".join(m.get("text", "") for m in messages).strip()

        try:
            resultado = gerar_resposta(pergunta, target, agent, session=messaging_session)
        except Exception as e:
            _handle_generation_error(channel, payload, agent, e)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        if resultado.handoff_requested:
            _handle_handoff(channel, payload, agent, resultado.handoff_reason, resultado.handoff_suggested_queue)
            channel.basic_ack(delivery_tag=method.delivery_tag)
            return

        outbound = _base_outbound_payload(payload)
        outbound["answer"] = {"text": resultado.texto or "", "audio": "", "image": ""}
        outbound["finishesProcessing"] = True
        publish_outbound_message(channel, outbound)

        channel.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"ERRO: Erro ao processar mensagem do agente genérico: {e}")
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
