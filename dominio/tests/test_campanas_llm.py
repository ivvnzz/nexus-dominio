
import httpx

from app import worker


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
