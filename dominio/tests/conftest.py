"""Las pruebas usan un PostgreSQL real con el esquema y los datos del cargador.

En el workflow, PostgreSQL corre como "service" y antes se ejecuta `python -m carga.cargar`.
En local: definir DATABASE_URL apuntando a una base ya cargada. La IA siempre se simula.
"""
import os

import httpx
import pytest

if not os.environ.get("DATABASE_URL"):
    pytest.skip("Define DATABASE_URL con una base cargada por carga.cargar", allow_module_level=True)

from fastapi.testclient import TestClient  # noqa: E402

from app import bd, ia  # noqa: E402
from app.main import app  # noqa: E402

USUARIO_CON_HISTORIAL = None


@pytest.fixture(scope="session")
def cliente():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="session")
def usuario(cliente):
    """Un cliente real de la base, con consentimiento y compras."""
    return cliente.get("/usuarios?limite=1").json()[0]["usuario_id"]


@pytest.fixture
def ia_simulada(monkeypatch):
    """Reemplaza las llamadas HTTP a la IA. Devuelve un dict para configurar la respuesta."""
    control = {"modo": "ok", "skus": None, "llamadas": 0}

    def post(url, json=None, timeout=None):
        control["llamadas"] += 1
        req = httpx.Request("POST", url)
        if control["modo"] == "caida":
            raise httpx.ConnectError("conexión rechazada", request=req)
        if control["modo"] == "lenta":
            raise httpx.ReadTimeout("tiempo agotado", request=req)
        if control["modo"] == "error":
            return httpx.Response(503, json={"detail": "El modelo no está disponible"}, request=req)
        skus = control["skus"] or recomendables(json["k"] + 2)
        cuerpo = {
            "usuario_id": json["usuario_id"],
            "origen": "modelo",
            "motivo": None,
            "version_modelo": "hgb-prueba",
            "recomendaciones": [
                {"puesto": i + 1, "sku": s, "categoria": "redes", "marca": "Dell", "precio_lista": 1000.0, "puntaje": 2.0 - i / 10}
                for i, s in enumerate(skus)
            ],
        }
        return httpx.Response(200, json=cuerpo, request=req)

    monkeypatch.setattr(ia.httpx, "post", post)
    return control


def recomendables(n):
    with bd.pool.connection() as c:
        filas = c.execute(
            "SELECT sku FROM productos WHERE recomendable AND activo AND COALESCE(stock,0) > 0 ORDER BY sku LIMIT %s",
            (n,),
        ).fetchall()
    return [f["sku"] for f in filas]
