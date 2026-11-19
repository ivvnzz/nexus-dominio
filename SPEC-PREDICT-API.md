# Especificación: API pública de predicción EP3

## Objetivo

Exponer detrás del gateway HTTPS `POST /api/predict` para la revisión de avance EP3. La ruta reutiliza el flujo existente del dominio: valida `usuario_id` y `k`, llama al microservicio de IA que puntúa con `nexus-reco`, aplica stock y respaldo, guarda entrada y resultado en PostgreSQL y responde HTTP 200.

La respuesta debe identificar la versión inmutable del modelo de SageMaker que atendió la predicción, no solamente la familia del algoritmo, la fecha de corte o el nombre estable del endpoint. Para el despliegue actual esa versión es el nombre del modelo asociado a la configuración activa de `nexus-reco`.

## Contrato

Petición válida:

```http
POST /api/predict
Content-Type: application/json

{"usuario_id":"U100406","k":8}
```

Respuesta principal:

```json
{
  "id": 123,
  "fecha": "2026-11-19T01:30:00+00:00",
  "version_modelo": "nexus-reco-20261119-012857",
  "usuario_id": "U100406",
  "origen": "modelo",
  "motivo": null,
  "recomendaciones": [],
  "atendido_por": "dominio-1",
  "ia_ms": 150,
  "total_ms": 170
}
```

- Estado válido: HTTP 200.
- `k`: entero entre 4 y 8; valor predeterminado 8.
- Entrada ausente, vacía o con tipo/rango incorrecto: HTTP 422 con detalle de FastAPI.
- Cada respuesta, incluso el respaldo, se persiste en `predicciones` con entrada, resultado, origen, versión y fecha.
- Cuando SageMaker produce los puntajes, `version_modelo` es el modelo inmutable configurado en el endpoint.
- Cuando se usa el respaldo del dominio, se conserva `version_modelo: "respaldo-dominio"` y el motivo.
- La ruta EP2 `/api/dominio/predicciones` conserva su comportamiento y HTTP 201.

## Stack técnico

- FastAPI/Pydantic en `dominio/` y `modelo-nexus`.
- PostgreSQL 16 y psycopg; se reutiliza la tabla `predicciones` sin migración.
- Nginx como gateway; Caddy mantiene HTTPS delante del gateway.
- boto3 invoca el endpoint serverless de SageMaker mediante `LabInstanceProfile`.

## Comandos

Pruebas del dominio con una base cargada:

```powershell
$env:DATABASE_URL='postgresql://nexus:nexus_dev@localhost:5432/nexus'
Set-Location dominio
python -m pytest -q
```

Validación del gateway:

```powershell
docker compose -f tests/compose.stubs.yaml up -d --build
pwsh -File tests/smoke.ps1
docker compose -f tests/compose.stubs.yaml down
```

Validación del modelo:

```powershell
python -m pytest -q
```

Validación de Compose en EC2:

```bash
cd ~/nexus-dominio
docker compose -p equipo2 config --quiet
docker compose -p equipo2 ps -a
```

## Estructura y alcance

- `dominio/app/main.py`: alias HTTP 200 que reutiliza una única implementación de predicción.
- `dominio/tests/test_dominio.py`: contrato HTTP 200, persistencia, versión y validación.
- `modelo-nexus/app/`: propagar en la respuesta la versión configurada del modelo SageMaker.
- `modelo-nexus/tests/`: comprobar versión de modelo principal y respaldo.
- `api-gateway/nginx/default.conf`: enrutar exactamente `/api/predict` al dominio sin exponer puertos nuevos.
- `api-gateway/tests/`: comprobar la ruta pública y que las rutas desconocidas siguen en 404.
- `compose.yaml` desplegado: proporcionar la versión inmutable que corresponde a la configuración activa del endpoint.

No se cambia el esquema SQL, no se agrega Redis y no se duplica la lógica de recomendación o persistencia.

## Estilo de código

Se mantienen nombres y respuestas en español, tipado existente y funciones pequeñas. La ruta nueva debe delegar en la implementación compartida, por ejemplo:

```python
@app.post("/predict")
def predecir(p: PeticionPrediccion):
    return crear_prediccion(p)
```

La forma final puede evitar incluso esa función si FastAPI permite registrar la misma implementación con ambos contratos sin alterar el 201 de EP2.

## Estrategia de pruebas

1. Escribir primero pruebas rojas para `/predict` HTTP 200 y la versión inmutable.
2. Verificar que la fila persistida coincide con la respuesta.
3. Verificar 422 para campo faltante, tipo incorrecto y `k` fuera de rango.
4. Mantener verdes las pruebas existentes de `/predicciones`, fallback, consentimiento y stock.
5. Probar el enrutamiento del gateway con stubs.
6. Tras desplegar, hacer una petición HTTPS real y consultar la fila guardada sin imprimir secretos.

## Límites

### Siempre

- Reutilizar persistencia y reglas EP2 existentes.
- Ejecutar pruebas antes de cualquier commit o despliegue.
- Preservar volúmenes, contraseña, certificados y variables secretas.
- Obtener credenciales AWS mediante el rol de EC2.
- Revisar el diff de los tres repositorios y los archivos remotos antes de sincronizar.

### Preguntar antes

- Hacer commit, push, PR, merge, tag `ep3` o publicar imágenes.
- Recrear más servicios que gateway, dominio o IA.
- Cambiar el esquema de PostgreSQL o el endpoint de SageMaker.

### Nunca

- Ejecutar `docker compose down -v`.
- Añadir `.env`, credenciales AWS, claves NVIDIA o el PEM a Git.
- Sobrescribir los cambios previos de README o los archivos remotos sin compararlos.
- Romper las rutas EP2 durante la transición.

## Criterios de éxito

1. `POST https://52-1-100-14.sslip.io/api/predict` devuelve HTTP 200 con 4–8 recomendaciones, `id`, `fecha`, `origen` y `version_modelo`.
2. En flujo de modelo, la versión coincide con el modelo inmutable asociado a la configuración activa de `nexus-reco`.
3. La predicción queda en PostgreSQL con la misma entrada, resultado y versión.
4. Una entrada inválida devuelve 422 con detalle y no invoca la IA.
5. La ruta EP2 conserva HTTP 201 y sus pruebas existentes.
6. Gateway, dominio e IA pasan sus pruebas; `docker compose config --quiet` pasa en EC2.
7. Solo se recrean los servicios estrictamente afectados y HTTPS continúa válido.

## Fuera de alcance de este módulo

- Autenticación, rate limiting, `/api/health`, `/api/predicciones/{id}` y `/docs` público.
- RabbitMQ, worker NVIDIA, campañas y anonimización.
- Locust, dashboard, informe y láminas.
- Publicación y merges, cubiertos después por `ep3-publication`.

## Pregunta abierta

- Confirmar si la versión se configurará explícitamente en el contenedor (`SAGEMAKER_MODEL_VERSION`) o si la IA consultará al iniciar la configuración activa del endpoint. Se recomienda la variable explícita: es mínima, no añade una llamada de control a AWS y permite comprobar con el despliegue que coincide con `nexus-reco-20261119-012857`.
