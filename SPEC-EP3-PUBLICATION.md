# Especificación: publicación EP3

## Objetivo

Convertir el corte probado de `/api/predict` en cambios Git revisables y en imágenes reproducibles `:ep3`, siguiendo el flujo requerido `feat/ → dev → main`. El código desplegado en EC2 debe terminar siendo el mismo código identificado por el tag `ep3`; no se publicarán imágenes locales sin trazabilidad.

La publicación abarca cuatro repositorios:

| Repositorio | Resultado |
|---|---|
| `Gaborilincio/modelo-nexus` | IA con SageMaker y versión inmutable; workflow/tag publica `modelo-nexus:ep3` |
| `ivvnzz/nexus-dominio` | `/predict`, persistencia, Compose/Caddy sincronizados; workflow/tag publica dominio y carga `:ep3` |
| `ivvnzz/Api-GateWay-` | Enrutamiento público y tests; workflow/tag publica gateway `:ep3` |
| `JaimeBarrales/frontnexusJ` | Sin cambio funcional; workflow/tag permite reetiquetar la imagen aprobada como `:ep3` |

## Commits previstos

Los cambios previos sin relación de cada `README.md` quedan fuera de staging.

### modelo-nexus · rama existente `feat/sagemaker-real`

1. `feat(api): devolver la versión inmutable de SageMaker`
   - `app/main.py`, `app/recomendador.py`, `app/sagemaker_cliente.py`
   - `tests/test_api.py`, `tests/test_sagemaker.py`
2. `ci: publicar la imagen etiquetada ep3`
   - `.github/workflows/ci-cd.yml`
3. `docs: actualizar el despliegue de IA para ep3`
   - `README.md`

Los commits ya existentes de migración SageMaker permanecen sin reescribir.

### nexus-dominio · rama nueva `feat/api-predict-ep3` desde `origin/dev`

1. `feat(api): exponer predict con persistencia`
   - `dominio/app/main.py`, `dominio/tests/test_dominio.py`
2. `docs: registrar el contrato público de predict`
   - `README.md`, `CAPABILITY-MAP-EP3.md`, `SPEC-PREDICT-API.md`, `SPEC-EP3-PUBLICATION.md`, `tasks/`
3. `ci: publicar imágenes y compose de ep3`
   - workflow, `compose.yaml`, `Caddyfile` y configuración no secreta necesaria para reproducir EC2

### Api-GateWay- · rama nueva `feat/api-predict-ep3` desde `origin/dev`

1. `feat(gateway): enrutar la predicción pública`
   - `nginx/default.conf`, `tests/smoke.ps1`, `tests/balanceo.ps1`
2. `ci: publicar la imagen etiquetada ep3`
   - `.github/workflows/ci-cd.yml`
3. `docs: actualizar el estado del despliegue ep3`
   - `README.md`

### frontnexusJ · rama nueva `ci/etiqueta-ep3` desde `origin/dev`

1. `ci: publicar la imagen etiquetada ep3`
   - `.github/workflows/ci.yml`
2. `docs: documentar las rutas de predicción ep3`
   - `README.md`

## Flujo Git y de imágenes

Para cada repositorio:

```text
rama feat/ci
  → push
  → PR hacia dev
  → CI verde y revisión humana
  → merge a dev
  → PR dev hacia main
  → CI verde y revisión humana
  → merge a main
  → tag anotado ep3 sobre main
  → workflow publica :ep3
  → verificar digest y label org.opencontainers.image.revision
```

No se hará merge directo ni force-push. La creación de PR, merge y tag se detiene si el workflow falla.

## Comandos de verificación

### IA

```powershell
python -m pytest -q
docker build -t nexus-ia:verificacion .
```

### Dominio

```powershell
python -m unittest discover -s carga/tests -v
$env:DATABASE_URL='postgresql://nexus:nexus_test@localhost:55432/nexus'
Set-Location dominio
python -m pytest -q
```

### Gateway

```powershell
powershell -ExecutionPolicy Bypass -File .\tests\smoke.ps1
powershell -ExecutionPolicy Bypass -File .\tests\balanceo.ps1
docker build -t nexus-gateway:verificacion .
docker run --rm nexus-gateway:verificacion nginx -t
```

### Compose

```bash
docker compose -p equipo2 config --quiet
```

### Imágenes publicadas

```bash
docker buildx imagetools inspect ghcr.io/OWNER/IMAGE:ep3
docker image inspect ghcr.io/OWNER/IMAGE:ep3 --format '{{ index .Config.Labels "org.opencontainers.image.revision" }}'
```

## Estructura y estilo

- Se conserva un repositorio por servicio y sus workflows existentes.
- Los workflows amplían el soporte de tags de `ep2` a `ep2` y `ep3`; no duplican jobs completos.
- El nombre del tag se obtiene de `github.ref_name`/`GITHUB_REF_NAME`; no se incrusta `ep3` en varios pasos.
- Las imágenes de `main` siguen teniendo SHA/revisión OCI; `:ep3` es un alias inmutable del artefacto aprobado.
- El Compose no contiene secretos ni access keys. `SAGEMAKER_MODEL_VERSION` sí se versiona porque identifica un recurso, no una credencial.

## Estrategia de pruebas

1. Validar sintaxis y condiciones de cada workflow antes de commit.
2. Ejecutar suites locales ya establecidas antes de push.
3. Abrir PR a `dev` y esperar todos los checks; no silenciar ni omitir pruebas.
4. Tras merge a `main`, comprobar imágenes por digest y revisión OCI.
5. Actualizar EC2 para usar `ghcr.io/...:ep3`, recrear solo servicios cuya imagen cambió y repetir la prueba HTTPS.

## Límites

### Siempre

- Revisar `git diff --staged` y buscar secretos antes de cada commit.
- Mantener commits atómicos por repositorio y preocupación.
- Conservar los cambios previos de README sin incluirlos ni descartarlos.
- Mantener la identidad Git configurada; no atribuir commits a otra persona.
- Esperar CI verde antes de cada merge/tag.
- Conservar las imágenes locales de rollback hasta verificar GHCR.

### Preguntar antes

- Push de cada rama.
- Crear o fusionar PR.
- Crear/pushear el tag `ep3`.
- Cambiar EC2 desde imágenes locales a GHCR `:ep3`.
- Incluir cambios previos de README.

### Nunca

- Force-push, reescritura de commits publicados o commit directo a `main`/`dev`.
- Saltar CI, borrar tests o reducir sus aserciones.
- Publicar `.env`, PEM, claves AWS/NVIDIA o contraseñas.
- Usar `docker compose down -v`.
- Crear commits bajo la identidad de otro integrante para simular participación.

## Criterios de éxito

1. Cada cambio está en un commit atómico; los README quedan en commits documentales separados y coherentes con el despliegue.
2. Cada repositorio sigue `feat/ci → dev → main` con checks verdes.
3. Los tags `ep3` apuntan a `main` aprobado y publican las cinco imágenes propias: IA, dominio, carga, gateway y front.
4. Cada imagen `:ep3` tiene digest verificable y label OCI de revisión correspondiente al tag.
5. El Compose versionado usa imágenes `:ep3`, Caddy/HTTPS, SageMaker y la versión activa sin secretos.
6. EC2 ejecuta las imágenes GHCR `:ep3` y `/api/predict` mantiene 200, versión y persistencia.
7. Hay evidencia real de autores/PR; no se falsifica el requisito de participación.

## Preguntas abiertas

1. Resuelto: todos los commits de este corte se crearán como `Gaborilincio <ga.mendez@duocuc.cl>`; el usuario confirmó que tiene permisos de push en los repositorios del equipo.
2. Resuelto: los cuatro README se actualizarán y publicarán en commits documentales separados para que concuerden con EP3.
3. Resuelto: el cambio mínimo del front también será de `Gaborilincio`. Esto no acredita participación de los demás integrantes, que deberán aportar sus propios commits y PR.
