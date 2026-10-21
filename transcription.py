"""Transcrição de áudio pelo endpoint de áudio da Groq."""

import logging
import os
from pathlib import PurePath

import httpx


_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
_MODELS = ("whisper-large-v3-turbo", "whisper-large-v3")
_MAX_BYTES = 20 * 1024 * 1024
_TIMEOUT = 90
_logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Erro que pode ser mostrado com segurança na interface."""


def transcribe_bytes(
    audio: bytes,
    content_type: str = "audio/webm",
    original_filename: str = "audio.webm",
) -> str:
    """Transcreve os bytes de um áudio em português."""
    if not audio:
        raise TranscriptionError("A gravação está vazia.")
    if len(audio) > _MAX_BYTES:
        raise TranscriptionError("Áudio grande demais. Grave um trecho menor.")

    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise TranscriptionError("Transcrição não configurada: defina GROQ_API_KEY no servidor.")

    mime = content_type.split(";", 1)[0].strip().lower()
    extensions = {
        "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/mp4": "m4a",
        "audio/x-m4a": "m4a", "audio/wav": "wav", "audio/x-wav": "wav",
        "audio/webm": "webm", "audio/ogg": "ogg", "audio/flac": "flac",
        "audio/mpga": "mpga",
    }
    extension = extensions.get(mime)
    if not extension:
        suffix = PurePath(original_filename.replace("\\", "/")).suffix.lower().lstrip(".")
        if suffix not in {"mp3", "m4a", "wav", "webm", "ogg", "flac", "mpga"}:
            raise TranscriptionError("Formato de áudio não suportado. Use MP3, M4A, WAV, WebM, OGG ou FLAC.")
        extension = suffix
        mime = {
            "mp3": "audio/mpeg", "m4a": "audio/mp4", "wav": "audio/wav",
            "webm": "audio/webm", "ogg": "audio/ogg", "flac": "audio/flac",
            "mpga": "audio/mpga",
        }[extension]

    safe_filename = PurePath(original_filename.replace("\\", "/")).name[:120] or f"audio.{extension}"
    if "." not in safe_filename:
        safe_filename += f".{extension}"

    for model in _MODELS:
        try:
            response = httpx.post(
                _URL,
                headers={"Authorization": f"Bearer {key}"},
                data={"model": model, "language": "pt", "response_format": "json", "temperature": "0"},
                files={"file": (safe_filename, audio, mime)},
                timeout=_TIMEOUT,
            )
        except httpx.HTTPError as exc:
            _logger.warning("Falha de conexão ao transcrever (%s)", type(exc).__name__)
            continue

        if response.status_code == 200:
            return (response.json().get("text") or "").strip()
        _logger.warning("Groq transcription model=%s status=%s", model, response.status_code)
        if response.status_code != 429:
            break

    raise TranscriptionError("Não foi possível transcrever agora. Tente novamente.")
