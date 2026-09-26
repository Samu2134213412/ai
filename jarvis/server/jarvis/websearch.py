"""Web-Suche über einen konfigurierten Suchdienst.

Dieselbe Grundregel wie bei jedem Werkzeug: ein Treffer kommt nur zurück,
wenn ein echter Suchdienst tatsächlich geantwortet hat -- keine Erfindung,
kein Rückgriff auf trainiertes Wissen als Ersatz. Genau wie bei Whisper
(siehe ``whisper.py``) bringt Jarvis keinen eigenen Schlüssel oder Dienst
mit; leer in der Konfiguration heißt aus, nicht "nimm irgendeinen Dienst"
(Punkt 55). Bevorzugt eine selbst gehostete SearXNG-Instanz -- kein
Schlüssel, keine dritte Partei, passt zum Rest des Projekts (alles läuft
lokal); ersatzweise die Brave Search API, wenn keine eigene Infrastruktur
zur Verfügung steht.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class WebSearchError(Exception):
    """Die Web-Suche ist fehlgeschlagen -- der Grund steht in der Meldung."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str


@dataclass
class WebSearchClient:
    searxng_url: str = ""
    brave_api_key: str = ""
    timeout: int = 15

    @property
    def configured(self) -> bool:
        return bool(self.searxng_url or self.brave_api_key)

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        if not self.configured:
            raise WebSearchError(
                "Keine Web-Suche eingerichtet. In jarvis.json unter \"search\" "
                "entweder \"searxng_url\" (eigene SearXNG-Instanz, kein "
                "Schlüssel nötig) oder \"brave_api_key\" "
                "(https://brave.com/search/api) eintragen.")
        # SearXNG zuerst: kein Schlüssel, keine dritte Partei, wenn beides
        # eingetragen ist -- passt besser zum "läuft alles lokal"-Grundsatz.
        if self.searxng_url:
            return self._searxng(query, limit)
        return self._brave(query, limit)

    def _searxng(self, query: str, limit: int) -> list[SearchResult]:
        try:
            response = httpx.get(
                self.searxng_url.rstrip("/") + "/search",
                params={"q": query, "format": "json"}, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise WebSearchError(f"SearXNG war nicht erreichbar: {exc}") from exc
        if response.status_code != 200:
            raise WebSearchError(
                f"SearXNG hat abgelehnt (Status {response.status_code}). "
                "Läuft die Instanz, und ist das JSON-Format aktiviert "
                "(search.formats in settings.yml)?")
        try:
            data = response.json()
        except ValueError as exc:
            raise WebSearchError(f"SearXNG-Antwort war kein JSON: {exc}") from exc
        treffer = data.get("results") or []
        return [SearchResult(title=str(r.get("title", "")), url=str(r.get("url", "")),
                             snippet=str(r.get("content", "")))
                for r in treffer[:limit]]

    def _brave(self, query: str, limit: int) -> list[SearchResult]:
        try:
            response = httpx.get(
                "https://api.search.brave.com/res/v1/web/search",
                params={"q": query, "count": limit},
                headers={"X-Subscription-Token": self.brave_api_key,
                        "Accept": "application/json"},
                timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise WebSearchError(f"Brave Search war nicht erreichbar: {exc}") from exc
        if response.status_code != 200:
            detail = response.text.strip()[:300]
            raise WebSearchError(
                f"Brave Search hat abgelehnt (Status {response.status_code}): {detail}")
        try:
            data = response.json()
        except ValueError as exc:
            raise WebSearchError(f"Brave-Antwort war kein JSON: {exc}") from exc
        treffer = ((data.get("web") or {}).get("results")) or []
        return [SearchResult(title=str(r.get("title", "")), url=str(r.get("url", "")),
                             snippet=str(r.get("description", "")))
                for r in treffer[:limit]]
