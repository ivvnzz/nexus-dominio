"""Acceso a PostgreSQL. El dominio es el único servicio que lee y escribe la base.

El esquema lo crea el servicio "carga" (carga/sql/esquema.sql): aquí solo se consulta
y se insertan predicciones.
"""
from __future__ import annotations

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from app import config

pool = ConnectionPool(
    config.DATABASE_URL,
    min_size=1,
    max_size=5,
    open=False,
    timeout=5,
    kwargs={"row_factory": dict_row, "connect_timeout": 5},
)


def abrir():
    # wait=False: el dominio arranca aunque la base todavía no responda; /health lo informa.
    pool.open(wait=False)


def cerrar():
    pool.close()


def ping() -> bool:
    with pool.connection() as c:
        c.execute("SELECT 1")
    return True


def existe_usuario(usuario_id: str) -> bool:
    with pool.connection() as c:
        return c.execute("SELECT 1 FROM usuarios WHERE usuario_id = %s", (usuario_id,)).fetchone() is not None


def excluido_de_perfilamiento(usuario_id: str) -> bool:
    with pool.connection() as c:
        return (
            c.execute("SELECT 1 FROM exclusiones_perfilamiento WHERE usuario_id = %s", (usuario_id,)).fetchone()
            is not None
        )


def usuarios_de_ejemplo(limite: int) -> list[dict]:
    """Clientes con consentimiento y con compras: los que el modelo puede personalizar."""
    with pool.connection() as c:
        return c.execute(
            """SELECT u.usuario_id, u.region
               FROM usuarios u
               WHERE u.consentimiento IS TRUE
                 AND EXISTS (SELECT 1 FROM transacciones t WHERE t.usuario_id = u.usuario_id)
               ORDER BY u.usuario_id
               LIMIT %s""",
            (limite,),
        ).fetchall()


def compras(usuario_id: str, limite: int) -> list[dict]:
    with pool.connection() as c:
        filas = c.execute(
            """SELECT t.sku, p.nombre, p.categoria, p.marca, t.fecha, t.cantidad, t.estado
               FROM transacciones t
               JOIN productos p ON p.sku = t.sku
               WHERE t.usuario_id = %s
               ORDER BY t.fecha DESC, t.pedido_id, t.linea
               LIMIT %s""",
            (usuario_id, limite),
        ).fetchall()
    for f in filas:
        f["fecha"] = f["fecha"].isoformat()
    return filas


def skus_disponibles(skus: list[str]) -> set[str]:
    """SKU que siguen activos y con stock. Stock desconocido cuenta como sin stock (regla conservadora)."""
    if not skus:
        return set()
    with pool.connection() as c:
        filas = c.execute(
            """SELECT sku FROM productos
               WHERE sku = ANY(%s) AND activo IS TRUE AND COALESCE(stock, 0) > 0""",
            (skus,),
        ).fetchall()
    return {f["sku"] for f in filas}


def mas_vendidos(usuario_id: str, k: int, dias: int) -> list[dict]:
    """Respaldo del dominio: los más vendidos de los últimos `dias` días de datos, sin lo ya comprado."""
    with pool.connection() as c:
        filas = c.execute(
            """WITH fin AS (SELECT max(fecha) AS f FROM transacciones)
               SELECT p.sku, p.categoria, p.marca, p.precio_lista::float AS precio_lista
               FROM transacciones t
               JOIN productos p ON p.sku = t.sku
               CROSS JOIN fin
               WHERE t.estado = 'pagado'
                 AND t.fecha >= fin.f - make_interval(days => %s)
                 AND p.recomendable IS TRUE AND p.activo IS TRUE AND COALESCE(p.stock, 0) > 0
                 AND p.sku NOT IN (SELECT sku FROM transacciones WHERE usuario_id = %s)
               GROUP BY p.sku, p.categoria, p.marca, p.precio_lista
               ORDER BY sum(t.cantidad) DESC, p.sku
               LIMIT %s""",
            (dias, usuario_id, k),
        ).fetchall()
    return [{"puesto": i + 1, **f, "puntaje": None} for i, f in enumerate(filas)]


def guardar_prediccion(
    *,
    usuario_id: str,
    k: int,
    origen: str,
    motivo: str | None,
    version_modelo: str,
    entrada: dict,
    resultado: list[dict],
    ia_ms: int | None,
    total_ms: int,
    atendido_por: str,
) -> dict:
    with pool.connection() as c:
        return c.execute(
            """INSERT INTO predicciones
                 (usuario_id, k, origen, motivo, version_modelo, entrada, resultado, ia_ms, total_ms, atendido_por)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
               RETURNING id, creado_en""",
            (usuario_id, k, origen, motivo, version_modelo, Jsonb(entrada), Jsonb(resultado),
             ia_ms, total_ms, atendido_por),
        ).fetchone()


def predicciones_de(usuario_id: str, limite: int) -> list[dict]:
    with pool.connection() as c:
        filas = c.execute(
            """SELECT id, creado_en, usuario_id, k, origen, motivo, version_modelo,
                      resultado AS recomendaciones, ia_ms, total_ms, atendido_por
               FROM predicciones
               WHERE usuario_id = %s
               ORDER BY creado_en DESC, id DESC
               LIMIT %s""",
            (usuario_id, limite),
        ).fetchall()
    for f in filas:
        f["fecha"] = f.pop("creado_en").isoformat()
    return filas


def prediccion_por_id(prediccion_id: int) -> dict | None:
    with pool.connection() as c:
        fila = c.execute(
            """SELECT id, creado_en, usuario_id, k, origen, motivo, version_modelo,
                      resultado AS recomendaciones, ia_ms, total_ms, atendido_por
               FROM predicciones
               WHERE id = %s""",
            (prediccion_id,),
        ).fetchone()
    if fila is None:
        return None
    fila["fecha"] = fila.pop("creado_en").isoformat()
    return fila


class LimiteCampanasExcedido(Exception):
    """Se alcanzo el limite de solicitudes de campanas."""


def crear_campana(usuario_id: str) -> dict | None:
    """Registra campañas autorizadas, aplicando limites compartidos."""

    with pool.connection() as c:
        # Evita que las dos replicas superen el limite al mismo tiempo.
        # El bloqueo se libera al finalizar la transaccion.
        c.execute("SELECT pg_advisory_xact_lock(20261122)")

        limites = c.execute(
            """
            SELECT
                COUNT(*) AS globales,
                COUNT(*) FILTER (WHERE usuario_id = %s) AS del_usuario
            FROM campanas
            WHERE creado_en > NOW() - INTERVAL '60 seconds'
            """,
            (usuario_id,),
        ).fetchone()

        if limites["globales"] >= 20 or limites["del_usuario"] >= 3:
            raise LimiteCampanasExcedido()

        return c.execute(
            """
            INSERT INTO campanas (usuario_id)
            SELECT u.usuario_id
            FROM usuarios u
            WHERE u.usuario_id = %s
              AND u.consentimiento IS TRUE
              AND u.acepta_marketing IS TRUE
              AND NOT EXISTS (
                  SELECT 1
                  FROM exclusiones_perfilamiento e
                  WHERE e.usuario_id = u.usuario_id
              )
            RETURNING id, estado, creado_en
            """,
            (usuario_id,),
        ).fetchone()

def obtener_campana(campana_id: int) -> dict | None:
    """Consulta una campaña y su estado en PostgreSQL."""
    with pool.connection() as c:
        fila = c.execute(
            """
            SELECT id, usuario_id, estado, texto,
                   modelo_llm, intentos, motivo_error,
                   creado_en, actualizado_en
            FROM campanas
            WHERE id = %s
            """,
            (campana_id,),
        ).fetchone()

    if fila:
        fila["creado_en"] = fila["creado_en"].isoformat()
        fila["actualizado_en"] = fila["actualizado_en"].isoformat()

    return fila

def actualizar_campana(
    campana_id: int,
    estado: str,
    texto: str | None = None,
    modelo_llm: str | None = None,
    intentos: int = 0,
    motivo_error: str | None = None,
) -> bool:
    """Actualiza el estado y resultado de una campaña."""

    if estado not in ("pendiente", "listo", "error", "degradado"):
        raise ValueError("Estado de campaña no válido")

    with pool.connection() as c:
        fila = c.execute(
            """
            UPDATE campanas
            SET estado = %s,
                texto = %s,
                modelo_llm = %s,
                intentos = %s,
                motivo_error = %s,
                actualizado_en = now()
            WHERE id = %s
            RETURNING id
            """,
            (
                estado,
                texto,
                modelo_llm,
                intentos,
                motivo_error,
                campana_id,
            ),
        ).fetchone()

    return fila is not None