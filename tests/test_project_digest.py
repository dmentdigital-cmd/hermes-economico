"""Tests de project_digest.py (motor genérico, Fase 3).

Regla dura (Blueprint 10.3): CERO llamadas HTTP reales. `run_digest` recibe
el cliente como parámetro, así que acá se le pasa un `unittest.mock.Mock`
con `fetch_recent_messages` controlado a mano; nunca se instancia
`EvolutionClient` de verdad ni se toca `requests`.

`config/otrix.json` (con las palabras clave placeholder) NO se usa acá:
estos tests usan `tests/fixtures/otrix_config_sample.json`, 100% sintética,
para no depender de que el usuario ya haya completado la lista real.
"""
import json
from pathlib import Path
from unittest.mock import Mock

from evolution_client import EvolutionClientError
from project_digest import run_digest

FIXTURE_CONFIG_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "otrix_config_sample.json"
)


def _cargar_fixture_config():
    with open(FIXTURE_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _copiar_config_a(tmp_path: Path, overrides: dict = None) -> Path:
    """Escribe una copia de la config de fixture (con overrides opcionales)
    en tmp_path, para no depender de mutar el archivo real de fixtures."""
    data = _cargar_fixture_config()
    if overrides:
        data.update(overrides)
    destino = tmp_path / "otrix_config_sample.json"
    destino.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return destino


def _mensaje(id_mensaje: str, texto: str, remote_jid: str = "111111111111@g.us") -> dict:
    """Mensaje sintético con la forma real confirmada en la Fase 2
    (records[].key.id / message.conversation)."""
    return {
        "id": id_mensaje,
        "key": {"id": id_mensaje, "fromMe": False, "remoteJid": remote_jid},
        "pushName": "Persona Ficticia",
        "messageType": "conversation",
        "message": {"conversation": texto},
        "messageTimestamp": 1700000000,
    }


def test_primera_corrida_sin_estado_da_novedad(tmp_path):
    """Caso 1: sin estado previo, un mensaje que matchea palabra clave
    produce novedad (no [SILENT]), y el estado queda guardado."""
    config_path = _copiar_config_a(tmp_path)
    state_path = tmp_path / "state" / "otrix_config_sample.json"

    mensajes = [
        _mensaje("MSG-001", "todo tranquilo por acá"),
        _mensaje("MSG-002", "Esto es urgente, revisar ya"),
    ]
    client = Mock()
    client.fetch_recent_messages.return_value = mensajes

    resultado = run_digest(config_path, state_path, client)

    assert resultado != "[SILENT]"
    assert not resultado.startswith("[ERROR]")
    assert "1 mensajes nuevos" in resultado
    assert state_path.is_file()
    estado_guardado = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(estado_guardado["ids_vistos"]) == {"MSG-001", "MSG-002"}


def test_segunda_corrida_mismo_estado_da_silencio_criterio_demostrable(tmp_path):
    """Caso 2, y a la vez el criterio demostrable de la Fase 3 (Blueprint
    sección 11, fila 3): dos corridas seguidas sobre la misma fixture dan
    novedad la primera vez y silencio la segunda."""
    config_path = _copiar_config_a(tmp_path)
    state_path = tmp_path / "state" / "otrix_config_sample.json"

    mensajes = [_mensaje("MSG-010", "Aviso urgente para el equipo")]
    client = Mock()
    client.fetch_recent_messages.return_value = mensajes

    primera = run_digest(config_path, state_path, client)
    segunda = run_digest(config_path, state_path, client)

    assert primera != "[SILENT]"
    assert "1 mensajes nuevos" in primera
    assert segunda == "[SILENT]"
    assert client.fetch_recent_messages.call_count == 2


def test_mensajes_nuevos_sin_match_da_silencio(tmp_path):
    """Caso 3: hay mensajes nuevos (no estaban en el estado), pero ninguno
    contiene una palabra clave -> silencio, aunque haya novedad "cruda"."""
    config_path = _copiar_config_a(tmp_path)
    state_path = tmp_path / "state" / "otrix_config_sample.json"

    mensajes = [_mensaje("MSG-020", "buen dia a todos"), _mensaje("MSG-021", "nos vemos mañana")]
    client = Mock()
    client.fetch_recent_messages.return_value = mensajes

    resultado = run_digest(config_path, state_path, client)

    assert resultado == "[SILENT]"
    estado_guardado = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(estado_guardado["ids_vistos"]) == {"MSG-020", "MSG-021"}


def test_config_malformado_da_error_sin_reventar(tmp_path):
    """Caso 4: config sin 'grupo' -> [ERROR] sin excepción, y el cliente
    nunca se llama (falla antes de intentar la red)."""
    config_path = tmp_path / "config_malformada.json"
    config_path.write_text(
        json.dumps({"palabras_clave": ["urgente"], "frecuencia": "diaria"}),
        encoding="utf-8",
    )
    state_path = tmp_path / "state" / "config_malformada.json"
    client = Mock()

    resultado = run_digest(config_path, state_path, client)

    assert resultado.startswith("[ERROR]")
    client.fetch_recent_messages.assert_not_called()
    assert not state_path.exists()


def test_estado_corrupto_tratado_como_primera_corrida(tmp_path):
    """Caso 5: un estado con JSON inválido no revienta el motor; se trata
    igual que si no existiera ningún estado previo."""
    config_path = _copiar_config_a(tmp_path)
    state_path = tmp_path / "state" / "otrix_config_sample.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{esto no es json valido", encoding="utf-8")

    mensajes = [_mensaje("MSG-030", "algo urgente pasó")]
    client = Mock()
    client.fetch_recent_messages.return_value = mensajes

    resultado = run_digest(config_path, state_path, client)

    assert resultado != "[SILENT]"
    assert "1 mensajes nuevos" in resultado
    estado_guardado = json.loads(state_path.read_text(encoding="utf-8"))
    assert set(estado_guardado["ids_vistos"]) == {"MSG-030"}


def test_evolution_client_error_da_error_sin_reintentos(tmp_path):
    """Caso 6: si el cliente levanta EvolutionClientError, run_digest
    devuelve [ERROR] sin relanzar, llama al cliente UNA sola vez (cero
    reintentos, Blueprint 10.3) y no toca el estado."""
    config_path = _copiar_config_a(tmp_path)
    state_path = tmp_path / "state" / "otrix_config_sample.json"

    client = Mock()
    client.fetch_recent_messages.side_effect = EvolutionClientError("timeout simulado")

    resultado = run_digest(config_path, state_path, client)

    assert resultado.startswith("[ERROR]")
    assert client.fetch_recent_messages.call_count == 1
    assert not state_path.exists()


def test_records_vacio_da_silencio(tmp_path):
    """Caso 7: records=[] (grupo sin mensajes recientes) es silencio, no
    error."""
    config_path = _copiar_config_a(tmp_path)
    state_path = tmp_path / "state" / "otrix_config_sample.json"

    client = Mock()
    client.fetch_recent_messages.return_value = []

    resultado = run_digest(config_path, state_path, client)

    assert resultado == "[SILENT]"
    estado_guardado = json.loads(state_path.read_text(encoding="utf-8"))
    assert estado_guardado["ids_vistos"] == []
