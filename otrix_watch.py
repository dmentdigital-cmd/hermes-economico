#!/usr/bin/env python3
"""Wrapper de cron para OTRIX (Fase 4 de hermes-economico).

Punto de entrada que efectivamente registra el cron en la VPS: invoca al
motor genérico `project_digest.py` con la config de OTRIX, vía
`subprocess.run` (no import), para que una excepción no controlada dentro
del motor no tumbe este proceso ni deje un traceback a medio imprimir sin
código de salida. stdout/stderr del subproceso se heredan tal cual (sin
capturar), así el cron ve la misma salida que si invocara al motor
directo. El código de salida del subproceso se propaga como código de
salida de este script, para que el cron pueda distinguir éxito de error.

Rutas resueltas siempre relativas a la ubicación de este archivo, nunca
hardcodeadas: el repo debe funcionar sin importar en qué carpeta esté
clonado.
"""
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
PROJECT_DIGEST_PATH = REPO_ROOT / "project_digest.py"
CONFIG_PATH = REPO_ROOT / "config" / "otrix.json"


def main() -> None:
    resultado = subprocess.run(
        [sys.executable, str(PROJECT_DIGEST_PATH), str(CONFIG_PATH)]
    )
    sys.exit(resultado.returncode)


if __name__ == "__main__":
    main()
