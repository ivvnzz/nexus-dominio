"""Cargador idempotente de los CSV tratados para Nexus Retail.

Uso local:
    $env:DATABASE_URL='postgresql://nexus:nexus_dev@localhost:5433/nexus'
    py -m carga.cargar

Se ejecuta como un solo job: crea el esquema y carga tres tablas dentro de una
única transacción. Si ocurre un error, toda la carga se revierte.
"""
import csv
import hashlib
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from carga.transformaciones import COLUMNAS, convertir

RAIZ = Path(__file__).resolve().parent
ESQUEMA = RAIZ / "sql" / "esquema.sql"
DATOS = RAIZ / "datos"


@dataclass(frozen=True)
class Especificacion:
    tabla: str
    archivo: str
    claves: tuple[str, ...]


ESPECIFICACIONES = (
    Especificacion("productos", "productos_limpio.csv", ("sku",)),
    Especificacion("usuarios", "usuarios_limpio.csv", ("usuario_id",)),
    Especificacion("transacciones", "transacciones_limpio.csv", ("pedido_id", "linea")),
)


def leer_csv(especificacion):
    """Valida columnas, claves presentes y duplicados antes de abrir una conexión."""
    ruta = DATOS / especificacion.archivo
    if not ruta.is_file():
        raise FileNotFoundError(f"No existe el CSV: {ruta}")
    if ruta.stat().st_size == 0:
        raise ValueError(f"CSV vacío: {ruta.name}")
    contenido = ruta.read_bytes()
    huella = hashlib.sha256(contenido).hexdigest()
    with ruta.open(newline="", encoding="utf-8-sig") as archivo:
        lector = csv.DictReader(archivo)
        if not lector.fieldnames:
            raise ValueError(f"CSV sin encabezados: {ruta.name}")
        requeridas = {
            "productos": set(COLUMNAS["productos"]),
            "usuarios": set(COLUMNAS["usuarios"]),
            "transacciones": {
                "pedido_id", "linea", "usuario_id", "sku", "fecha_dt", "cantidad",
                "precio_unitario", "descuento", "monto", "canal_norm", "estado_norm",
            },
        }[especificacion.tabla]
        faltantes = requeridas.difference(lector.fieldnames)
        if faltantes:
            raise ValueError(f"Columnas faltantes en {ruta.name}: {sorted(faltantes)}")
        vistos = set()
        filas = []
        for numero_linea, registro in enumerate(lector, start=2):
            try:
                fila = convertir(especificacion.tabla, registro)
                columnas = COLUMNAS[especificacion.tabla]
                clave = tuple(fila[columnas.index(col)] for col in especificacion.claves)
                if any(valor is None for valor in clave):
                    raise ValueError("clave vacía")
                if clave in vistos:
                    raise ValueError("clave duplicada")
                vistos.add(clave)
                filas.append(fila)
            except (ValueError, KeyError, TypeError) as exc:
                raise ValueError(
                    f"Dato inválido en {ruta.name}, línea {numero_linea}: {exc}"
                ) from exc
    if not filas:
        raise ValueError(f"CSV sin filas: {ruta.name}")
    return filas, huella


def preparar_datos():
    """Valida los tres datasets y la integridad referencial antes de insertar."""
    preparados = {}
    for spec in ESPECIFICACIONES:
        preparados[spec.tabla] = leer_csv(spec)
    skus = {fila[0] for fila in preparados["productos"][0]}
    usuarios = {fila[0] for fila in preparados["usuarios"][0]}
    for t in preparados["transacciones"][0]:
        if t[2] not in usuarios or t[3] not in skus:
            raise ValueError("Transacción con usuario o SKU inexistente")
    return preparados


def crear_esquema(cursor):
    if not ESQUEMA.is_file():
        raise FileNotFoundError(f"Falta el esquema: {ESQUEMA}")
    # No se interpolan datos en este SQL: el archivo es parte del código versionado.
    cursor.execute(ESQUEMA.read_text(encoding="utf-8-sig"), prepare=False)


def cargar_tabla(cursor, spec, filas, huella):
    from psycopg import sql

    columnas = COLUMNAS[spec.tabla]
    campos = sql.SQL(", ").join(map(sql.Identifier, columnas))
    marcadores = sql.SQL(", ").join(sql.Placeholder() for _ in columnas)
    sentencia = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT DO NOTHING").format(
        sql.Identifier(spec.tabla), campos, marcadores
    )
    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(spec.tabla)))
    antes = cursor.fetchone()[0]
    cursor.executemany(sentencia, filas)
    cursor.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(spec.tabla)))
    despues = cursor.fetchone()[0]
    insertadas = despues - antes
    existentes = len(filas) - insertadas
    cursor.execute(
        """INSERT INTO auditoria_carga
           (tabla, archivo, archivo_sha256, filas_archivo,
            filas_insertadas, filas_ya_existentes, filas_descartadas, detalle)
           VALUES (%s, %s, %s, %s, %s, %s, 0, %s)""",
        (spec.tabla, spec.archivo, huella, len(filas), insertadas, existentes,
         "Carga idempotente (ON CONFLICT DO NOTHING)"),
    )
    print(f"{spec.tabla}: archivo={len(filas)}, nuevas={insertadas}, existentes={existentes}", flush=True)


def main():
    import psycopg

    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        print("ERROR: define DATABASE_URL (ver documentación F1).", file=sys.stderr)
        return 1
    try:
        preparados = preparar_datos()
        print("CSV validados: productos, usuarios y transacciones.", flush=True)
        with psycopg.connect(dsn, connect_timeout=15) as conn:
            with conn.cursor() as cursor:
                # Evita carreras si se iniciaran dos cargadores simultáneamente.
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (20261017,))
                crear_esquema(cursor)
                for spec in ESPECIFICACIONES:
                    filas, huella = preparados[spec.tabla]
                    cargar_tabla(cursor, spec, filas, huella)
            # El bloque conn confirma todas las tablas en una sola transacción.
        print("CARGA COMPLETADA: transacción confirmada.", flush=True)
        return 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR de datos o archivos: {exc}", file=sys.stderr)
        return 1
    except psycopg.Error as exc:
        # Mostrar el mensaje principal del motor, sin exponer la cadena de conexión.
        detalle = getattr(getattr(exc, "diag", None), "message_primary", None)
        print(f"ERROR PostgreSQL: {detalle or type(exc).__name__}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"ERROR inesperado de carga: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
