#!/usr/bin/env python3
"""Script demostrable de la Fase 2 de hermes-economico.

Usa env_loader + evolution_client para traer los mensajes recientes del
grupo de WhatsApp de OTRIX y reporta por stdout cuántos mensajes trajo y
cuántas llamadas HTTP hizo. NO decide "hay novedad" (eso es la Fase 3,
fuera de alcance acá) y no escribe ningún config/otrix.json.
"""
from pathlib import Path

from env_loader import EnvLoadError, load_env, require
from evolution_client import EvolutionClient, EvolutionClientError

# Constante local: este script SÍ conoce a OTRIX, evolution_client.py no.
# Nombre exacto confirmado contra la lista real de grupos de la instancia
# Evolution API en la VPS (incluye el emoji de fuego al final).
GRUPO = "Marketeros Otrix \U0001F525"

ENV_PATH = Path(__file__).resolve().parent / ".env"


def main() -> None:
    try:
        env = load_env(ENV_PATH)
        api_key = require(env, "EVOLUTION_API_KEY")
    except EnvLoadError as exc:
        print(f"Error de configuración: {exc}")
        return

    client = EvolutionClient(api_key=api_key)
    try:
        messages = client.fetch_recent_messages(GRUPO)
    except EvolutionClientError as exc:
        print(f"Error consultando Evolution API: {exc}")
        print(f"Llamadas HTTP realizadas: {client.call_count}")
        return

    print(f"Mensajes traídos del grupo '{GRUPO}': {len(messages)}")
    print(f"Llamadas HTTP realizadas: {client.call_count}")


if __name__ == "__main__":
    main()
