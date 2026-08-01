import json

import pika

QUEUE_OUTBOUND_SEND = "outbound.message.send"
QUEUE_DESK_TICKET_CREATE = "desk.ticket.create"


def _publish(channel, queue: str, payload: dict) -> None:
    dlq = f"{queue}.dlq"

    channel.queue_declare(queue=dlq, durable=True)
    channel.queue_declare(
        queue=queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": dlq,
        },
    )

    channel.basic_publish(
        exchange="",
        routing_key=queue,
        body=json.dumps(payload, ensure_ascii=False),
        properties=pika.BasicProperties(delivery_mode=2),
    )

    target = payload.get("target") or {}
    session = payload.get("messagingSession") or {}
    answer_preview = ((payload.get("answer") or {}).get("text") or "")[:150]
    print(
        f"[fly] [session={session.get('id')} wa={target.get('waId')}] "
        f"PUBLICOU em {queue}: answer='{answer_preview}'"
    )


def publish_outbound_message(channel, payload: dict) -> None:
    """Resposta normal / erro / formato não suportado — segue pro
    Outbound-Worker entregar via Meta."""
    _publish(channel, QUEUE_OUTBOUND_SEND, payload)


def publish_desk_ticket_create(channel, payload: dict) -> None:
    """Handoff para atendimento humano — Desk-Worker cria o ticket WAITING."""
    _publish(channel, QUEUE_DESK_TICKET_CREATE, payload)
