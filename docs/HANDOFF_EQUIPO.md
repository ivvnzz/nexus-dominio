# Traspaso a compañeros — Nexus Retail EP2

## Estado y responsabilidades

- Repositorio `ivvnzz/nexus-dominio`, rama de trabajo `feat/esquema-y-carga`.
- API Gateway ya publicada como `ghcr.io/ivvnzz/nexus-gateway:ep2`.
- **F1:** PostgreSQL schema, cargador e idempotencia. No marcarla aprobada hasta verificar en el Docker Desktop de quien desarrolla.
- **F2:** API REST FastAPI en puerto 3000; `GET /health`, `GET /usuarios`, `GET /usuarios/{id}/compras`, `GET /predicciones`.
- **F3:** `POST /predicciones` integrando IA `http://ia:8000/predict`, stock, consentimientos, fallback y persistencia.
- **F5:** Dockerfile para Dominio, CI/CD y dos imágenes GHCR públicas (`nexus-dominio`, `nexus-carga`).
- **F6/F8:** integración con Gateway real, dos réplicas, Compose final de seis servicios e informe.

## Acuerdos Gitflow

- **Cada compañero que implemente una funcionalidad debe hacerlo desde su cuenta** y abrir su propio PR `feat/*` hacia `dev` (el enunciado pide dos PR feat→dev por integrante).
- No escribir en `main` ni `dev` directamente.
- Antes de una rama nueva: `git switch dev; git pull origin dev; git switch -c feat/nombre`.
- Evitar que dos compañeros editen el mismo archivo sin coordinación.
- No modificar el API Gateway `ep2` salvo necesidad técnica justificada.
- Las variables de entorno con contraseñas no se suben; usar `.env.example`.

## Cómo dar acceso a colaboradores

GitHub → repositorio `nexus-dominio` → **Settings → Collaborators and teams** (o **Collaborators**) → Add people → invitar usuario GitHub. En repositorios públicos, también pueden hacer fork y abrir PR sin ser colaboradores.

## Para el responsable de Dominio

Primero comprobar que F1 se ejecuta y que la BD guarda 1.500 productos, 2.077 usuarios y 9.770 transacciones. El contrato existente del Gateway elimina `/api/dominio/` al reenviar: `POST /api/dominio/predicciones` llega a Dominio como `POST /predicciones`.

No afirmar que la IA real o Front están integrados hasta haber ejecutado la prueba correspondiente.
