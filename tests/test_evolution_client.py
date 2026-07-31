"""Tests de evolution_client.py.

Regla dura (Blueprint sección 10.3): CERO llamadas HTTP reales. Todo se
mockea con unittest.mock.patch contra una fixture SINTÉTICA
(tests/fixtures/evolution_sample.json, marcada como tal en su propio
contenido) para no confundirla nunca con una captura real.

find_group_id usa GET (requests.get); fetch_recent_messages resuelve el
grupo con GET y después trae mensajes con POST (requests.post) contra
findMessages — confirmado contra la Evolution API real de la VPS.
"""
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from evolution_client import EvolutionClient, EvolutionClientError

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "evolution_sample.json"


def _cargar_fixture():
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _mock_response(status_code=200, json_data=None, text=""):
    response = Mock()
    response.status_code = status_code
    response.text = text
    if json_data is None:
        response.json.side_effect = ValueError("respuesta sin JSON válido")
    else:
        response.json.return_value = json_data
    return response


def test_fetch_recent_messages_caso_feliz():
    fixture = _cargar_fixture()
    client = EvolutionClient(api_key="clave-de-prueba-no-real")

    with patch("evolution_client.requests.get") as mock_get, patch(
        "evolution_client.requests.post"
    ) as mock_post:
        mock_get.return_value = _mock_response(json_data=fixture["groups_response"])
        mock_post.return_value = _mock_response(json_data=fixture["messages_response"])

        mensajes = client.fetch_recent_messages("Marketeros Otrix")

    esperados = fixture["messages_response"]["messages"]["records"]
    assert len(mensajes) == len(esperados)
    assert mensajes == esperados
    assert client.call_count == 2
    assert mock_get.call_count == 1
    assert mock_post.call_count == 1


def test_fetch_recent_messages_records_vacio():
    """Grupo sin mensajes recientes: records=[] es válido, no es error."""
    fixture = _cargar_fixture()
    client = EvolutionClient(api_key="clave-de-prueba-no-real")

    with patch("evolution_client.requests.get") as mock_get, patch(
        "evolution_client.requests.post"
    ) as mock_post:
        mock_get.return_value = _mock_response(json_data=fixture["groups_response"])
        mock_post.return_value = _mock_response(
            json_data={"messages": {"total": 0, "pages": 0, "currentPage": 1, "records": []}}
        )

        mensajes = client.fetch_recent_messages("Marketeros Otrix")

    assert mensajes == []
    assert client.call_count == 2


def test_fetch_recent_messages_error_http():
    client = EvolutionClient(api_key="clave-de-prueba-no-real")

    with patch("evolution_client.requests.get") as mock_get:
        mock_get.return_value = _mock_response(
            status_code=500, json_data={}, text="Internal Server Error"
        )
        with pytest.raises(EvolutionClientError):
            client.fetch_recent_messages("Marketeros Otrix")

    assert client.call_count == 1


def test_fetch_recent_messages_timeout():
    client = EvolutionClient(api_key="clave-de-prueba-no-real")

    with patch("evolution_client.requests.get") as mock_get:
        mock_get.side_effect = requests.exceptions.Timeout("se agotó el tiempo de espera")
        with pytest.raises(EvolutionClientError):
            client.fetch_recent_messages("Marketeros Otrix")

    assert client.call_count == 1


def test_fetch_recent_messages_falta_clave_messages_degrada_sin_reventar():
    fixture = _cargar_fixture()
    client = EvolutionClient(api_key="clave-de-prueba-no-real")

    with patch("evolution_client.requests.get") as mock_get, patch(
        "evolution_client.requests.post"
    ) as mock_post:
        mock_get.return_value = _mock_response(json_data=fixture["groups_response"])
        mock_post.return_value = _mock_response(json_data={"algo": "con forma inesperada"})

        with pytest.raises(EvolutionClientError):
            client.fetch_recent_messages("Marketeros Otrix")

    assert client.call_count == 2


def test_fetch_recent_messages_falta_clave_records_degrada_sin_reventar():
    fixture = _cargar_fixture()
    client = EvolutionClient(api_key="clave-de-prueba-no-real")

    with patch("evolution_client.requests.get") as mock_get, patch(
        "evolution_client.requests.post"
    ) as mock_post:
        mock_get.return_value = _mock_response(json_data=fixture["groups_response"])
        mock_post.return_value = _mock_response(
            json_data={"messages": {"total": 0, "pages": 0, "currentPage": 1}}
        )

        with pytest.raises(EvolutionClientError):
            client.fetch_recent_messages("Marketeros Otrix")

    assert client.call_count == 2
