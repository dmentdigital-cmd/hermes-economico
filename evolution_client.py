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
# fetchAllGroups y findMessages ya están confirmados contra la Evolution API
# real de la VPS (ver aprendizajes de la Fase 2 en BUILD-STATE). Si la VPS
# cambiara de forma en el futuro, este sigue siendo el ÚNICO lugar del
# proyecto que hay que corregir.
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

    def _post(self, path: str, body: Dict[str, Any]) -> Any:
        """Hace un único POST con body JSON, cuenta la llamada y devuelve el
        JSON parseado.

        Levanta EvolutionClientError en cualquier fallo. Cero reintentos,
        mismo criterio que `_get`.
        """
        url = f"{self.base_url}{path}"
        self.call_count += 1
        try:
            response = requests.post(
                url, headers=self._headers(), json=body, timeout=TIMEOUT_SECONDS
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

        findMessages es POST, no GET (confirmado contra la VPS real: GET
        responde 404 "Cannot GET"). El body exacto confirmado es
        `{"where": {"key": {"remoteJid": <group_id>}}, "limit": ...}`.

        OJO: aunque se manda "limit" en el body, la Evolution API real
        observada en la VPS lo ignoró y devolvió TODO el historial
        disponible. Este método nunca asume que el servidor limita la
        cantidad; si en el futuro hace falta acotar, se hace del lado
        cliente después de recibir la respuesta completa.

        Devuelve la lista de mensajes (`records`, puede ser vacía). Levanta
        EvolutionClientError en cualquier fallo, incluida forma inesperada.
        """
        group_id = self.find_group_id(group_name)
        data = self._post(
            MESSAGES_PATH,
            body={"where": {"key": {"remoteJid": group_id}}},
        )

        messages_obj = data.get("messages") if isinstance(data, dict) else None
        records = messages_obj.get("records") if isinstance(messages_obj, dict) else None

        if not isinstance(records, list):
            raise EvolutionClientError(
                f"Forma de respuesta inesperada al listar mensajes: {type(data).__name__}"
            )
        return records
