"""Configuración por variables de entorno. Los valores por defecto sirven para el compose.yaml."""
import os
import socket

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://nexus:nexus_dev@db:5432/nexus")
IA_URL = os.environ.get("IA_URL", "http://ia:8000").rstrip("/")
# El gateway corta a los 10 s: la IA tiene que responder antes para que el dominio alcance a usar el respaldo.
IA_TIMEOUT_S = float(os.environ.get("IA_TIMEOUT_S", "4"))
# Ventana para la lista de respaldo ("más vendidos"), igual que el fallback del modelo.
DIAS_RESPALDO = int(os.environ.get("DIAS_RESPALDO", "90"))
# Identifica a la réplica que atendió (con 2 réplicas cada contenedor tiene su propio hostname).
REPLICA = os.environ.get("HOSTNAME") or socket.gethostname()
