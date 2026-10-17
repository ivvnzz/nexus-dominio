from app import bd


def test_health_informa_base_y_replica(cliente):
    r = cliente.get("/health")
    assert r.status_code == 200
    cuerpo = r.json()
    assert cuerpo["status"] == "ok" and cuerpo["bd"] == "ok" and cuerpo["replica"]
    assert r.headers["X-Replica"] == cuerpo["replica"]


def test_usuarios_de_ejemplo_tienen_compras(cliente):
    usuarios = cliente.get("/usuarios?limite=5").json()
    assert len(usuarios) == 5
    for u in usuarios:
        assert cliente.get(f"/usuarios/{u['usuario_id']}/compras").json(), u


def test_compras_ordenadas_de_la_mas_reciente(cliente, usuario):
    filas = cliente.get(f"/usuarios/{usuario}/compras?limite=50").json()
    fechas = [f["fecha"] for f in filas]
    assert fechas == sorted(fechas, reverse=True)
    assert {"sku", "categoria", "marca", "fecha", "cantidad", "estado"} <= set(filas[0])


def test_cliente_desconocido_no_tiene_compras(cliente):
    assert cliente.get("/usuarios/NO-EXISTE/compras").json() == []


def test_prediccion_llama_a_la_ia_y_se_guarda(cliente, usuario, ia_simulada):
    r = cliente.post("/predicciones", json={"usuario_id": usuario, "k": 6})
    assert r.status_code == 201
    p = r.json()
    assert p["origen"] == "modelo" and p["version_modelo"] == "hgb-prueba"
    assert len(p["recomendaciones"]) == 6
    assert [x["puesto"] for x in p["recomendaciones"]] == list(range(1, 7))
    assert p["id"] and p["fecha"] and p["atendido_por"]

    # Quedó en la base con su entrada, resultado, versión y fecha.
    with bd.pool.connection() as c:
        fila = c.execute("SELECT * FROM predicciones WHERE id = %s", (p["id"],)).fetchone()
    assert fila["entrada"] == {"usuario_id": usuario, "k": 6}
    assert [x["sku"] for x in fila["resultado"]] == [x["sku"] for x in p["recomendaciones"]]
    assert fila["version_modelo"] == "hgb-prueba" and fila["creado_en"] is not None

    historial = cliente.get(f"/predicciones?usuario_id={usuario}&limite=1").json()
    assert historial[0]["id"] == p["id"]


def test_se_quitan_productos_sin_stock(cliente, usuario, ia_simulada):
    with bd.pool.connection() as c:
        sin_stock = c.execute("SELECT sku FROM productos WHERE COALESCE(stock,0) <= 0 LIMIT 1").fetchone()["sku"]
    from tests.conftest import recomendables

    ia_simulada["skus"] = [sin_stock] + recomendables(4)
    p = cliente.post("/predicciones", json={"usuario_id": usuario, "k": 4}).json()
    skus = [x["sku"] for x in p["recomendaciones"]]
    assert sin_stock not in skus
    assert [x["puesto"] for x in p["recomendaciones"]] == list(range(1, len(skus) + 1))


def test_ia_caida_usa_el_respaldo_del_dominio(cliente, usuario, ia_simulada):
    for modo in ("caida", "lenta", "error"):
        ia_simulada["modo"] = modo
        r = cliente.post("/predicciones", json={"usuario_id": usuario, "k": 5})
        assert r.status_code == 201, modo
        p = r.json()
        assert p["origen"] == "fallback" and "IA no disponible" in p["motivo"], modo
        assert p["version_modelo"] == "respaldo-dominio"
        assert 0 < len(p["recomendaciones"]) <= 5
        compradas = {c["sku"] for c in cliente.get(f"/usuarios/{usuario}/compras?limite=50").json()}
        assert not compradas & {x["sku"] for x in p["recomendaciones"]}


def test_exclusion_de_perfilamiento_no_llama_a_la_ia(cliente, usuario, ia_simulada):
    with bd.pool.connection() as c:
        c.execute("INSERT INTO exclusiones_perfilamiento (usuario_id) VALUES (%s) ON CONFLICT DO NOTHING", (usuario,))
    try:
        p = cliente.post("/predicciones", json={"usuario_id": usuario, "k": 4}).json()
        assert p["origen"] == "fallback" and "historial" in p["motivo"]
        assert ia_simulada["llamadas"] == 0
    finally:
        with bd.pool.connection() as c:
            c.execute("DELETE FROM exclusiones_perfilamiento WHERE usuario_id = %s", (usuario,))


def test_validacion_de_entrada(cliente, ia_simulada):
    assert cliente.post("/predicciones", json={"usuario_id": "U1", "k": 3}).status_code == 422
    assert cliente.post("/predicciones", json={"usuario_id": "U1", "k": 9}).status_code == 422
    assert cliente.post("/predicciones", json={"usuario_id": ""}).status_code == 422
    assert ia_simulada["llamadas"] == 0
