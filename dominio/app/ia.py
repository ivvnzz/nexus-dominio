"""Cliente del microservicio de IA (POST /predict, GET /health)."""
from __future__ import annotations

import time

import httpx

from app import config


class IANoDisponible(Exception):
    """La IA no respondió, tardó demasiado o respondió con un error del servidor."""


_version_cache: dict = {"valor": None, "hasta": 0.0}


def predecir(usuario_id: str, k: int) -> tuple[dict, int]:
    """Devuelve (respuesta de la IA, milisegundos). Lanza IANoDisponible o httpx.HTTPStatusError (4xx)."""
    inicio = time.perf_counter()
    try:
        r = httpx.post(f"{config.IA_URL}/predict", json={"usuario_id": usuario_id, "k": k}, timeout=config.IA_TIMEOUT_S)
    except httpx.TimeoutException as e:
        raise IANoDisponible(f"la IA tardó más de {config.IA_TIMEOUT_S:g} s") from e
    except httpx.TransportError as e:
        raise IANoDisponible("no hay conexión con la IA") from e
    ms = round((time.perf_counter() - inicio) * 1000)
    if r.status_code >= 500:
        raise IANoDisponible(f"la IA respondió {r.status_code}")
    r.raise_for_status()
    return r.json(), ms


def version_modelo(respuesta_ia: dict) -> str:
    """La versión viene en la respuesta de la IA; si no la trae, se arma desde su /health (cache de 60 s)."""
    v = respuesta_ia.get("version_modelo") or respuesta_ia.get("version")
    if v:
        return str(v)
    ahora = time.monotonic()
    if _version_cache["valor"] and ahora < _version_cache["hasta"]:
        return _version_cache["valor"]
    try:
        h = httpx.get(f"{config.IA_URL}/health", timeout=2).json()
        valor = f"{h.get('modelo', 'modelo')}-corte-{h.get('corte_servicio', 'sin-fecha')}"
    except (httpx.HTTPError, ValueError):
        valor = "no-informada"
    _version_cache.update(valor=valor, hasta=ahora + 60)
    return valor
