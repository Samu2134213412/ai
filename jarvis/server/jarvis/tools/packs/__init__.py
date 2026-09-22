"""Die Tool-Packs.

Aufgabenstellung Punkt 38: die Werkzeuge liegen **nicht** hart im Kern,
sondern in Packs, die sich einzeln hinzufügen und weglassen lassen. Ein Pack
ist ein Modul mit einer einzigen Funktion:

    def build(ctx: ToolContext) -> list[Tool]

Mehr nicht. Es kennt weder die Registry noch ``app.py`` noch ein anderes
Pack -- das ist die Voraussetzung dafür, dass später auch fremde Pakete
Werkzeuge beisteuern können (Punkt 39), ohne dass eines davon die anderen
umbauen könnte.

Scheitert ein Pack beim Bauen, fehlen genau seine Werkzeuge; die übrigen
laufen weiter, und der Grund steht in ``registry.pack_errors``. Ein
Werkzeugkasten, den ein einzelnes kaputtes Fach komplett lahmlegt, wäre bei
dieser Menge an Fächern nicht zu betreiben.
"""

from __future__ import annotations

from typing import Callable

from . import db, dev, docker, fs, git, media, minecraft, net, nginx, sysinfo, text

#: Reihenfolge = Ladereihenfolge. Sie ist ohne Bedeutung für das Ergebnis
#: (Namen sind eindeutig), macht aber die Fehlersuche vorhersagbar.
PACKS: tuple[tuple[str, Callable], ...] = (
    ("fs", fs.build),
    ("text", text.build),
    ("sysinfo", sysinfo.build),
    ("net", net.build),
    ("git", git.build),
    ("dev", dev.build),
    ("media", media.build),
    ("docker", docker.build),
    ("nginx", nginx.build),
    ("minecraft", minecraft.build),
    ("db", db.build),
)

__all__ = ["PACKS"]
