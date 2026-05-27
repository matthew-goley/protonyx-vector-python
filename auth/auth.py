"""Backend communication for the Vector auth layer.

Single point of contact with the Fastify REST API. ``API_URL`` is the only
constant a deployment swap needs to touch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import requests


API_URL = 'http://localhost:3000'

_REQUEST_TIMEOUT = 15

_SESSION_FILE = Path(__file__).resolve().parent / 'session.json'


def _extract_error(response: 'requests.Response') -> str:
    """Pull the most useful error string from a non-2xx response."""
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f'HTTP {response.status_code}'
    if isinstance(payload, dict):
        for key in ('error', 'message', 'detail', 'msg'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return json.dumps(payload)
    return str(payload)


def login(username_or_email: str, password: str) -> str:
    """POST /login. Returns the bearer token on success."""
    response = requests.post(
        f'{API_URL}/login',
        json={'username': username_or_email, 'password': password},
        timeout=_REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise Exception(_extract_error(response))
    try:
        data = response.json()
    except ValueError as exc:
        raise Exception('Login response was not valid JSON') from exc
    token = data.get('token') if isinstance(data, dict) else None
    if not isinstance(token, str) or not token:
        raise Exception('Login response did not include a token')
    return token


def signup(username: str, email: str, password: str) -> bool:
    """POST /signup. Returns True on success, raises with the server message on failure."""
    response = requests.post(
        f'{API_URL}/signup',
        json={'username': username, 'email': email, 'password': password},
        timeout=_REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise Exception(_extract_error(response))
    return True


def get_me(token: str) -> dict:
    """GET /me with Bearer auth. Returns the full user dict."""
    response = requests.get(
        f'{API_URL}/me',
        headers={'Authorization': f'Bearer {token}'},
        timeout=_REQUEST_TIMEOUT,
    )
    if response.status_code >= 400:
        raise Exception(_extract_error(response))
    try:
        data = response.json()
    except ValueError as exc:
        raise Exception('User response was not valid JSON') from exc
    if not isinstance(data, dict):
        raise Exception('User response was not a JSON object')
    return data


def check_eula_status(token: str) -> Optional[dict]:
    """GET /legal/status with Bearer auth.

    Returns the parsed JSON response (which includes ``tos_accepted`` /
    ``eula_accepted`` flags and the current document versions), or ``None`` on
    any failure (network error, non-2xx status, or unparseable body). Unlike
    ``get_me`` this never raises - the caller fails open when it returns None.
    """
    try:
        response = requests.get(
            f'{API_URL}/legal/status',
            headers={'Authorization': f'Bearer {token}'},
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code >= 400:
            return None
        data = response.json()
    except (requests.RequestException, ValueError):
        return None
    return data if isinstance(data, dict) else None


def accept_legal_document(token: str, document: str) -> Optional[dict]:
    """POST /legal/accept with Bearer auth and body ``{"document": document}``.

    ``document`` is ``'eula'`` or ``'tos'``. Returns the parsed JSON response on
    success, or ``None`` on any failure (network error, non-2xx status, or
    unparseable body). Never raises.
    """
    try:
        response = requests.post(
            f'{API_URL}/legal/accept',
            headers={'Authorization': f'Bearer {token}'},
            json={'document': document},
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code >= 400:
            return None
        data = response.json()
    except (requests.RequestException, ValueError):
        return None
    return data if isinstance(data, dict) else None


def accept_eula(token: str) -> Optional[dict]:
    """Accept the End User License Agreement. Thin wrapper over
    ``accept_legal_document(token, 'eula')`` (kept for call-site clarity)."""
    return accept_legal_document(token, 'eula')


def accept_tos(token: str) -> Optional[dict]:
    """Accept the Terms of Service. Thin wrapper over
    ``accept_legal_document(token, 'tos')``."""
    return accept_legal_document(token, 'tos')


def _legal_status_code(token: str) -> Optional[int]:
    """GET /legal/status and return only the HTTP status code (``None`` on a
    network-level failure).

    Used by the legal gate to classify an accept failure: a follow-up probe
    returning 401 means the session expired (clear + re-login), while a 2xx or
    None means the accept failure was transient (let the user retry).
    """
    try:
        response = requests.get(
            f'{API_URL}/legal/status',
            headers={'Authorization': f'Bearer {token}'},
            timeout=_REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return None
    return response.status_code


def save_token(token: str) -> None:
    """Persist the token alongside the auth module."""
    _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SESSION_FILE.write_text(json.dumps({'token': token}), encoding='utf-8')


def load_token() -> Optional[str]:
    """Return the saved token, or None if missing / unreadable / malformed."""
    if not _SESSION_FILE.exists():
        return None
    try:
        raw = _SESSION_FILE.read_text(encoding='utf-8')
        data = json.loads(raw)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    token = data.get('token')
    if isinstance(token, str) and token:
        return token
    return None


def clear_token() -> None:
    """Delete the session file if present."""
    if _SESSION_FILE.exists():
        try:
            _SESSION_FILE.unlink()
        except OSError:
            pass
