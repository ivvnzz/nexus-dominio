# Tareas: `predict-api`

## Tarea 1: Confirmar versión activa de SageMaker

**Descripción:** Consultar el endpoint y su configuración en `us-east-1` para obtener el nombre inmutable del modelo que debe registrar cada predicción.

**Aceptación:**
- [x] `nexus-reco` está `InService`.
- [x] Se registra endpoint config y modelo activo sin exponer credenciales.

**Verificación:**
- [x] `aws sagemaker describe-endpoint` y `describe-endpoint-config` coinciden.

**Dependencias:** ninguna.

**Archivos:** ninguno; evidencia local no secreta si corresponde.

**Tamaño:** XS.

## Tarea 2: Propagar la versión desde la IA

**Descripción:** Añadir pruebas y el mínimo código para que la respuesta de IA incluya el modelo inmutable configurado mediante `SAGEMAKER_MODEL_VERSION`.

**Aceptación:**
- [x] Respuesta principal y fallback de SageMaker incluyen `version_modelo`.
- [x] Una configuración remota incompleta no se presenta como versión válida.
- [x] El modo local de desarrollo conserva un identificador explícito y comprobable.

**Verificación:**
- [x] `python -m pytest -q` en `modelo-nexus` (31 pruebas pasan).

**Dependencias:** Tarea 1.

**Archivos probables:**
- `app/main.py`
- `app/recomendador.py`
- `tests/test_api.py`
- `tests/test_sagemaker.py`

**Tamaño:** M.

## Checkpoint 1: IA

- [x] Pruebas completas verdes.
- [x] La versión retornada coincide con AWS.
- [x] Diff revisado y sin secretos.

## Tarea 3: Exponer `/predict` persistente en el dominio

**Descripción:** Probar y registrar el nuevo contrato HTTP 200 reutilizando el flujo de `/predicciones`.

**Aceptación:**
- [x] `/predict` responde 200, persiste entrada/resultado/versión y devuelve su ID.
- [x] Una entrada inválida devuelve 422 sin invocar la IA.
- [x] `/predicciones` sigue respondiendo 201.

**Verificación:**
- [x] `python -m pytest -q` desde `dominio/` con PostgreSQL cargado (10 pruebas pasan).

**Dependencias:** Tarea 2.

**Archivos probables:**
- `dominio/app/main.py`
- `dominio/tests/test_dominio.py`

**Tamaño:** S.

## Checkpoint 2: Dominio

- [x] Pruebas completas verdes.
- [x] No hay migración SQL.
- [x] Contrato EP2 preservado.

## Tarea 4: Publicar la ruta en el gateway

**Descripción:** Añadir la prueba y el `location` exacto que envía `/api/predict` al `/predict` del dominio.

**Aceptación:**
- [x] `POST /api/predict` llega al dominio sin reescritura incorrecta.
- [x] Una ruta API desconocida sigue respondiendo 404.
- [x] No se publican puertos adicionales.

**Verificación:**
- [x] Ejecutar smoke (53 comprobaciones) y balanceo (61 comprobaciones) con stubs.

**Dependencias:** Tarea 3.

**Archivos probables:**
- `nginx/default.conf`
- `tests/smoke.ps1`
- `tests/compose.stubs.yaml` solo si el stub actual no permite comprobar el contrato.

**Tamaño:** S.

## Checkpoint 3: Ruta pública local

- [x] Tests de IA, dominio y gateway verdes.
- [x] Flujo completo disponible en contenedores locales o stubs.
- [x] Diffs de los tres repositorios revisados.

## Tarea 5: Desplegar el corte mínimo en EC2

**Descripción:** Comparar y sincronizar cambios, configurar la versión confirmada y recrear solo IA, dominio y gateway.

**Aceptación:**
- [x] `docker compose -p equipo2 config --quiet` pasa.
- [x] Servicios afectados quedan healthy y los demás no pierden datos ni certificados.
- [x] La configuración desplegada referencia las imágenes/código recién probado.

**Verificación:**
- [x] `docker compose -p equipo2 ps -a` y logs acotados sin secretos.

**Dependencias:** Tarea 4.

**Archivos remotos probables:**
- `/home/ubuntu/nexus-dominio/compose.yaml`
- Código o imágenes de IA, dominio y gateway según el método de despliegue existente.

**Tamaño:** M.

## Tarea 6: Verificar HTTPS y persistencia real

**Descripción:** Ejecutar la prueba de aceptación desde el borde y comprobar la fila en PostgreSQL.

**Aceptación:**
- [x] `POST /api/predict` devuelve 200, 4–8 productos y versión inmutable correcta.
- [x] La fila guardada coincide con ID, entrada, resultado y versión.
- [x] Entrada inválida da 422; health y ruta EP2 continúan funcionando.

**Verificación:**
- [x] Peticiones HTTPS con validación del certificado.
- [x] Consulta acotada de la predicción por ID en PostgreSQL.

**Dependencias:** Tarea 5.

**Archivos:** evidencia de salida sin datos personales ni secretos.

**Tamaño:** S.

## Checkpoint final

- [x] Criterios de `SPEC-PREDICT-API.md` completos.
- [x] No se ejecutó `down -v` ni se cambiaron secretos.
- [x] Cambios listos para revisión humana antes de commit/push/publicación.

---

# Tareas: `ep3-publication`

## Tarea 7: Preparar ramas de publicación

**Aceptación:**
- [x] Dominio y gateway están en `feat/api-predict-ep3` desde `origin/dev`.
- [x] Front está en `ci/etiqueta-ep3` desde `origin/dev`.
- [x] IA conserva `feat/sagemaker-real`; ningún cambio local desaparece.

**Verificación:** `git status`, `git log --graph` y `git diff` por repositorio.

**Dependencias:** checkpoint final de `predict-api`.

## Tarea 8: Crear commits de IA

**Aceptación:**
- [x] Contrato de versión, workflow EP3 y README están en tres commits separados.
- [x] README previo queda actualizado, no descartado.

**Verificación:** 31 pruebas, build de imagen, `git show --stat` por commit.

**Dependencias:** Tarea 7.

## Tarea 9: Crear commits de dominio

**Aceptación:**
- [x] API, documentación y despliegue/CI están separados.
- [x] Compose/Caddy reproducen AWS sin secretos y usan imágenes `:ep3`.

**Verificación:** 10 pruebas de dominio, 6 de carga, `docker compose config --quiet`.

**Dependencias:** Tarea 7.

## Tarea 10: Crear commits de gateway

**Aceptación:**
- [x] Ruta/tests, workflow EP3 y README están separados.
- [x] Workflow conserva soporte de `ep2`.

**Verificación:** 53 smoke, 61 balanceo, `nginx -t`.

**Dependencias:** Tarea 7.

## Tarea 11: Crear commits de front

**Aceptación:**
- [x] Workflow publica tags `ep2` y `ep3` sin duplicar lógica.
- [x] README describe rutas 200/201 actuales.

**Verificación:** tests existentes del front y build Docker.

**Dependencias:** Tarea 7.

## Checkpoint 4: Commits locales

- [x] Todos los commits nuevos pertenecen a Gaborilincio.
- [x] Diffs y secretos revisados; suites verdes.
- [ ] Usuario revisa historial antes del push.

## Tarea 12: Push y PR hacia dev

**Aceptación:**
- [ ] Cuatro ramas publicadas y cuatro PR hacia `dev`.
- [ ] Todos los checks requeridos verdes.

**Verificación:** URLs y estados de GitHub Actions.

**Dependencias:** Checkpoint 4 y aprobación explícita.

## Tarea 13: Promover dev hacia main

**Aceptación:**
- [ ] PR de feature fusionados a `dev`.
- [ ] PR `dev → main` fusionados con CI verde.

**Verificación:** SHA de cada `origin/main` y workflows.

**Dependencias:** Tarea 12 y aprobación explícita.

## Tarea 14: Publicar y verificar imágenes ep3

**Aceptación:**
- [ ] Tags `ep3` en los cuatro repositorios.
- [ ] IA, dominio, carga, gateway y front `:ep3` disponibles con revisión OCI correcta.

**Verificación:** `docker buildx imagetools inspect` y labels de revisión.

**Dependencias:** Tarea 13 y aprobación explícita.

## Tarea 15: Desplegar imágenes trazables

**Aceptación:**
- [ ] EC2 usa GHCR `:ep3`, no imágenes locales de desarrollo.
- [ ] `/api/predict` mantiene 200, versión, persistencia y 422; servicios healthy.

**Verificación:** Compose, imágenes/digests, HTTPS y PostgreSQL.

**Dependencias:** Tarea 14 y aprobación explícita.

## Checkpoint final de publicación

- [ ] Código, tag, imagen y EC2 son trazables al mismo commit.
- [ ] Rollback disponible y recursos persistentes intactos.
