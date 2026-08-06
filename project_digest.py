#!/usr/bin/env python3
"""Motor genérico de recolección de novedades (Fase 3 de hermes-economico).

Lee la config de un proyecto (`config/<proyecto>.json`), pide a Evolution API
los mensajes recientes de su grupo de WhatsApp, los compara contra el estado
guardado de la corrida anterior y contra las palabras clave del proyecto, y
decide entre "hay novedad" y "silencio". No conoce OTRIX ni ningún otro
proyecto concreto: todo lo específico llega por `config_path`.

Contrato de salida (Blueprint sección 5): `run_digest` siempre devuelve un
string, nunca lanza. `"[SILENT]"` sin novedad; una línea corta
`"<PROYECTO>: N mensajes nuevos. <novedad>"` con novedad; `"[ERROR] ..."` si
la config es inválida o Evolution API falla. Cero reintentos (Blueprint
10.3): un fallo termina la corrida, no se reintenta en bucle.

`<PROYECTO>` se deriva del nombre del archivo de config (`otrix.json` ->
`OTRIX`), no hace falta un campo extra en el JSON para eso.
"""
import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from env_loader import EnvLoadError, load_env, require
from evolution_client import EvolutionClient, EvolutionClientError

# Carpeta de estado entre corridas: un archivo JSON por proyecto. Excluida de
# Git (.gitignore agrega "state/" en esta misma fase): es memoria de
# ejecución, no configuración versionable.
STATE_DIR = Path(__file__).resolve().parent / "state"

ENV_PATH = Path(__file__).resolve().parent / ".env"


class ProjectDigestError(Exception):
    """Error propio del motor: config malformada o ilegible. Nunca se deja
    escapar de `run_digest`: ahí se atrapa y se convierte en un string de
    error, para que el cron nunca reviente."""


def _validar_config(data: Any) -> None:
    """Valida la forma mínima de una config de proyecto ya parseada.

    Levanta ProjectDigestError con un mensaje claro ante cualquier campo
    faltante o con el tipo incorrecto. Nunca indexa `data[...]` a ciegas
    antes de este chequeo.
    """
    if not isinstance(data, dict):
        raise ProjectDigestError("La config debe ser un objeto JSON (dict).")

    grupo = data.get("grupo")
    if not isinstance(grupo, str) or not grupo.strip():
        raise ProjectDigestError("La config debe tener 'grupo' (string no vacío).")

    palabras_clave = data.get("palabras_clave")
    if not isinstance(palabras_clave, list) or not all(
        isinstance(p, str) for p in palabras_clave
    ):
        raise ProjectDigestError(
            "La config debe tener 'palabras_clave' como lista de strings."
        )

    frecuencia = data.get("frecuencia")
    if not isinstance(frecuencia, str) or not frecuencia.strip():
        raise ProjectDigestError("La config debe tener 'frecuencia' (string no vacío).")


def _cargar_config(path: Union[str, Path]) -> Dict[str, Any]:
    """Lee y parsea `config/<proyecto>.json`, validado con `_validar_config`.

    Levanta ProjectDigestError (nunca una excepción cruda de json/OSError) si
    el archivo no existe, no es JSON válido, o no cumple la forma mínima.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise ProjectDigestError(f"No se encontró el archivo de config en: {config_path}")

    try:
        contenido = config_path.read_text(encoding="utf-8")
        data = json.loads(contenido)
    except OSError as exc:
        raise ProjectDigestError(f"No se pudo leer {config_path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ProjectDigestError(f"{config_path} no es JSON válido: {exc}") from exc

    _validar_config(data)
    return data


def _cargar_estado(path: Union[str, Path]) -> Dict[str, Any]:
    """Lee el estado de la corrida anterior de un proyecto.

    Si el archivo no existe, no es JSON válido, o no tiene la forma
    esperada (`{"ids_vistos": [...]}` con strings), se trata como si fuera
    la primera corrida: se devuelve el estado por defecto, nunca se levanta
    una excepción.

    IMPORTANTE (concurrencia): este proyecto diseña una ejecución por proyecto
    (máximo 1 run/día por proyecto en cron). Si en el futuro hay múltiples
    runs simultáneos del mismo proyecto, esta función es vulnerable a race
    conditions (partial read de writes en progreso). En ese caso, agregar
    file locking explícito (fcntl.flock en Unix, portalocker en Windows).
    """
    estado_path = Path(path)
    default: Dict[str, Any] = {"ids_vistos": []}

    if not estado_path.is_file():
        return default

    try:
        contenido = estado_path.read_text(encoding="utf-8")
        data = json.loads(contenido)
    except (OSError, json.JSONDecodeError):
        return default

    if not isinstance(data, dict):
        return default

    ids_vistos = data.get("ids_vistos")
    if not isinstance(ids_vistos, list) or not all(isinstance(i, str) for i in ids_vistos):
        return default

    return {"ids_vistos": ids_vistos}


def _guardar_estado(path: Union[str, Path], estado: Dict[str, Any]) -> None:
    """Escribe el estado de esta corrida a disco de forma atomic.

    Crea la carpeta contenedora si hace falta, escribe a un temp file en
    el mismo directorio, y luego hace rename atomic. Si el rename falla,
    el archivo original queda intacto (no hay corrupción parcial).
    """
    estado_path = Path(path)
    estado_path.parent.mkdir(parents=True, exist_ok=True)

    contenido = json.dumps(estado, ensure_ascii=False, indent=2)

    try:
        fd, temp_path = tempfile.mkstemp(
            dir=estado_path.parent, prefix=".tmp_", suffix=".json"
        )
        with open(fd, "w", encoding="utf-8") as tmp_file:
            tmp_file.write(contenido)
        Path(temp_path).replace(estado_path)
    except Exception as exc:
        raise ProjectDigestError(f"No se pudo guardar estado en {estado_path}: {exc}") from exc


def _extraer_texto(mensaje: Any) -> str:
    """Extrae el texto útil de un mensaje de Evolution API, si lo tiene.

    Soporta los tipos vistos en la Fase 2 (fixture real): `conversation` y
    la `caption` de `imageMessage`. Los mensajes sin texto (p.ej. una
    reacción, que solo trae un emoji) devuelven `""` a propósito: un emoji
    no es contenido buscable por palabra clave. Nunca indexa a ciegas.
    """
    if not isinstance(mensaje, dict):
        return ""

    contenido = mensaje.get("message")
    if not isinstance(contenido, dict):
        return ""

    texto = contenido.get("conversation")
    if isinstance(texto, str) and texto.strip():
        return texto

    imagen = contenido.get("imageMessage")
    if isinstance(imagen, dict):
        caption = imagen.get("caption")
        if isinstance(caption, str) and caption.strip():
            return caption

    return ""


def _id_de_mensaje(mensaje: Any) -> Optional[str]:
    """Identificador estable de un mensaje (`key.id`, con fallback a `id`
    de nivel superior). Devuelve None si no se puede determinar uno: ese
    mensaje no se puede rastrear entre corridas y se ignora al comparar
    contra el estado (detalle interno de `_mensajes_nuevos`/`run_digest`)."""
    if not isinstance(mensaje, dict):
        return None

    key = mensaje.get("key")
    if isinstance(key, dict):
        id_key = key.get("id")
        if isinstance(id_key, str) and id_key:
            return id_key

    id_top = mensaje.get("id")
    if isinstance(id_top, str) and id_top:
        return id_top

    return None


def _mensajes_nuevos(mensajes: Any, ids_vistos: Any) -> List[Dict[str, Any]]:
    """Filtra, de la lista de mensajes traídos en esta corrida, los que no
    estaban en `ids_vistos` (el estado de la corrida anterior).

    Mensajes sin id rastreable se excluyen (no se pueden comparar de forma
    confiable). Devuelve `[]` si `mensajes` no es una lista."""
    if not isinstance(mensajes, list):
        return []

    vistos = ids_vistos if isinstance(ids_vistos, (set, frozenset)) else set(ids_vistos or [])

    nuevos = []
    for mensaje in mensajes:
        id_mensaje = _id_de_mensaje(mensaje)
        if id_mensaje is None:
            continue
        if id_mensaje not in vistos:
            nuevos.append(mensaje)
    return nuevos


def _contiene_palabra_clave(texto: str, palabras_clave: Any) -> bool:
    """True si `texto` contiene alguna de `palabras_clave`, sin distinguir
    mayúsculas/minúsculas. `""` o una lista vacía/ inválida siempre dan
    False (nunca hay coincidencia con texto vacío)."""
    if not texto or not isinstance(palabras_clave, list):
        return False
    texto_lower = texto.lower()
    return any(
        isinstance(palabra, str) and palabra and palabra.lower() in texto_lower
        for palabra in palabras_clave
    )


def run_digest(
    config_path: Union[str, Path],
    state_path: Union[str, Path],
    client: EvolutionClient,
) -> str:
    """Orquesta una corrida completa del motor para un proyecto.

    Nunca lanza: cualquier fallo (config inválida, Evolution API caída)
    degrada a un string `"[ERROR] ..."`. Sin novedad, `"[SILENT]"`. Con
    novedad, `"<PROYECTO>: N mensajes nuevos. <novedad>"`.

    Regla dura (Blueprint 10.3): una sola llamada a `client` por corrida
    (más la que hace `find_group_id` internamente para resolver el grupo);
    nunca reintenta si falla.
    """
    try:
        config = _cargar_config(config_path)
    except ProjectDigestError as exc:
        return f"[ERROR] Config inválida: {exc}"

    estado = _cargar_estado(state_path)
    ids_vistos = set(estado["ids_vistos"])

    try:
        mensajes = client.fetch_recent_messages(config["grupo"])
    except EvolutionClientError as exc:
        return f"[ERROR] Evolution API: {exc}"

    nuevos = _mensajes_nuevos(mensajes, ids_vistos)

    # El estado se actualiza con TODOS los ids vistos en esta corrida (los
    # que ya estaban + los nuevos), hayan matcheado palabra clave o no: así
    # un mensaje sin match no se vuelve a evaluar mañana como "nuevo".
    ids_de_esta_corrida = {
        id_mensaje
        for id_mensaje in (_id_de_mensaje(m) for m in mensajes if isinstance(mensajes, list))
        if id_mensaje is not None
    }
    _guardar_estado(state_path, {"ids_vistos": sorted(ids_vistos | ids_de_esta_corrida)})

    palabras_clave = config["palabras_clave"]
    coincidencias = [
        mensaje for mensaje in nuevos if _contiene_palabra_clave(_extraer_texto(mensaje), palabras_clave)
    ]

    if not coincidencias:
        return "[SILENT]"

    proyecto = Path(config_path).stem.upper()
    novedad = _extraer_texto(coincidencias[0])[:120]
    return f"{proyecto}: {len(coincidencias)} mensajes nuevos. {novedad}"


def main() -> None:
    """Punto de entrada de línea de comandos: `python project_digest.py
    <ruta-config.json>`. El estado se guarda en `state/<proyecto>.json`,
    junto a este archivo (convención derivada del nombre de la config)."""
    if len(sys.argv) < 2:
        print("Uso: python project_digest.py <ruta-config.json>")
        return

    config_path = Path(sys.argv[1])

    try:
        env = load_env(ENV_PATH)
        api_key = require(env, "EVOLUTION_API_KEY")
    except EnvLoadError as exc:
        print(f"[ERROR] Configuración de entorno: {exc}")
        return

    client = EvolutionClient(api_key=api_key)
    state_path = STATE_DIR / f"{config_path.stem}.json"

    resultado = run_digest(config_path, state_path, client)
    print(resultado)


if __name__ == "__main__":
    main()
