# nexus-dominio

Microservicio de dominio, base de datos y carga inicial del sistema de recomendación de **Nexus Retail SpA** (EP2, ITY1102). Aquí también está el `compose.yaml` que levanta el sistema completo para la defensa.

| Carpeta | Imagen | Qué hace |
|---|---|---|
| `dominio/` | `ghcr.io/ivvnzz/nexus-dominio` | API REST (FastAPI, puerto 3000). Es el único servicio que lee y escribe la base. Llama a la IA y guarda cada predicción. |
| `carga/` | `ghcr.io/ivvnzz/nexus-carga` | Se ejecuta una vez: crea el esquema y carga los CSV tratados. Si corre dos veces no duplica filas. |
| `compose.yaml` | — | Sistema completo: gateway, front, dominio (2 réplicas), IA, PostgreSQL y carga. |

## Levantar el sistema (computador de la defensa)

```bash
docker compose -p equipoNN pull
docker compose -p equipoNN up -d
```

Luego `http://localhost:8080`. Al terminar: `docker compose -p equipoNN down -v`.

## API del dominio

El gateway quita el prefijo: `POST /api/dominio/predicciones` llega como `POST /predicciones`.

| Método | Ruta | Respuesta |
|---|---|---|
| GET | `/health` | `{"status":"ok","service":"dominio","replica":"<hostname>","bd":"ok"}`; 503 si la base no responde |
| GET | `/usuarios?limite=6` | Clientes con consentimiento y compras: `[{"usuario_id","region"}]` |
| GET | `/usuarios/{id}/compras?limite=8` | Compras del cliente, de la más reciente a la más antigua |
| GET | `/predicciones?usuario_id=…&limite=5` | Predicciones guardadas del cliente |
| POST | `/predicciones` | Entrada `{"usuario_id":"U100003","k":8}` (k de 4 a 8); responde 201 |

Respuesta de `POST /predicciones`:

```json
{
  "id": 62,
  "fecha": "2026-10-17T17:23:41-03:00",
  "version_modelo": "Boosting-corte-2026-08-01",
  "usuario_id": "U100003",
  "origen": "modelo",
  "motivo": null,
  "recomendaciones": [{"puesto": 1, "sku": "NX-10899", "categoria": "gaming", "marca": "Corsair", "precio_lista": 32868.0, "puntaje": 4.92}],
  "atendido_por": "a1b2c3d4e5f6",
  "ia_ms": 98,
  "total_ms": 112
}
```

Cada respuesta trae además la cabecera `X-Replica` con el contenedor que atendió.

### Reglas de negocio

1. **Flujo principal:** el dominio llama a `http://ia:8000/predict`, quita los productos que la base marca como inactivos o sin stock (stock desconocido cuenta como sin stock), renumera los puestos y guarda la predicción en la tabla `predicciones` con su entrada, resultado, versión del modelo, réplica, tiempos y fecha.
2. **Versión del modelo:** se usa `version_modelo` de la respuesta de la IA. Si la IA no la envía, se arma desde su `/health` (`<modelo>-corte-<fecha>`).
3. **IA caída o lenta (más de `IA_TIMEOUT_S`, 4 s por defecto, menos que los 10 s del gateway):** el dominio no falla. Responde con su propia lista de respaldo (los más vendidos de los últimos 90 días de datos, sin lo que el cliente ya compró), con `origen: "fallback"`, el motivo y `version_modelo: "respaldo-dominio"`. La predicción también se guarda.
4. **Exclusión de perfilamiento:** si el cliente está en `exclusiones_perfilamiento`, no se llama a la IA y se usa la lista de respaldo.
5. **Base caída:** responde 503 `{"detail":"La base de datos no responde"}`.

### Configuración

| Variable | Por defecto |
|---|---|
| `DATABASE_URL` | `postgresql://nexus:nexus_dev@db:5432/nexus` |
| `IA_URL` | `http://ia:8000` |
| `IA_TIMEOUT_S` | `4` |
| `DIAS_RESPALDO` | `90` |

La contraseña de ejemplo `nexus_dev` solo sirve para el entorno local; ver `.env.example`.

## Pruebas

```bash
pip install -r carga/requirements.txt -r dominio/requirements-dev.txt
export DATABASE_URL=postgresql://nexus:nexus_dev@localhost:5432/nexus   # PostgreSQL de prueba
python -m unittest discover -s carga/tests -v
python -m carga.cargar && python -m carga.cargar     # la segunda vez: nuevas=0
cd dominio && python -m pytest -q                    # 9 pruebas, PostgreSQL real e IA simulada
```

## Pipeline (`.github/workflows/ci.yml`)

| Evento | Qué hace |
|---|---|
| Pull request hacia `dev` o `main` | PostgreSQL como servicio, pruebas del cargador, prueba de idempotencia, pruebas del dominio y build de las dos imágenes, sin publicar |
| Push a `main` | Lo mismo y publica `nexus-dominio` y `nexus-carga` con `sha-<commit>` y `latest` |
| Tag `ep2` sobre `main` | Publica las mismas imágenes con el tag `ep2` |

Para ver qué commit está corriendo:

```bash
docker image inspect ghcr.io/ivvnzz/nexus-dominio:ep2 --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
```

## Gitflow

`main` (lo que se entrega, solo por PR desde `dev`), `dev` (integración, solo por PR desde `feat/`) y `feat/<descripcion>` (se crea desde `dev` y se borra al integrarse).
