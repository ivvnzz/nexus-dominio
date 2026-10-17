"""Microservicio de dominio de Nexus Retail.

Es el único que lee y escribe la base de datos. Atiende al front (a través del gateway,
que quita el prefijo /api/dominio), llama a la IA para las recomendaciones y guarda cada
predicción con su entrada, su resultado, la versión del modelo y la fecha.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import httpx
import psycopg
import psycopg_pool
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import bd, config, ia

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("nexus.dominio")

VERSION_RESPALDO = "respaldo-dominio"  # versión registrada cuando la lista no la produjo el modelo


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    bd.abrir()
    yield
    bd.cerrar()


app = FastAPI(title="Nexus · Dominio", version="1.0.0", lifespan=ciclo_de_vida)


@app.exception_handler(psycopg.Error)
@app.exception_handler(psycopg_pool.PoolTimeout)
async def base_caida(_: Request, exc: Exception):
    log.error("Error de base de datos: %s", type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "La base de datos no responde"})


@app.middleware("http")
async def cabecera_replica(request: Request, call_next):
    respuesta = await call_next(request)
    respuesta.headers["X-Replica"] = config.REPLICA
    return respuesta


# ------------------------------------------------------------------ modelos de entrada


class PeticionPrediccion(BaseModel):
    usuario_id: str = Field(..., min_length=1, max_length=40, examples=["U100649"])
    k: int = Field(8, ge=4, le=8, description="Cantidad de productos (4 a 8)")


# ------------------------------------------------------------------ rutas


@app.get("/health")
def health():
    try:
        bd.ping()
    except (psycopg.Error, psycopg_pool.PoolTimeout):
        return JSONResponse(
            status_code=503,
            content={"status": "error", "service": "dominio", "replica": config.REPLICA, "bd": "sin_conexion"},
        )
    return {"status": "ok", "service": "dominio", "replica": config.REPLICA, "bd": "ok"}


@app.get("/usuarios")
def usuarios(limite: int = Query(6, ge=1, le=50)):
    return bd.usuarios_de_ejemplo(limite)


@app.get("/usuarios/{usuario_id}/compras")
def compras(usuario_id: str, limite: int = Query(8, ge=1, le=50)):
    return bd.compras(usuario_id.strip(), limite)


@app.get("/predicciones")
def listar_predicciones(usuario_id: str = Query(..., min_length=1, max_length=40), limite: int = Query(5, ge=1, le=50)):
    return bd.predicciones_de(usuario_id.strip(), limite)


@app.post("/predicciones", status_code=201)
def crear_prediccion(p: PeticionPrediccion):
    inicio = time.perf_counter()
    uid = p.usuario_id.strip()
    entrada = {"usuario_id": uid, "k": p.k}
    ia_ms = None

    if bd.excluido_de_perfilamiento(uid):
        # RN2: el cliente pidió que no se use su historial; no se llama a la IA.
        origen, motivo, version = "fallback", "el cliente pidió no usar su historial", VERSION_RESPALDO
        recs = bd.mas_vendidos(uid, p.k, config.DIAS_RESPALDO)
    else:
        try:
            respuesta, ia_ms = ia.predecir(uid, p.k)
            origen = respuesta.get("origen", "modelo")
            motivo = respuesta.get("motivo")
            version = ia.version_modelo(respuesta)
            recs = filtrar_disponibles(respuesta.get("recomendaciones", []), p.k)
        except ia.IANoDisponible as e:
            # Degradación controlada: si la IA no responde, el dominio entrega su propia lista de respaldo.
            log.warning("IA no disponible para %s: %s", uid, e)
            origen, motivo, version = "fallback", f"servicio de IA no disponible ({e})", VERSION_RESPALDO
            recs = bd.mas_vendidos(uid, p.k, config.DIAS_RESPALDO)
        except httpx.HTTPStatusError as e:
            return JSONResponse(status_code=e.response.status_code, content={"detail": "La IA rechazó la petición"})

    total_ms = round((time.perf_counter() - inicio) * 1000)
    guardada = bd.guardar_prediccion(
        usuario_id=uid, k=p.k, origen=origen, motivo=motivo, version_modelo=version,
        entrada=entrada, resultado=recs, ia_ms=ia_ms, total_ms=total_ms, atendido_por=config.REPLICA,
    )
    log.info("prediccion id=%s origen=%s ia_ms=%s total_ms=%s", guardada["id"], origen, ia_ms, total_ms)
    return {
        "id": guardada["id"],
        "fecha": guardada["creado_en"].isoformat(),
        "version_modelo": version,
        "usuario_id": uid,
        "origen": origen,
        "motivo": motivo,
        "recomendaciones": recs,
        "atendido_por": config.REPLICA,
        "ia_ms": ia_ms,
        "total_ms": total_ms,
    }


def filtrar_disponibles(recs: list[dict], k: int) -> list[dict]:
    """Quita lo que la base marca como inactivo o sin stock, deja como máximo k y vuelve a numerar."""
    disponibles = bd.skus_disponibles([str(r.get("sku")) for r in recs])
    quedan = [r for r in recs if str(r.get("sku")) in disponibles][:k]
    return [{**r, "puesto": i + 1} for i, r in enumerate(quedan)]
