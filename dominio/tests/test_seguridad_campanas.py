import pytest
from uuid import uuid4
from app import bd
def test_get_sin_api_key(cliente, monkeypatch):
    monkeypatch.setenv("CAMPANAS_API_KEY", "clave-de-prueba")

    respuesta = cliente.get("/campanas/999999999")

    assert respuesta.status_code == 401


def test_post_sin_api_key(cliente, monkeypatch):
    monkeypatch.setenv("CAMPANAS_API_KEY", "clave-de-prueba")

    respuesta = cliente.post("/campanas/U100649")

    assert respuesta.status_code == 401


def test_api_key_incorrecta(cliente, monkeypatch):
    monkeypatch.setenv("CAMPANAS_API_KEY", "clave-de-prueba")

    respuesta = cliente.get(
        "/campanas/999999999",
        headers={"X-API-Key": "clave-equivocada"}
    )

    assert respuesta.status_code == 401


def test_api_key_correcta(cliente, monkeypatch):
    monkeypatch.setenv("CAMPANAS_API_KEY", "clave-de-prueba")

    respuesta = cliente.get(
        "/campanas/999999999",
        headers={"X-API-Key": "clave-de-prueba"}
    )

    # La autenticacion pasa, pero la campana no existe.
    assert respuesta.status_code == 404
    assert respuesta.json()["detail"] == "Campaña no encontrada"


def test_sin_configuracion_de_api_key(cliente, monkeypatch):
    monkeypatch.delenv("CAMPANAS_API_KEY", raising=False)

    respuesta = cliente.get("/campanas/999999999")

    assert respuesta.status_code == 503


def test_limite_campanas_responde_429(cliente, monkeypatch):
    monkeypatch.setenv("CAMPANAS_API_KEY", "clave-de-prueba")

    def limite_excedido(usuario):
        raise bd.LimiteCampanasExcedido()

    monkeypatch.setattr(bd, "crear_campana", limite_excedido)

    respuesta = cliente.post(
        "/campanas/U100649",
        headers={"X-API-Key": "clave-de-prueba"},
    )

    assert respuesta.status_code == 429
    assert respuesta.headers["Retry-After"] == "60"

def test_limite_real_postgresql(cliente):
    """Solo permite tres campañas por usuario cada 60 segundos."""
    usuario = f"U-TEST-{uuid4().hex[:12]}"
    campanas_creadas = []

    with bd.pool.connection() as conexion:
        conexion.execute(
            """
            INSERT INTO usuarios
                (usuario_id, consentimiento, acepta_marketing)
            VALUES (%s, TRUE, TRUE)
            """,
            (usuario,),
        )

    try:
        for _ in range(3):
            campana = bd.crear_campana(usuario)
            assert campana is not None
            campanas_creadas.append(campana["id"])

        # La cuarta solicitud debe ser rechazada.
        with pytest.raises(bd.LimiteCampanasExcedido):
            bd.crear_campana(usuario)

    finally:
        # Eliminar todos los datos temporales de la prueba.
        with bd.pool.connection() as conexion:
            conexion.execute(
                "DELETE FROM campanas WHERE id = ANY(%s)",
                (campanas_creadas,),
            )
            conexion.execute(
                "DELETE FROM usuarios WHERE usuario_id = %s",
                (usuario,),
            )


def test_predict_sin_api_key_rechaza(cliente, usuario, monkeypatch):
    monkeypatch.setenv("CAMPANAS_API_KEY", "clave-de-prueba")

    respuesta = cliente.post("/predict", json={"usuario_id": usuario, "k": 4})

    assert respuesta.status_code == 401


def test_predict_con_api_key_correcta_pasa_autenticacion(cliente, usuario, monkeypatch):
    monkeypatch.setenv("CAMPANAS_API_KEY", "clave-de-prueba")

    respuesta = cliente.post(
        "/predict",
        json={"usuario_id": usuario, "k": 4},
        headers={"X-API-Key": "clave-de-prueba"},
    )

    assert respuesta.status_code == 200


def test_openapi_declara_prefijos_publicos(cliente):
    servidores = cliente.get("/openapi.json").json()["servers"]

    assert [servidor["url"] for servidor in servidores] == ["/api", "/api/dominio"]
