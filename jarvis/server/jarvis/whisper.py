"""Speech-to-Text über die Whisper-API von OpenAI.

Dieselbe Grundregel wie bei jedem Werkzeug: ein Transkript kommt nur zurück,
wenn die API tatsächlich geantwortet hat. Fehlender Schlüssel, kein Netz, eine
Ablehnung oder eine leere Antwort werden als Fehler gemeldet -- Jarvis rät den
gesprochenen Text nicht, wenn er ihn nicht bekommen hat.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class WhisperError(Exception):
    """Der Whisper-Aufruf ist fehlgeschlagen -- der Grund steht in der Meldung."""


@dataclass
class WhisperClient:
    api_key: str = ""
    model: str = "whisper-1"
    url: str = "https://api.openai.com/v1/audio/transcriptions"
    timeout: int = 30

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    def transcribe(self, audio: bytes, filename: str = "sprache.webm",
                    content_type: str = "audio/webm") -> str:
        if not self.configured:
            raise WhisperError("Kein Whisper-API-Schlüssel eingetragen.")
        if not audio:
            raise WhisperError("Keine Audiodaten empfangen.")
        try:
            response = httpx.post(
                self.url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                data={"model": self.model},
                files={"file": (filename, audio, content_type or "audio/webm")},
                timeout=self.timeout,
            )
        except httpx.HTTPError as exc:
            raise WhisperError(f"Whisper war nicht erreichbar: {exc}") from exc
        if response.status_code != 200:
            detail = response.text.strip()[:300]
            raise WhisperError(
                f"Whisper hat abgelehnt (Status {response.status_code}): {detail}")
        try:
            text = str(response.json().get("text", "")).strip()
        except ValueError as exc:
            raise WhisperError(f"Whisper-Antwort war kein JSON: {exc}") from exc
        if not text:
            raise WhisperError("Whisper hat einen leeren Text zurückgegeben.")
        return text
