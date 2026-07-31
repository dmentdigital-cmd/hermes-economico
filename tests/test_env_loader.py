"""Tests de env_loader.py contra archivos .env sintéticos temporales
(tmp_path de pytest). Ningún archivo real del proyecto se toca."""
import pytest

from env_loader import EnvLoadError, load_env, require


def test_load_env_formato_valido(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "EVOLUTION_API_KEY=clave-de-prueba-no-real\nOTRO=valor\n", encoding="utf-8"
    )

    result = load_env(env_file)

    assert result == {
        "EVOLUTION_API_KEY": "clave-de-prueba-no-real",
        "OTRO": "valor",
    }


def test_load_env_ignora_lineas_vacias_y_comentarios(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n# esto es un comentario\nEVOLUTION_API_KEY=clave-de-prueba-no-real\n\n"
        "# otro comentario\n",
        encoding="utf-8",
    )

    result = load_env(env_file)

    assert result == {"EVOLUTION_API_KEY": "clave-de-prueba-no-real"}


def test_load_env_linea_mal_formada_falla(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("EVOLUTION_API_KEY_SIN_IGUAL\n", encoding="utf-8")

    with pytest.raises(EnvLoadError):
        load_env(env_file)


def test_load_env_archivo_inexistente_falla(tmp_path):
    with pytest.raises(EnvLoadError):
        load_env(tmp_path / "no_existe.env")


def test_require_clave_presente():
    env = {"EVOLUTION_API_KEY": "clave-de-prueba-no-real"}

    assert require(env, "EVOLUTION_API_KEY") == "clave-de-prueba-no-real"


def test_require_clave_faltante_falla():
    env = {}

    with pytest.raises(EnvLoadError) as exc_info:
        require(env, "EVOLUTION_API_KEY")

    assert "EVOLUTION_API_KEY" in str(exc_info.value)


def test_require_clave_vacia_falla():
    env = {"EVOLUTION_API_KEY": ""}

    with pytest.raises(EnvLoadError):
        require(env, "EVOLUTION_API_KEY")
