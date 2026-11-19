# Plan de implementación: `predict-api`

## Resumen

Completar una ruta vertical mínima desde SageMaker hasta HTTPS: la IA devuelve la versión inmutable configurada del modelo, el dominio reutiliza su flujo persistente con un contrato HTTP 200 y el gateway publica exactamente `POST /api/predict`. Después se valida en AWS sin borrar volúmenes ni recrear servicios ajenos.

## Dependencias

```text
Confirmar modelo activo en AWS
        ↓
IA propaga version_modelo
        ↓
Dominio expone /predict y persiste la versión
        ↓
Gateway publica /api/predict
        ↓
Despliegue mínimo y prueba HTTPS + PostgreSQL
```

## Decisiones de arquitectura

- `SAGEMAKER_MODEL_VERSION` identifica el modelo inmutable asociado a la configuración activa. El arranque falla de forma visible si hay endpoint remoto pero falta la versión, evitando guardar una versión inventada.
- El endpoint estable `nexus-reco` no se usa como versión porque puede apuntar a distintos modelos a lo largo del tiempo.
- El dominio conserva una sola implementación del flujo de predicción; `/predicciones` mantiene 201 y `/predict` responde 200.
- PostgreSQL y la tabla `predicciones` ya satisfacen la persistencia; no habrá migración.
- Nginx enruta solo la ruta pública exacta. No se abre ningún puerto adicional.
- Los tres repositorios se modifican y prueban por separado. No se hace commit, push, merge, tag ni publicación de imagen durante este módulo sin aprobación posterior.

## Fases

### Fase 1: contrato de versión en la IA

1. Confirmar mediante AWS que la configuración activa de `nexus-reco` usa `nexus-reco-20261119-012857`, o registrar el nombre vigente si cambió.
2. Escribir pruebas rojas para exigir `version_modelo` en respuestas de modelo y fallback cuando la IA está configurada con SageMaker.
3. Implementar la propagación mínima desde `SAGEMAKER_MODEL_VERSION` y mantener el contrato de salud.

### Punto de control 1

- Todas las pruebas de `modelo-nexus` pasan.
- La versión retornada coincide con el recurso activo de AWS.
- No se añadieron credenciales ni llamadas de control innecesarias.

### Fase 2: dominio persistente HTTP 200

4. Escribir pruebas rojas para `/predict`: HTTP 200, versión, persistencia y 422.
5. Registrar `/predict` reutilizando la implementación existente y preservar `/predicciones` HTTP 201.

### Punto de control 2

- Todas las pruebas del dominio pasan contra PostgreSQL real e IA simulada.
- Ambos contratos, nuevo y heredado, conservan sus códigos HTTP.
- No hay cambio de esquema.

### Fase 3: ruta pública

6. Añadir primero una prueba de gateway para `POST /api/predict` y luego el enrutamiento exacto al dominio.
7. Ejecutar smoke tests del gateway y confirmar que `/api/*` desconocidas continúan en 404.

### Punto de control 3

- Gateway pasa sus pruebas.
- La ruta pública no pasa por el frontend ni queda atrapada por el 404 genérico.
- No se exponen nuevos puertos.

### Fase 4: despliegue y evidencia

8. Comparar código local con `/home/ubuntu/nexus-dominio` y `/home/ubuntu/nexus-sagemaker`; aplicar únicamente los cambios revisados.
9. Construir o cargar las tres imágenes afectadas, actualizar la versión en Compose y recrear únicamente IA, dominio y gateway en orden seguro.
10. Probar HTTPS: respuesta 200, 4–8 productos, versión real, 422 inválido y persistencia de la fila; comprobar health y rutas EP2.

### Punto de control final

- Todos los criterios de `SPEC-PREDICT-API.md` están demostrados.
- HTTPS y servicios no afectados siguen operativos.
- El diff queda listo para revisión antes del módulo `ep3-publication`.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| El modelo activo cambió | Se guarda una versión falsa | Consultar AWS antes de configurar y contrastar tras desplegar |
| Código remoto distinto del local | Se pierde una corrección del servidor | Comparar archivos/diffs antes de copiar; no sobrescribir a ciegas |
| Dos réplicas del dominio mezclan imágenes | Resultados inconsistentes | Recrear el servicio completo y comprobar `X-Replica` varias veces |
| Cold start de SageMaker supera el timeout | Primera respuesta usa fallback | Calentar antes de la prueba y aceptar fallback controlado sin falsear la evidencia |
| Cambios previos en README | Trabajo del usuario sobrescrito | No tocar ni incluir esos cambios en commits automáticos |
| Gateway nuevo no está publicado | La ruta externa sigue en 404 | Probar el contenedor exacto que se despliega antes de recrearlo |

## Fuera del plan

Autenticación, rate limiting, LLM, campañas, anonimización, API agregada de salud, consulta por ID, Swagger público, carga y publicación Git `ep3`.

---

# Plan de implementación: `ep3-publication`

## Resumen

Publicar el corte probado como commits atómicos de `Gaborilincio`, llevarlo por `feat/ci → dev → main`, crear el tag `ep3`, verificar las imágenes GHCR y reemplazar en EC2 las imágenes locales por artefactos trazables. Los README se incluyen en commits documentales separados.

## Dependencias

```text
Ramas limpias desde origin/dev
        ↓
Commits funcionales y documentales por repositorio
        ↓
Workflows compatibles con tag ep3
        ↓
Push + PR a dev + CI verde
        ↓
PR dev a main + CI verde
        ↓
Tag ep3 + imágenes GHCR verificadas
        ↓
Compose con :ep3 + despliegue EC2 + prueba HTTPS
```

## Decisiones

- Todos los commits del corte usan la identidad Git ya configurada: `Gaborilincio <ga.mendez@duocuc.cl>`.
- No se reescriben los dos commits existentes de `feat/sagemaker-real`.
- Los workflows agregan `ep3` sin retirar compatibilidad con `ep2`.
- El tag publicado se obtiene dinámicamente de `GITHUB_REF_NAME`; un mismo job sirve para ambas entregas.
- Front no cambia funcionalmente: solo documentación y capacidad de publicar el artefacto existente como `:ep3`.
- Las imágenes locales `ep3-predict` se conservan para rollback hasta terminar la verificación de GHCR.

## Fases

### Fase 1: preparar ramas y commits locales

1. Crear ramas de dominio, gateway y front desde `origin/dev`, conservando únicamente los cambios previstos.
2. Crear los commits de IA: contrato de versión, workflow EP3 y README.
3. Crear los commits de dominio: API, documentación y Compose/workflow EP3 sincronizados con EC2.
4. Crear los commits de gateway: ruta/tests, workflow EP3 y README.
5. Crear los commits de front: workflow EP3 y README.

### Punto de control local

- Revisar historial, contenido de cada commit, autor y ausencia de secretos.
- Ejecutar las suites afectadas después de los cambios de workflow/Compose.
- Mostrar ramas y commits antes de cualquier push.

### Fase 2: flujo remoto

6. Con aprobación, pushear ramas y abrir PR individuales hacia `dev`.
7. Esperar CI verde; corregir por commits adicionales, nunca omitiendo checks.
8. Con aprobación, fusionar PR a `dev`, abrir PR `dev → main` y esperar CI verde.

### Punto de control de main

- Confirmar que `main` contiene exactamente el corte aprobado en cada repositorio.
- Verificar que cada workflow de `main` publicó imagen SHA/revisión OCI.

### Fase 3: release e imágenes

9. Con aprobación, crear y pushear tag anotado `ep3` sobre cada `main`.
10. Esperar workflows y verificar digest/revisión OCI de IA, dominio, carga, gateway y front.
11. Actualizar el Compose versionado y EC2 a imágenes GHCR `:ep3`; recrear solo servicios afectados.
12. Repetir HTTP 200, 422, persistencia, versión, health, HTTPS y rollback disponible.

## Riesgos y mitigaciones

| Riesgo | Impacto | Mitigación |
|---|---|---|
| Cambios sin commit se pierden al cambiar de rama | Alto | Revisar diff, crear ramas con working tree intacto y comprobar tras cada switch |
| Permisos insuficientes en repos de terceros | Alto | Detenerse ante el primer rechazo; no cambiar remotos ni usar force-push |
| Tag dispara una imagen distinta al commit probado | Alto | Verificar digest y label OCI contra SHA de `main`/tag |
| Workflow hardcodeado a `ep2` | Medio | Generalizar con nombre de tag y validar condiciones antes de push |
| Compose remoto y local divergen | Alto | Sincronizar Caddy/SageMaker desde EC2 excluyendo secretos y validar `compose config` |
| Otros integrantes no cumplen autoría | Académico alto | Documentar que estos commits solo acreditan a Gaborilincio |

## Fuera del plan

Worker LLM, autenticación, rate limiting y demás brechas funcionales EP3; comienzan después de estabilizar las imágenes `:ep3`.
