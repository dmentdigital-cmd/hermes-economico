#!/usr/bin/env python3
"""Carga y parseo de un archivo .env con la biblioteca estándar de Python.

Decisión explícita del usuario (ver STACK-PROFILE-hermes-economico.md,
sección "Backend y datos"): sin `python-dotenv`, cero dependencias nuevas.
El .env es un punto de entrada de datos más: nunca se indexa a ciegas.
"""
from pathlib import Path
from typing import Dict, Union


class EnvLoadError(Exception):
    """Se levanta cuando el .env no existe, está mal formado, o falta una
    clave requerida. El mensaje siempre dice explícitamente qué pasó."""


def load_env(path: Union[str, Path]) -> Dict[str, str]:
    """Parsea un archivo .env simple (CLAVE=VALOR) y devuelve un dict.

    Reglas de parseo:
    - Ignora líneas vacías (solo espacios en blanco).
    - Ignora líneas que empiezan con '#' (comentarios).
    - Cada línea restante debe tener forma CLAVE=VALOR; si no la tiene,
      levanta EnvLoadError identificando el número de línea y su contenido.
    - No hace expansión de variables ni manejo especial de comillas: el
      valor es todo lo que sigue al primer '=', con espacios externos
      recortados.

    Levanta EnvLoadError si el archivo no existe.
    """
    env_path = Path(path)
    if not env_path.is_file():
        raise EnvLoadError(f"No se encontró el archivo .env en: {env_path}")

    result: Dict[str, str] = {}
    contenido = env_path.read_text(encoding="utf-8")
    for numero_linea, linea_cruda in enumerate(contenido.splitlines(), start=1):
        linea = linea_cruda.strip()
        if not linea or linea.startswith("#"):
            continue
        if "=" not in linea:
            raise EnvLoadError(
                f"Línea {numero_linea} de {env_path} no tiene formato CLAVE=VALOR: {linea_cruda!r}"
            )
        clave, _, valor = linea.partition("=")
        clave = clave.strip()
        valor = valor.strip()
        if not clave:
            raise EnvLoadError(
                f"Línea {numero_linea} de {env_path} tiene una clave vacía: {linea_cruda!r}"
            )
        result[clave] = valor
    return result


def require(env_dict: Dict[str, str], key: str) -> str:
    """Devuelve env_dict[key] validado, o levanta EnvLoadError con un mensaje
    claro si la clave falta o está vacía. Nunca indexa env_dict[...] a ciegas."""
    if key not in env_dict:
        raise EnvLoadError(
            f"Falta la variable de entorno requerida '{key}' en el .env. "
            f"Agregala como '{key}=<valor>' antes de volver a correr el script."
        )
    valor = env_dict[key]
    if not valor:
        raise EnvLoadError(
            f"La variable de entorno '{key}' está presente en el .env pero vacía."
        )
    return valor
