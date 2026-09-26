"""Tool Discovery: aus mehreren hundert Werkzeugen die richtigen finden --
ohne dem Modell jedes Mal den ganzen Katalog vorzulegen.

Das ist die Voraussetzung dafür, dass ein großer Werkzeugkasten überhaupt
funktioniert. Bei 400 Tools wären die vollständigen Schemata grob 60.000
Token pro Anfrage -- mehr als das Kontextfenster. Nicht langsam, sondern
kaputt. Deshalb: erst suchen, dann die besten Treffer in den Prompt.

Die Suche ist bewusst **lokal und deterministisch**, kein Embedding-Dienst:

* gewichtete Begriffstreffer über Name, Beschreibung, Tags, Aliase und
  natürlichsprachliche Beispielsätze,
* unscharfer Namensvergleich über ``difflib`` für Tippfehler,
* Bonus für Favoriten und kürzlich Benutztes,
* Bonus für Tools, die zum aktuellen Kontext passen (Punkt 45).

Ein echter Vektorindex ließe sich später danebenstellen -- die Schnittstelle
(``search`` liefert bewertete Treffer) bliebe dieselbe. Was hier steht,
braucht keine zusätzliche Abhängigkeit, lädt nicht erst ein Modell und ist in
Millisekunden fertig; das ist für einen persönlichen Assistenten die bessere
Abwägung als ein Index, der beim Start zehn Sekunden kostet.
"""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Iterable

from .base import Registry, Tool
from .catalog import runnable

#: Diese Werkzeuge stehen dem Modell immer zur Verfügung, egal was gesucht
#: wurde -- sonst könnte eine schlechte Suche dem Agenten die Grundfähigkeiten
#: wegnehmen. Bewusst kurz gehalten.
CORE_TOOLS: tuple[str, ...] = (
    "read_file", "write_file", "list_dir", "search_files",
    "get_system_info", "memory_search", "memory_add",
    "jarvis.tools.search",
)

#: Wie viele Werkzeuge höchstens in eine Modellanfrage wandern.
DEFAULT_LIMIT = 14

_WORD = re.compile(r"[\wäöüßÄÖÜ]+", re.UNICODE)

#: Füllwörter, die als Suchbegriff nichts aussagen. Bewusst dieselbe Idee wie
#: in ``memory.py``, hier um Frageformen ergänzt.
_STOP = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einen", "einem", "eines",
    "einer", "für", "mit", "von", "vom", "zum", "zur", "auf", "aus", "bei",
    "nach", "über", "unter", "ist", "sind", "war", "hat", "habe", "haben",
    "wird", "werden", "kann", "soll", "muss", "mir", "mich", "sich", "wie",
    "was", "wer", "wann", "wo", "warum", "nicht", "kein", "keine", "noch",
    "schon", "sehr", "mal", "bitte", "dann", "du", "ich", "wir", "sie", "man",
    "des", "dem", "den", "im", "in", "an", "am", "zu", "es", "als", "auch",
    "jetzt", "gerade", "the", "and", "for", "with", "get", "show",
}


def _fold(text: str) -> str:
    """Kleinschreibung ohne Akzente -- damit „Grafikkarte Temperatur" und
    „grafikkarte temperatur" dasselbe finden."""
    lowered = (text or "").lower()
    return "".join(c for c in unicodedata.normalize("NFD", lowered)
                   if unicodedata.category(c) != "Mn")


def terms(text: str) -> list[str]:
    return [w for w in _WORD.findall(_fold(text)) if w and w not in _STOP]


@dataclass(frozen=True)
class Hit:
    tool: Tool
    score: float
    reason: str = ""

    def as_dict(self) -> dict:
        return {**self.tool.as_dict(), "score": round(self.score, 3),
                "treffer": self.reason}


@dataclass
class _Entry:
    """Ein Tool im Suchindex, vorberechnet."""

    tool: Tool
    name_folded: str
    #: Begriff → Gewicht. Name wiegt mehr als Beschreibung.
    weights: dict[str, float] = field(default_factory=dict)


# Gewichte je Fundort. Ein Treffer im Namen sagt deutlich mehr über die
# Absicht als einer irgendwo in der Beschreibung.
_W_NAME = 6.0
_W_ALIAS = 5.0
_W_TAG = 3.0
_W_PHRASE = 2.5
_W_CATEGORY = 1.5
_W_DESCRIPTION = 1.0


class ToolIndex:
    """Der Suchindex. Wird einmal beim Aufbau der Registry erzeugt."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self._entries: list[_Entry] = []
        self.rebuild()

    def rebuild(self) -> None:
        self._entries = [self._entry(tool) for tool in self.registry]

    def add(self, tool: Tool) -> None:
        """Ein einzelnes, neu hinzugekommenes Werkzeug nachtragen, ohne die
        übrigen Einträge neu zu berechnen -- z. B. für ``jarvis.tools.*``,
        das erst nach dem übrigen Katalog gebaut wird (siehe
        ``tools/__init__.py::build_registry``) und sonst einen zweiten
        vollständigen ``rebuild()`` über bereits indizierte Werkzeuge nötig
        machen würde."""
        self._entries.append(self._entry(tool))

    @staticmethod
    def _entry(tool: Tool) -> _Entry:
        weights: dict[str, float] = {}

        def feed(text: str, weight: float) -> None:
            for term in terms(text):
                weights[term] = weights.get(term, 0.0) + weight

        # Der gepunktete Name wird an den Punkten zerlegt: aus
        # "system.gpu.temperature" werden system, gpu, temperature.
        feed(tool.name.replace(".", " ").replace("_", " "), _W_NAME)
        for alias in tool.aliases:
            feed(alias.replace(".", " ").replace("_", " "), _W_ALIAS)
        for tag in tool.tags:
            feed(tag.replace("-", " "), _W_TAG)
        for phrase in tool.phrases:
            feed(phrase, _W_PHRASE)
        feed(f"{tool.category} {tool.subcategory}", _W_CATEGORY)
        feed(tool.description, _W_DESCRIPTION)
        return _Entry(tool=tool, name_folded=_fold(tool.name), weights=weights)

    # ------------------------------------------------------------- Suche
    def search(self, query: str, limit: int = DEFAULT_LIMIT, *,
               category: str | None = None, tags: Iterable[str] | None = None,
               include_unavailable: bool = True,
               boosts: dict[str, float] | None = None) -> list[Hit]:
        """Bewertete Treffer, beste zuerst.

        ``boosts`` sind Zuschläge je Tool-Name -- damit tragen Favoriten,
        kürzlich Benutztes und der aktuelle Kontext in das Ranking ein, ohne
        dass der Index davon etwas wissen muss.
        """
        wanted = terms(query)
        folded_query = _fold(query).strip()
        tag_filter = {t.lower() for t in (tags or [])}
        boosts = boosts or {}
        hits: list[Hit] = []

        for entry in self._entries:
            tool = entry.tool
            if category and tool.category != category:
                continue
            if tag_filter and not tag_filter & {t.lower() for t in tool.tags}:
                continue
            if not include_unavailable and not runnable(tool):
                continue

            score = 0.0
            matched: list[str] = []
            for term in wanted:
                weight = entry.weights.get(term)
                if weight:
                    score += weight
                    matched.append(term)
                    continue
                # Teiltreffer: "temp" findet "temperature".
                partial = max((w for t, w in entry.weights.items()
                               if len(term) >= 3 and t.startswith(term)), default=0.0)
                if partial:
                    score += partial * 0.6
                    matched.append(term)

            # Ein Tool, dessen Name die Anfrage wörtlich enthält, ist fast
            # immer gemeint ("gpu temp" → system.gpu.temperature).
            if folded_query and folded_query in entry.name_folded:
                score += 8.0
                matched.append(tool.name)
            elif folded_query and len(folded_query) >= 3:
                ratio = SequenceMatcher(None, folded_query, entry.name_folded).ratio()
                if ratio >= 0.62:
                    score += ratio * 4.0

            if not score:
                continue
            # Ein Werkzeug, das hier gar nicht laufen kann, soll nicht vor
            # einem stehen, das läuft -- aber auch nicht verschwinden, damit
            # Jarvis ehrlich sagen kann, dass es das Tool gäbe.
            if not runnable(tool):
                score *= 0.35
            score += boosts.get(tool.name, 0.0)
            hits.append(Hit(tool=tool, score=score,
                            reason=", ".join(dict.fromkeys(matched))))

        hits.sort(key=lambda h: (-h.score, h.tool.name))
        return hits[:max(1, int(limit or DEFAULT_LIMIT))]


class ToolDiscovery:
    """Die Auswahl, die vor jeder Modellanfrage getroffen wird.

    Merkt sich, was zuletzt benutzt wurde und was als Favorit markiert ist,
    und schlägt das entsprechend höher (Punkt 2, 37). Das Gedächtnis ist
    flüchtig-im-Prozess; dauerhaft liegt beides in ``history.py``.
    """

    #: Zuschlag für ein Werkzeug, das als Favorit markiert ist.
    FAVORITE_BOOST = 3.0
    #: Zuschlag für das zuletzt benutzte Werkzeug, linear abfallend.
    RECENT_BOOST = 2.0
    #: Zuschlag, wenn die Kategorie zum aktuellen Kontext passt (Punkt 45).
    CONTEXT_BOOST = 2.5

    #: Welche Kategorien zu welchem Vordergrund-Kontext gehören.
    CONTEXT_CATEGORIES: dict[str, tuple[str, ...]] = {
        "code": ("dev", "git", "python", "node", "files"),
        "browser": ("web", "net"),
        "terminal": ("dev", "system", "files"),
        "explorer": ("files",),
        "server": ("server", "docker", "nginx", "minecraft", "net"),
        "media": ("image", "audio", "video"),
    }

    def __init__(self, registry: Registry, index: ToolIndex | None = None,
                 history=None):
        self.registry = registry
        self.index = index or ToolIndex(registry)
        #: ``history.ToolHistory`` oder ``None`` -- ohne Historie funktioniert
        #: die Suche genauso, nur ohne Favoriten-/Verlaufsbonus.
        self.history = history
        self._recent: list[str] = []
        self.context: str = ""

    # ------------------------------------------------------- Rückmeldung
    def note_use(self, tool_name: str) -> None:
        name = self.registry.resolve(tool_name)
        self._recent = [n for n in self._recent if n != name][:19]
        self._recent.insert(0, name)

    def set_context(self, context: str) -> None:
        """Was gerade im Vordergrund ist (``code``, ``browser``, …). Woher das
        kommt, entscheidet der Aufrufer -- der Server kann es nicht selbst
        sehen, und es zu raten wäre schlechter als es offen zu lassen."""
        self.context = (context or "").strip().lower()

    @property
    def recent(self) -> list[str]:
        return list(self._recent)

    def _boosts(self) -> dict[str, float]:
        boosts: dict[str, float] = {}
        for position, name in enumerate(self._recent[:10]):
            boosts[name] = boosts.get(name, 0.0) + self.RECENT_BOOST * (1 - position / 10)
        if self.history is not None:
            for name in self.history.favorites():
                real = self.registry.resolve(name)
                boosts[real] = boosts.get(real, 0.0) + self.FAVORITE_BOOST
        categories = self.CONTEXT_CATEGORIES.get(self.context, ())
        if categories:
            for tool in self.registry:
                if tool.category in categories:
                    boosts[tool.name] = boosts.get(tool.name, 0.0) + self.CONTEXT_BOOST
        return boosts

    # ------------------------------------------------------------- Suche
    def search(self, query: str, limit: int = DEFAULT_LIMIT, **kwargs) -> list[Hit]:
        started = time.perf_counter()
        hits = self.index.search(query, limit=limit, boosts=self._boosts(), **kwargs)
        self.last_search_ms = (time.perf_counter() - started) * 1000
        return hits

    def select(self, request: str, limit: int = DEFAULT_LIMIT) -> list[str]:
        """Die Werkzeugnamen für **eine** Modellanfrage: die Kernwerkzeuge
        plus die besten Treffer zur Anfrage.

        Die Kernwerkzeuge stehen bewusst immer dabei. Eine Suche, die nichts
        findet, darf Jarvis nicht handlungsunfähig machen -- er soll dann
        immer noch lesen, schreiben und im Gedächtnis suchen können.
        """
        chosen: dict[str, None] = {}
        for name in CORE_TOOLS:
            if name in self.registry:
                chosen[self.registry.resolve(name)] = None
        for hit in self.search(request, limit=limit):
            chosen[hit.tool.name] = None
        return list(chosen)

    def schemas_for(self, request: str, limit: int = DEFAULT_LIMIT) -> list[dict]:
        return self.registry.schemas(only=self.select(request, limit=limit))
