# F1 — Esquema PostgreSQL y cargador idempotente

## Alcance

- `carga/sql/esquema.sql` ya existe en el repositorio del estudiante, creado a partir del diseño revisado con Claude. **Este paquete NO lo reemplaza.**
- `carga/cargar.py`: carga los tres CSV tratados en una sola transacción.
- `carga/transformaciones.py`: convierte valores vacíos a `NULL`, campos numéricos `.0`, bool y fechas.
- `carga/tests/test_cargar.py`: pruebas automáticas de conversiones, conteos e integridad referencial.
- `carga/Dockerfile`: futura imagen `nexus-carga`, para usar en Compose final.
- `carga/datos/PROCEDENCIA.md`: referencia a datos y huellas SHA-256.

## Requisitos previos

- En la raíz `nexus-dominio`, CSV reales (no vacíos) en `carga/datos/`.
- `carga/sql/esquema.sql` con las seis tablas definidas por Claude.
- PostgreSQL de prueba encendido con el nombre `pg-nexus-test`, puerto Windows 5433.
- Python 3.13 instalado en Windows.

## Comandos PowerShell (desde la raíz del repositorio)

```powershell
py -m pip install -r .\carga\requirements.txt
py -m unittest discover -s carga/tests -v
$env:DATABASE_URL = 'postgresql://nexus:nexus_dev@127.0.0.1:5433/nexus'
py -m carga.cargar
```

La primera carga debería mostrar 1500 productos, 2077 usuarios y 9770 transacciones **nuevas**, si las tablas estaban vacías. Vuelve a ejecutar:

```powershell
py -m carga.cargar
```

La segunda ejecución debería mostrar **0 nuevas** en las tres tablas y 1500/2077/9770 **existentes** respectivamente.

Consulta de comprobación (PowerShell):

```powershell
docker exec pg-nexus-test psql -U nexus -d nexus -c 'SELECT (SELECT count(*) FROM productos) AS productos, (SELECT count(*) FROM usuarios) AS usuarios, (SELECT count(*) FROM transacciones) AS transacciones;'
docker exec pg-nexus-test psql -U nexus -d nexus -c 'SELECT tabla, filas_insertadas, filas_ya_existentes FROM auditoria_carga ORDER BY id;'
```

`auditoria_carga` debe tener seis filas luego de dos ejecuciones exitosas (tres por ejecución).

## Prueba de imagen Docker opcional

```powershell
docker build -f carga/Dockerfile -t nexus-carga:local .
```

Cuando se cree el Compose definitivo, el cargador recibirá `DATABASE_URL` por entorno y será un servicio de ejecución única con `restart: "no"`.

## Notas para el siguiente desarrollador

- El cargador **falla completo** si faltan claves, hay duplicados, referencias huérfanas o valores requeridos inválidos; no pierde filas silenciosamente.
- `ON CONFLICT DO NOTHING` evita duplicados: **no actualiza** filas previamente cargadas. Una actualización de fuente requerirá una estrategia de refresh explícita.
- No almacena estado local entre ejecuciones; el advisory lock evita dos cargadores simultáneos sobre la misma BD.
- En producción, no usar `nexus_dev` como contraseña y no publicar PostgreSQL hacia el host.
- La aplicación Dominio será responsable de las recomendaciones, fallback, y almacenar predicciones en próximas fases; **F1 aún no implementa la API**.
