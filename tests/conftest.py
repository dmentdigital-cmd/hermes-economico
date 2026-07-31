"""Asegura que la raíz del repo esté en sys.path para poder importar
env_loader.py y evolution_client.py desde tests/ sin instalar el proyecto
como paquete (no hay setup.py/pyproject: cero dependencias nuevas)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
