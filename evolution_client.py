#!/usr/bin/env python3
"""Cliente HTTP para Evolution API (puente de WhatsApp self-hosted,
preexistente — ver STACK-PROFILE-hermes-economico.md).

Aísla TODA la llamada HTTP en este módulo. Reutilizable a propósito: no
conoce ningún proyecto concreto (ni "OTRIX" ni "Marketeros Otrix" aparecen
acá). El grupo objetivo se pasa como parámetro en cada llamada.

Regla dura (Blueprint sección 10.3): CERO reintentos, cero backoff. Un
fallo (HTTP error, timeout, JSON inválido, forma inesperada) levanta
EvolutionClientError; quien llama decide si degrada a silencio o a un
aviso de error. Este módulo nunca reintenta por su cuenta.
"""
from typing import Any, Dict, List, Optional

import requests

# --- Constantes de conexión ------------------------------------------------
# El endpoint exacto todavía NO está confirmado contra la Evolution API real
# de la VPS (ver Blueprint sección 4 / STACK-PROFILE, "Dependencia externa
# preexistente"). Los paths de abajo son la mejor suposición según la forma
# habitual de la API de Evolution. Si la VPS confirma otra forma, este es el
# ÚNICO lugar del proyecto que hay que corregir.
BASE_URL = "http://127.0.0.1:8085"
INSTANCE_NAME = "WHATSAPP DMENTE DIGITAL"

GROUPS_PATH = f"/group/fetchAllGroups/{INSTANCE_NAME}"
MESSAGES_PATH = f"/chat/findMessages/{INSTANCE_NAME}"

TIMEOUT_SECONDS = 10
# -----------------------------------------------------------------------


class EvolutionClientError(Exception):
    """Error propio del cliente: HTTP no-200, timeout, JSON inválido o forma
    de respuesta inesperada. Nunca se reintenta automáticamente."""


class EvolutionClient:
    """Cliente contra Evolution API. No conoce el grupo objetivo de ningún
    proyecto: se lo pasan como argumento en cada llamada.

    Expone `call_count`: cuántas llamadas HTTP reales hizo esta instancia
    durante su vida, para poder verificar el techo de la sección 10.3 del
    Blueprint (20 llamadas/día agregadas).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = BASE_URL,
        instance: str = INSTANCE_NAME,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.instance = instance
        self.call_count = 0

    def _headers(self) -> Dict[str, str]:
        return {"apikey": self.api_key}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Hace un único GET, cuenta la llamada y devuelve el JSON parseado.

        Levanta EvolutionClientError en cualquier fallo. Cero reintentos:
        si esta llamada falla, falla — no hay bucle de reintento acá ni en
        quien la invoca.
        """
        url = f"{self.base_url}{path}"
        self.call_count += 1
        try:
            response = requests.get(
                url, headers=self._headers(), params=params, timeout=TIMEOUT_SECONDS
            )
        except requests.exceptions.Timeout as exc:
            raise EvolutionClientError(f"Timeout llamando a {url}") from exc
        except requests.exceptions.RequestException as exc:
            raise EvolutionClientError(f"Error de red llamando a {url}: {exc}") from exc

        if response.status_code != 200:
            raise EvolutionClientError(
                f"Evolution API respondió HTTP {response.status_code} en {url}: "
                f"{response.text[:200]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise EvolutionClientError(f"Respuesta no es JSON válido desde {url}") from exc

    def find_group_id(self, group_name: str) -> str:
        """Resuelve el id interno del grupo a partir de su nombre visible.

        Valida la forma de la respuesta con dict.get()/isinstance, nunca
        indexa a ciegas.

        Evolution API exige el query param `getParticipants` en esta llamada
        (confirmado contra la VPS real: sin él responde HTTP 400 "The
        getParticipants needs to be informed in the query"). Se pide en
        "false" porque acá solo hace falta resolver el id del grupo por
        nombre, no la lista de participantes.
        """
        data = self._get(GROUPS_PATH, params={"getParticipants": "false"})

        if isinstance(data, list):
            groups = data
        elif isinstance(data, dict):
            groups = data.get("groups")
        else:
            groups = None

        if not isinstance(groups, list):
            raise EvolutionClientError(
                f"Forma de respuesta inesperada al listar grupos: {type(data).__name__}"
            )

        for group in groups:
            if not isinstance(group, dict):
                continue
            nombre = group.get("subject") or group.get("name")
            if nombre == group_name:
                group_id = group.get("id")
                if not group_id:
                    raise EvolutionClientError(
                        f"Grupo '{group_name}' encontrado pero sin campo 'id' en la respuesta."
                    )
                return group_id

        raise EvolutionClientError(f"No se encontró ningún grupo llamado '{group_name}'.")

    def fetch_recent_messages(self, group_name: str) -> List[Dict[str, Any]]:
        """Resuelve el grupo por nombre y trae sus mensajes recientes.

        Devuelve la lista de mensajes (puede ser vacía). Levanta
        EvolutionClientError en cualquier fallo, incluida forma inesperada.
        """
        group_id = self.find_group_id(group_name)
        data = self._get(MESSAGES_PATH, params={"remoteJid": group_id})

        if isinstance(data, list):
            messages = data
        elif isinstance(data, dict):
            messages = data.get("messages")
        else:
            messages = None

        if not isinstance(messages, list):
            raise EvolutionClientError(
                f"Forma de respuesta inesperada al listar mensajes: {type(data).__name__}"
            )
        return messages
