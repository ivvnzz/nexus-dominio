
"""Worker de campañas de Nexus Retail EP3."""

import json
import os
import time

import httpx
import pika

from app import bd

COLA = "campanas"
NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"


def datos_comerciales(campana_id: int):
    """Obtiene solo categorías y marcas. Nunca envía datos del cliente."""

    with bd.pool.connection() as conexion:
        autorizado = conexion.execute(
            """
            SELECT 1
            FROM campanas c
            JOIN usuarios u ON u.usuario_id = c.usuario_id
            WHERE c.id = %s
              AND u.consentimiento IS TRUE
              AND u.acepta_marketing IS TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM exclusiones_perfilamiento e
                  WHERE e.usuario_id = u.usuario_id
              )
            """,
            (campana_id,),
        ).fetchone()

        if autorizado is None:
            return None

        filas = conexion.execute(
            """
            SELECT p.categoria, p.marca
            FROM campanas c
            JOIN transacciones t ON t.usuario_id = c.usuario_id
            JOIN productos p ON p.sku = t.sku
            WHERE c.id = %s
              AND t.estado = 'pagado'
              AND p.activo IS TRUE
              AND p.recomendable IS TRUE
              AND COALESCE(p.stock, 0) > 0
            GROUP BY p.categoria, p.marca
            ORDER BY SUM(t.cantidad) DESC
            LIMIT 5
            """,
            (campana_id,),
        ).fetchall()

    return [
        {"categoria": f["categoria"], "marca": f["marca"]}
        for f in filas
    ]


def generar_texto(contexto: list[dict]):
    """Consulta NVIDIA con un máximo de tres intentos."""

    clave = os.getenv("NVIDIA_API_KEY", "")
    modelo = os.getenv("NVIDIA_MODELO", "")

    if not clave or not modelo:
        return None, 0, "NVIDIA no configurado"

    contenido = json.dumps(contexto, ensure_ascii=False)
    error = None

    for intento in range(1, 4):
        try:
            respuesta = httpx.post(
                NVIDIA_URL,
                headers={
                    "Authorization": f"Bearer {clave}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": modelo,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Eres un redactor de marketing de Nexus Retail. "
                                "Escribe una campaña en español de 2 a 3 frases. "
                                "Usa solo información comercial proporcionada. "
                                "No inventes descuentos ni solicites datos personales."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                "Categorías y marcas comerciales: "
                                + contenido
                            ),
                        },
                    ],
                    "max_tokens": 180,
                    "temperature": 0.5,
                },
                timeout=20.0,
            )

            respuesta.raise_for_status()
            texto = respuesta.json()["choices"][0]["message"]["content"]

            if not isinstance(texto, str) or not texto.strip():
                raise ValueError("Respuesta vacía")

            return texto.strip(), intento, None

        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            error = type(exc).__name__

            if isinstance(exc, httpx.HTTPStatusError):
                codigo = exc.response.status_code
                error = f"HTTP {codigo}"

                if codigo in (400, 401, 403, 404):
                    return None, intento, error

            if intento < 3:
                time.sleep(2 if intento == 1 else 5)

    return None, 3, error


def procesar_campana(campana_id: int):
    """Genera la campaña y persiste el resultado."""

    campana = bd.obtener_campana(campana_id)

    if campana is None or campana["estado"] != "pendiente":
        return

    contexto = datos_comerciales(campana_id)

    if contexto is None:
        bd.actualizar_campana(
            campana_id,
            estado="error",
            motivo_error="Sin consentimiento vigente",
        )
        return

    texto, intentos, error = generar_texto(contexto)

    if texto:
        bd.actualizar_campana(
            campana_id,
            estado="listo",
            texto=texto,
            modelo_llm=os.getenv("NVIDIA_MODELO"),
            intentos=intentos,
        )
    else:
        bd.actualizar_campana(
            campana_id,
            estado="degradado",
            texto="Descubre nuestras categorías y novedades disponibles.",
            modelo_llm=os.getenv("NVIDIA_MODELO") or None,
            intentos=intentos,
            motivo_error=error,
        )


def main():
    """Escucha RabbitMQ y procesa las campañas pendientes."""

    bd.abrir()

    parametros = pika.URLParameters(os.environ["RABBITMQ_URL"])
    parametros.heartbeat = 600
    parametros.connection_attempts = 5
    parametros.retry_delay = 2

    conexion = pika.BlockingConnection(parametros)
    canal = conexion.channel()
    canal.queue_declare(queue=COLA, durable=True)
    canal.queue_declare(queue="campanas.fallidas", durable=True)
    canal.confirm_delivery()
    canal.basic_qos(prefetch_count=1)

    def recibir(ch, metodo, propiedades, cuerpo):
        try:
            mensaje = json.loads(cuerpo)
            campana_id = int(mensaje["campana_id"])
        except (ValueError, TypeError, KeyError):
            ch.basic_reject(
                delivery_tag=metodo.delivery_tag,
                requeue=False,
            )
            return

        try:
            procesar_campana(campana_id)
        
        except Exception as exc:
            reintentos = int(
                (propiedades.headers or {}).get("x-reintentos-worker", 0)
            )

            print(
                f"Error en campaña {campana_id}: "
                f"{type(exc).__name__}. Reintento {reintentos}/2",
                flush=True,
            )

            # Máximo tres intentos en total.
            if reintentos < 2:
                time.sleep(2 if reintentos == 0 else 5)
                destino = COLA
            else:
                destino = "campanas.fallidas"

            # Publicar de forma persistente antes de confirmar el original.
            ch.basic_publish(
                exchange="",
                routing_key=destino,
                body=cuerpo,
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type="application/json",
                    headers={"x-reintentos-worker": reintentos + 1},
                ),
                mandatory=True,
            )

            if destino == "campanas.fallidas":
                try:
                    bd.actualizar_campana(
                        campana_id,
                        estado="degradado",
                        texto="Descubre nuestras novedades disponibles.",
                        intentos=3,
                        motivo_error=f"Error interno: {type(exc).__name__}",
                    )
                except Exception:
                    print(
                        "No fue posible actualizar la campaña; "
                        "mensaje conservado en campanas.fallidas",
                        flush=True,
                    )

            ch.basic_ack(delivery_tag=metodo.delivery_tag)
            return


        ch.basic_ack(delivery_tag=metodo.delivery_tag)

    canal.basic_consume(
        queue=COLA,
        on_message_callback=recibir,
    )

    print("Worker Nexus Retail iniciado", flush=True)
    canal.start_consuming()


if __name__ == "__main__":
    main()
