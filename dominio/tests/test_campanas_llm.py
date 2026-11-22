
import httpx
import json

from app import worker


class ResultadoFalso:
    def __init__(self, filas):
        self.filas = filas

    def fetchone(self):
        return self.filas[0] if self.filas else None

    def fetchall(self):
        return self.filas


class ConexionFalsa:
    def __init__(self):
        self.llamadas = 0

    def execute(self, *_args):
        self.llamadas += 1
        if self.llamadas == 1:
            return ResultadoFalso([{"autorizado": 1}])
        return ResultadoFalso([
            {
                "categoria": "tecnologia",
                "marca": "Nexus",
                "correo": "ana@example.com",
                "rut": "12.345.678-9",
                "telefono": "+56912345678",
                "tarjeta": "4111111111111111",
            }
        ])

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass


class PoolFalso:
    def __init__(self, conexion):
        self.conexion = conexion

    def connection(self):
        return self.conexion


def test_llm_429_reintenta_y_usa_respaldo(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("NVIDIA_MODELO", "modelo-de-prueba")
    monkeypatch.setattr(worker.time, "sleep", lambda _: None)

    llamadas = []

    def respuesta_429(*args, **kwargs):
        llamadas.append(1)
        return httpx.Response(
            429,
            json={"error": "Rate limit"},
            request=httpx.Request("POST", worker.NVIDIA_URL),
        )

    monkeypatch.setattr(worker.httpx, "post", respuesta_429)

    texto, intentos, error = worker.generar_texto(
        [{"categoria": "tecnologia", "marca": "Nexus"}]
    )

    assert texto is None
    assert intentos == 3
    assert error == "HTTP 429"
    assert len(llamadas) == 3


def test_llm_200_genera_texto(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("NVIDIA_MODELO", "modelo-de-prueba")

    def respuesta_200(*args, **kwargs):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": "Descubre nuestros productos."}}
                ]
            },
            request=httpx.Request("POST", worker.NVIDIA_URL),
        )

    monkeypatch.setattr(worker.httpx, "post", respuesta_200)

    texto, intentos, error = worker.generar_texto(
        [{"categoria": "tecnologia"}]
    )

    assert texto == "Descubre nuestros productos."
    assert intentos == 1
    assert error is None


def test_contexto_llm_solo_contiene_datos_comerciales(monkeypatch):
    conexion = ConexionFalsa()
    monkeypatch.setattr(worker.bd, "pool", PoolFalso(conexion))
    monkeypatch.setenv("NVIDIA_API_KEY", "clave-de-prueba")
    monkeypatch.setenv("NVIDIA_MODELO", "modelo-de-prueba")

    enviados = []

    def respuesta_200(*args, **kwargs):
        enviados.append(kwargs["json"]["messages"][1]["content"])
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Texto comercial."}}]},
            request=httpx.Request("POST", worker.NVIDIA_URL),
        )

    monkeypatch.setattr(worker.httpx, "post", respuesta_200)

    contexto = worker.datos_comerciales(7)
    texto, intentos, error = worker.generar_texto(contexto)

    assert texto == "Texto comercial."
    assert intentos == 1 and error is None
    payload = json.loads(enviados[0].split(": ", 1)[1])
    assert payload == [{"categoria": "tecnologia", "marca": "Nexus"}]
    assert not any(valor in enviados[0] for valor in (
        "ana@example.com", "12.345.678-9", "+56912345678", "4111111111111111"
    ))
