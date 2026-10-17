"""Conversión de CSV tratados al contrato del esquema PostgreSQL.

No altera los CSV originales. Los valores opcionales vacíos se convierten en None.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def texto(valor):
    if valor is None:
        return None
    limpio = str(valor).strip()
    return limpio or None


def decimal(valor):
    valor = texto(valor)
    if valor is None:
        return None
    try:
        resultado = Decimal(valor)
    except InvalidOperation as exc:
        raise ValueError(f"Decimal inválido: {valor!r}") from exc
    if not resultado.is_finite():
        raise ValueError("Decimal no finito")
    return resultado


def entero(valor):
    numero = decimal(valor)
    if numero is None:
        return None
    if numero != numero.to_integral_value():
        raise ValueError(f"No es entero: {valor!r}")
    return int(numero)


def booleano(valor):
    valor = texto(valor)
    if valor is None:
        return None
    v = valor.casefold()
    if v in ("true", "1", "1.0", "t", "yes", "si", "sí"):
        return True
    if v in ("false", "0", "0.0", "f", "no"):
        return False
    raise ValueError(f"Booleano inválido: {valor!r}")


def fecha(valor):
    v = texto(valor)
    return date.fromisoformat(v) if v else None


def fecha_hora(valor):
    v = texto(valor)
    return datetime.fromisoformat(v) if v else None


# El orden de las columnas coincide con la inserción parametrizada del cargador.
COLUMNAS = {
    "productos": ("sku", "nombre", "categoria", "marca", "precio_lista", "stock", "activo", "fecha_alta", "precio_sospechoso", "recomendable"),
    "usuarios": ("usuario_id", "fecha_registro", "region", "canal_captacion", "acepta_marketing", "consentimiento"),
    "transacciones": ("pedido_id", "linea", "usuario_id", "sku", "fecha", "cantidad", "precio_unitario", "descuento", "monto", "canal", "estado"),
}


def convertir(tabla, fila):
    """Transforma una fila de CSV en tupla tipada, sin inventar valores ausentes."""
    if tabla == "productos":
        return (
            texto(fila["sku"]), texto(fila["nombre"]), texto(fila["categoria"]),
            texto(fila["marca"]), decimal(fila["precio_lista"]), entero(fila["stock"]),
            booleano(fila["activo"]), fecha(fila["fecha_alta"]),
            booleano(fila["precio_sospechoso"]), booleano(fila["recomendable"]),
        )
    if tabla == "usuarios":
        return (
            texto(fila["usuario_id"]), fecha(fila["fecha_registro"]),
            texto(fila["region"]), texto(fila["canal_captacion"]),
            booleano(fila["acepta_marketing"]), booleano(fila["consentimiento"]),
        )
    if tabla == "transacciones":
        return (
            texto(fila["pedido_id"]), entero(fila["linea"]),
            texto(fila["usuario_id"]), texto(fila["sku"]),
            fecha_hora(fila["fecha_dt"]), entero(fila["cantidad"]),
            decimal(fila["precio_unitario"]), decimal(fila["descuento"]),
            decimal(fila["monto"]), texto(fila["canal_norm"]),
            texto(fila["estado_norm"]),
        )
    raise ValueError(f"Tabla no soportada: {tabla}")
