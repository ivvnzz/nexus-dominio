# Ejecutar desde la raíz nexus-dominio:
# powershell -ExecutionPolicy Bypass -File .\scripts\verificar_f1.ps1
$ErrorActionPreference = 'Stop'

Write-Host '1/6 Verificando el repositorio y los CSV...'
if (-not (Test-Path '.\carga\sql\esquema.sql')) { throw 'Falta carga/sql/esquema.sql' }
foreach ($archivo in @('productos_limpio.csv','usuarios_limpio.csv','transacciones_limpio.csv')) {
    $ruta = Join-Path '.\carga\datos' $archivo
    if ((-not (Test-Path $ruta)) -or ((Get-Item $ruta).Length -eq 0)) { throw "CSV ausente o vacío: $ruta" }
}

Write-Host '2/6 Instalando dependencia Python psycopg...'
py -m pip install -r .\carga\requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de psycopg' }

Write-Host '3/6 Ejecutando las seis pruebas de F1...'
py -m unittest discover -s carga/tests -v
if ($LASTEXITCODE -ne 0) { throw 'Fallaron las pruebas Python' }

Write-Host '4/6 Verificando PostgreSQL pg-nexus-test...'
docker exec pg-nexus-test pg_isready -h 127.0.0.1 -U nexus -d nexus
if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL no está listo: abre Docker Desktop y verifica el contenedor' }

$env:DATABASE_URL = 'postgresql://nexus:nexus_dev@127.0.0.1:5433/nexus'
Write-Host '5/6 Ejecutando cargador dos veces...'
py -m carga.cargar
if ($LASTEXITCODE -ne 0) { throw 'Falló la primera carga' }
py -m carga.cargar
if ($LASTEXITCODE -ne 0) { throw 'Falló la segunda carga' }

Write-Host '6/6 Validando conteos y segunda carga sin duplicados...'
$conteos = docker exec pg-nexus-test psql -U nexus -d nexus -t -A -c 'SELECT (SELECT count(*) FROM productos), (SELECT count(*) FROM usuarios), (SELECT count(*) FROM transacciones);'
if ($LASTEXITCODE -ne 0) { throw 'Error consultando PostgreSQL' }
$conteos = $conteos.Trim()
Write-Host "Conteos reales: $conteos (esperado: 1500|2077|9770)"
if ($conteos -ne '1500|2077|9770') { throw 'Los conteos no coinciden con los CSV' }
$nuevas = docker exec pg-nexus-test psql -U nexus -d nexus -t -A -c 'SELECT COALESCE(SUM(filas_insertadas),0) FROM (SELECT filas_insertadas FROM auditoria_carga ORDER BY id DESC LIMIT 3) ultimas;'
if ($LASTEXITCODE -ne 0) { throw 'Error consultando auditoría' }
if ($nuevas.Trim() -ne '0') { throw 'La segunda carga generó filas nuevas; revisa la idempotencia' }
Write-Host 'F1 APROBADA LOCALMENTE: CSV, seis pruebas, PostgreSQL, conteos e idempotencia.'
Write-Host 'NO se hizo commit ni push. Coordinarlos con ChatGPT antes de integrar dev.'
