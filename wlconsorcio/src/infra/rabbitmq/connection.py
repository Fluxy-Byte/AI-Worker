import os

import pika


class RabbitMQ:
    def __init__(self):
        self._connection = None
        self._channel = None

    def connect(self):
        url = os.getenv("URL_RABBITMQ")
        params = pika.URLParameters(url)

        self._connection = pika.BlockingConnection(params)
        self._channel = self._connection.channel()

        print("RabbitMQ conectado")

        return self._channel

    def get_channel(self):
        if self._channel is None:
            raise RuntimeError("Canal do RabbitMQ não inicializado. Chame connect() primeiro.")
        return self._channel

    def close(self):
        if self._connection and not self._connection.is_closed:
            self._connection.close()
