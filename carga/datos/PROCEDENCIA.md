# Procedencia de los datos tratados

Los CSV `productos_limpio.csv`, `usuarios_limpio.csv` y `transacciones_limpio.csv` provienen de `datos/procesados/` del repositorio https://github.com/Gaborilincio/modelo-nexus y se mantienen sin limpieza adicional.

Referencia de origen indicada por el equipo de IA: `bd88bc437014c86d5a0f61c73332ac8ce14868a3`.

| Archivo | Filas | SHA-256 de la copia del usuario |
| --- | ---: | --- |
| productos_limpio.csv | 1500 | `d24cab5b6fe1ce7c4f7d2ef539008d6b46729ec26e793a1d32506732d1aa947f` |
| usuarios_limpio.csv | 2077 | `7ddf41424fd7fcf11838e29976a0fd7268bbd3383fcd5563b47b1fcf40a4c110` |
| transacciones_limpio.csv | 9770 | `b185aa0024ba83be5bc8ddf4133642ee8d124f0971a91e36b6b2638615e2db8d` |

La variante local del CSV de usuarios carece únicamente del salto final respecto al archivo de origen de 114734 bytes; el contenido de sus 2077 filas es idéntico según la comprobación previa del equipo.

No se carga clickstream en esta fase de la BD operacional. El cargador admite NULL en campos opcionales; no inventa valores faltantes. Los productos con stock nulo o negativo deben excluirse de las recomendaciones en la siguiente fase (Dominio).
