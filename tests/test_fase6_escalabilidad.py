"""Test de escalabilidad para Fase 6: agregar proyecto con solo un archivo config.

Demuestra que el criterio de éxito #3 (Blueprint sección 3) se cumple:
"agregar un proyecto o grupo nuevo cuesta UN archivo de configuración, no código nuevo."

Se crea un proyecto sintético (demo_proyecto.json) y se ejecuta el motor contra él
usando datos de fixture, sin tocar una línea de código de project_digest.py.
"""
import json
from pathlib import Path
from unittest.mock import Mock

from project_digest import run_digest


def test_escalabilidad_agregar_proyecto_nuevo_solo_config(tmp_path):
    """Un nuevo proyecto (demo_proyecto.json) se procesa sin cambios de código.

    Verifica:
    - El motor lee la nueva config desde config/demo_proyecto.json
    - Procesa mensajes contra ella
    - Guarda estado correctamente
    - Sin tocar project_digest.py ni ningún código
    """
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    state_dir = tmp_path / "state"
    state_dir.mkdir()

    # Crear config del nuevo proyecto (estructura idéntica a otrix.json)
    new_project_config = {
        "grupo": "Demo Proyecto Test",
        "palabras_clave": ["urgente", "crítico"],
        "frecuencia": "diaria"
    }
    config_path = config_dir / "demo_proyecto.json"
    config_path.write_text(json.dumps(new_project_config, ensure_ascii=False), encoding="utf-8")

    # Datos de fixture: mensaje que matchea palabra clave
    mensajes = [
        {
            "id": "DEMO-001",
            "key": {"id": "DEMO-001", "fromMe": False, "remoteJid": "999999999@g.us"},
            "pushName": "Demo User",
            "messageType": "conversation",
            "message": {"conversation": "Urgente: revisar esto"},
            "messageTimestamp": 1700000100,
        }
    ]

    client = Mock()
    client.fetch_recent_messages.return_value = mensajes
    state_path = state_dir / "demo_proyecto.json"

    # Ejecutar: el motor procesa el nuevo proyecto sin cambios de código
    resultado = run_digest(config_path, state_path, client)

    # Verificaciones
    assert resultado != "[SILENT]", "Debe detectar la novedad (palabra clave 'urgente')"
    assert not resultado.startswith("[ERROR]"), "No debe fallar al leer la config nueva"
    assert "Demo Proyecto" in resultado or "demo_proyecto" in resultado.lower(), "Debe usar el nombre del proyecto en la salida"
    assert state_path.is_file(), "Debe crear estado para el nuevo proyecto"

    estado = json.loads(state_path.read_text(encoding="utf-8"))
    assert "DEMO-001" in estado.get("ids_vistos", []), "Debe guardar el ID del mensaje procesado"


def test_escalabilidad_segundo_proyecto_mismo_motor():
    """Mismo motor, dos configs distintos, dos states distintos: sin acoplamiento.

    Demuestra que el motor es agnóstico al proyecto:
    project_digest.py + config/proyecto_A.json + state/proyecto_A.json
    project_digest.py + config/proyecto_B.json + state/proyecto_B.json
    Ambos con el MISMO código, sin cambios, sin index.json ni registros centrales.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as tmp_base:
        tmp_path = Path(tmp_base)
        config_dir = tmp_path / "config"
        state_dir = tmp_path / "state"
        config_dir.mkdir()
        state_dir.mkdir()

        # Proyecto A: marketing
        config_a = {
            "grupo": "Marketing Team",
            "palabras_clave": ["campaña", "presupuesto"],
            "frecuencia": "diaria"
        }
        config_a_path = config_dir / "marketing.json"
        config_a_path.write_text(json.dumps(config_a, ensure_ascii=False), encoding="utf-8")

        # Proyecto B: desarrollo
        config_b = {
            "grupo": "Dev Team",
            "palabras_clave": ["bug", "deploy"],
            "frecuencia": "diaria"
        }
        config_b_path = config_dir / "desarrollo.json"
        config_b_path.write_text(json.dumps(config_b, ensure_ascii=False), encoding="utf-8")

        # Estado separado para cada proyecto
        state_a_path = state_dir / "marketing.json"
        state_b_path = state_dir / "desarrollo.json"

        # Procesar Proyecto A
        client_a = Mock()
        client_a.fetch_recent_messages.return_value = [
            {
                "id": "MKT-1",
                "key": {"id": "MKT-1", "fromMe": False, "remoteJid": "111@g.us"},
                "pushName": "User",
                "messageType": "conversation",
                "message": {"conversation": "Nueva campaña lanzada"},
                "messageTimestamp": 1700000200,
            }
        ]

        resultado_a = run_digest(config_a_path, state_a_path, client_a)
        assert resultado_a != "[SILENT]"
        assert state_a_path.is_file()

        # Procesar Proyecto B (con distinto client, distintos datos)
        client_b = Mock()
        client_b.fetch_recent_messages.return_value = [
            {
                "id": "DEV-1",
                "key": {"id": "DEV-1", "fromMe": False, "remoteJid": "222@g.us"},
                "pushName": "Developer",
                "messageType": "conversation",
                "message": {"conversation": "Bug crítico encontrado"},
                "messageTimestamp": 1700000300,
            }
        ]

        resultado_b = run_digest(config_b_path, state_b_path, client_b)
        assert resultado_b != "[SILENT]"
        assert state_b_path.is_file()

        # Verificar: estados son independientes (escalabilidad demostrada)
        estado_a = json.loads(state_a_path.read_text(encoding="utf-8"))
        estado_b = json.loads(state_b_path.read_text(encoding="utf-8"))
        assert "MKT-1" in estado_a.get("ids_vistos", [])
        assert "DEV-1" in estado_b.get("ids_vistos", [])
        assert "MKT-1" not in estado_b.get("ids_vistos", []), "Estados no se mezclan"
