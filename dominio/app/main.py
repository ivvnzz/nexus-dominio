"""Microservicio de dominio de Nexus Retail.

Es el único que lee y escribe la base de datos. Atiende al front (a través del gateway,
que quita el prefijo /api/dominio), llama a la IA para las recomendaciones y guarda cada
predicción con su entrada, su resultado, la versión del modelo y la fecha.
"""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

import os
import secrets
import httpx
import psycopg
import psycopg_pool
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import bd, config, ia, cola

import pika


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
log = logging.getLogger("nexus.dominio")

VERSION_RESPALDO = "respaldo-dominio"  # versión registrada cuando la lista no la produjo el modelo


def exigir_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key")
):
    """Protege las operaciones que pueden consumir servicios externos."""
    clave_esperada = os.getenv("CAMPANAS_API_KEY")
    if not clave_esperada:
        raise HTTPException(status_code=503, detail="Autenticacion no configurada")
    if not x_api_key or not secrets.compare_digest(
        x_api_key.encode("utf-8"), clave_esperada.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="API key invalida")


@asynccontextmanager
async def ciclo_de_vida(_: FastAPI):
    bd.abrir()
    yield
    bd.cerrar()


app = FastAPI(
    title="Nexus · Dominio",
    version="1.0.0",
    lifespan=ciclo_de_vida,
    servers=[
        {"url": "/api", "description": "Gateway: rutas públicas EP3"},
        {"url": "/api/dominio", "description": "Gateway: rutas de dominio"},
    ],
)


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


@app.get("/salud")
def salud():
    """Estado agregado sin invocar SageMaker ni el LLM."""
    estado = {
        "status": "ok",
        "service": "dominio",
        "bd": "ok",
        "ia": "ok",
        "sagemaker": "ok",
        "rabbitmq": "ok",
        "worker": "ok",
        "llm": "configurado",
    }
    try:
        bd.ping()
    except (psycopg.Error, psycopg_pool.PoolTimeout):
        estado.update(
            status="error",
            bd="sin_conexion",
            ia="sin_comprobar",
            sagemaker="sin_comprobar",
            rabbitmq="sin_comprobar",
            worker="sin_comprobar",
            llm="sin_comprobar",
        )
        return JSONResponse(status_code=503, content=estado)
    try:
        respuesta = httpx.get(f"{config.IA_URL}/health", timeout=2)
        respuesta.raise_for_status()
        datos_ia = respuesta.json()
        remoto = str(datos_ia.get("origen_puntajes", ""))
        if not remoto.startswith("sagemaker:"):
            estado.update(status="degradado", ia="ok", sagemaker="no_configurado")
    except (httpx.HTTPError, ValueError):
        estado.update(status="degradado", ia="sin_conexion", sagemaker="sin_conexion")
    try:
        estado.update(cola.salud())
    except (KeyError, OSError, pika.exceptions.AMQPError, TimeoutError):
        estado.update(rabbitmq="sin_conexion", worker="sin_conexion")
    if not os.getenv("NVIDIA_API_KEY") or not os.getenv("NVIDIA_MODELO"):
        estado.update(llm="sin_configuracion")
    if any(
        estado[c] not in ("ok", "configurado")
        for c in ("bd", "sagemaker", "rabbitmq", "worker", "llm")
    ):
        estado["status"] = "degradado"
        return JSONResponse(status_code=503, content=estado)
    return estado


@app.get("/usuarios")
def usuarios(limite: int = Query(6, ge=1, le=50)):
    return bd.usuarios_de_ejemplo(limite)


@app.get("/usuarios/{usuario_id}/compras")
def compras(usuario_id: str, limite: int = Query(8, ge=1, le=50)):
    return bd.compras(usuario_id.strip(), limite)


@app.get("/predicciones")
def listar_predicciones(usuario_id: str = Query(..., min_length=1, max_length=40), limite: int = Query(5, ge=1, le=50)):
    return bd.predicciones_de(usuario_id.strip(), limite)


@app.get("/predicciones/{prediccion_id}", dependencies=[Depends(exigir_api_key)])
def obtener_prediccion(prediccion_id: int):
    fila = bd.prediccion_por_id(prediccion_id)
    if fila is None:
        raise HTTPException(status_code=404, detail="Prediccion no encontrada")
    return fila


@app.post("/predict", dependencies=[Depends(exigir_api_key)])
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


@app.post(
    "/campanas/{usuario}",
    status_code=202,
    dependencies=[Depends(exigir_api_key)]
)
def solicitar_campana(usuario: str):
    """Registra una campaña y envía el trabajo a RabbitMQ."""


    try:
        campana = bd.crear_campana(usuario.strip())
    except bd.LimiteCampanasExcedido:
        raise HTTPException(
            status_code=429,
            detail="Limite de solicitudes de campanas excedido",
            headers={"Retry-After": "60"},
        ) from None

    if campana is None:
        raise HTTPException(
            status_code=403,
            detail="Usuario no autorizado para campañas de marketing"
        )

    campana_id = campana["id"]


    try:
        cola.publicar_campana(campana_id)
        estado = "pendiente"

    except (pika.exceptions.AMQPError, OSError, TimeoutError):
        # Si RabbitMQ falla, guardamos un resultado de respaldo.
        estado = "degradado"

        bd.actualizar_campana(
            campana_id,
            estado="degradado",
            texto="Descubre nuestros productos y novedades disponibles.",
            motivo_error="Cola de mensajes no disponible",
        )

    return {
        "id": campana_id,
        "estado": estado,
        "mensaje": "Solicitud de campaña registrada",
    }
@app.get(
    "/campanas/{campana_id}",
    dependencies=[Depends(exigir_api_key)]
)
def consultar_campana(campana_id: int):
    """Permite consultar el estado y resultado de una campaña."""

    campana = bd.obtener_campana(campana_id)

    if campana is None:
        raise HTTPException(
            status_code=404,
            detail="Campaña no encontrada",
        )

    return {
        "id": campana["id"],
        "estado": campana["estado"],
        "texto": campana["texto"],
        "modelo_llm": campana["modelo_llm"],
        "intentos": campana["intentos"],
        "motivo_error": campana["motivo_error"],
        "creado_en": campana["creado_en"],
        "actualizado_en": campana["actualizado_en"],
    }
