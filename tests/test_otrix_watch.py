"""Tests de otrix_watch.py (wrapper de cron, Fase 4).

Regla dura (Blueprint 10.3, Stack Profile): CERO red, CERO proceso real.
`subprocess.run` se mockea siempre; nunca se ejecuta project_digest.py de
verdad ni se levanta un proceso Python hijo real.
"""
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import otrix_watch

REPO_ROOT = Path(otrix_watch.__file__).resolve().parent
EXPECTED_PROJECT_DIGEST = REPO_ROOT / "project_digest.py"
EXPECTED_CONFIG = REPO_ROOT / "config" / "otrix.json"


def _mock_completed(returncode: int) -> Mock:
    completed = Mock()
    completed.returncode = returncode
    return completed


@patch("otrix_watch.subprocess.run")
def test_invoca_subprocess_con_interprete_y_rutas_correctas(mock_run):
    """Se invoca con sys.executable, la ruta exacta a project_digest.py y a
    config/otrix.json, sin capturar stdout/stderr (default: se heredan)."""
    mock_run.return_value = _mock_completed(0)

    with pytest.raises(SystemExit):
        otrix_watch.main()

    mock_run.assert_called_once_with(
        [sys.executable, str(EXPECTED_PROJECT_DIGEST), str(EXPECTED_CONFIG)]
    )


@patch("otrix_watch.subprocess.run")
def test_propaga_codigo_de_salida_cero(mock_run):
    """returncode 0 del subprocess -> sys.exit(0) del wrapper."""
    mock_run.return_value = _mock_completed(0)

    with pytest.raises(SystemExit) as exc_info:
        otrix_watch.main()

    assert exc_info.value.code == 0


@patch("otrix_watch.subprocess.run")
def test_propaga_codigo_de_salida_distinto_de_cero(mock_run):
    """returncode != 0 del subprocess -> sys.exit propaga ese mismo código,
    para que el cron pueda distinguir éxito de error."""
    mock_run.return_value = _mock_completed(7)

    with pytest.raises(SystemExit) as exc_info:
        otrix_watch.main()

    assert exc_info.value.code == 7
