"""Publicación de campañas en RabbitMQ para Nexus Retail EP3."""

import json
import os

import pika


COLA = "campanas"


def salud() -> dict[str, str]:
    """Comprueba RabbitMQ y si el worker tiene un consumidor activo."""
    url = os.environ["RABBITMQ_URL"]
    parametros = pika.URLParameters(url)
    parametros.socket_timeout = 3
    parametros.blocked_connection_timeout = 5
    conexion = pika.BlockingConnection(parametros)
    try:
        canal = conexion.channel()
        estado = canal.queue_declare(queue=COLA, passive=True)
        return {
            "rabbitmq": "ok",
            "worker": "ok" if estado.method.consumer_count else "sin_consumidor",
        }
    finally:
        conexion.close()


def publicar_campana(campana_id: int) -> None:
    """Envía el identificador de una campaña a RabbitMQ."""

    url = os.environ["RABBITMQ_URL"]

    parametros = pika.URLParameters(url)
    parametros.socket_timeout = 3
    parametros.blocked_connection_timeout = 5

    conexion = pika.BlockingConnection(parametros)

    try:
        canal = conexion.channel()

        canal.queue_declare(
            queue=COLA,
            durable=True,
        )

        canal.confirm_delivery()

        canal.basic_publish(
            exchange="",
            routing_key=COLA,
            body=json.dumps({"campana_id": campana_id}),
            properties=pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            ),
            mandatory=True,
        )

    finally:
        conexion.close()
