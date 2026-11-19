# Mapa de capacidades críticas EP3

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `predict-api` | Exponer `POST /api/predict`, persistir la predicción y devolver la versión real del modelo desplegado en SageMaker | Despliegue EP2 y endpoint `nexus-reco` |
| `ep3-publication` | Sincronizar el código desplegado, probarlo, publicar imágenes `:ep3` y completar el flujo `feat/ → dev → main` sin perder cambios previos | `predict-api` |

Orden: `predict-api` → `ep3-publication`.
