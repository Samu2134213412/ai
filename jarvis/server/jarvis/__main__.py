"""Start: ``python -m jarvis``.

Der erste Start legt die Konfiguration an und sagt, was noch fehlt — statt mit
Standardwerten loszulaufen, von denen der Nutzer nichts weiß.
"""

from __future__ import annotations

import argparse
import secrets
import socket
import sys
from pathlib import Path

from .config import Config


def lan_addresses() -> list[str]:
    """Die Adressen, unter denen dieser Rechner im eigenen Netz erreichbar ist.

    Nötig, weil ``0.0.0.0`` zwar die richtige Bind-Adresse ist, aber als
    Ziel nichts taugt: wer sie auf dem Handy eintippt, landet nirgends. Die
    Route wird über einen UDP-Socket ermittelt, der nichts verschickt --
    ``connect`` wählt bei UDP nur die Schnittstelle aus.
    """
    gefunden: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 53))  # TEST-NET-1, erreicht niemanden
            gefunden.append(probe.getsockname()[0])
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None,
                                       family=socket.AF_INET):
            adresse = info[4][0]
            if adresse not in gefunden and not adresse.startswith("127."):
                gefunden.append(adresse)
    except OSError:
        pass
    return gefunden


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis", description="Jarvis-Server")
    parser.add_argument("--config", help="Pfad zur jarvis.json")
    parser.add_argument("--host", help="Bind-Adresse, überschreibt die Konfiguration")
    parser.add_argument("--port", type=int, help="Port, überschreibt die Konfiguration")
    parser.add_argument("--init", action="store_true",
                        help="Konfiguration anlegen und beenden")
    parser.add_argument("--open-network", action="store_true",
                        help="Auf 0.0.0.0 binden und ein Token erzeugen, "
                             "damit das Handy sich verbinden kann")
    args = parser.parse_args(argv)

    config = Config.load(args.config)
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.open_network:
        config.host = "0.0.0.0"  # noqa: S104 - ausdrücklich angefordert
        if not config.token:
            config.token = secrets.token_urlsafe(24)

    gewuenscht = args.config or config.config_path
    if args.init or not Path(gewuenscht).is_file():
        path = config.save(args.config)
        print(f"Konfiguration: {path}")
        print(f"Arbeitsbereich: {', '.join(config.roots) or '(leer)'}")
        print(f"Gedächtnis: {config.db_path}")
        if args.init:
            return 0

    for problem in config.validate():
        print(f"  ACHTUNG  {problem}", file=sys.stderr)

    frage = f"?token={config.token}" if config.token else ""
    if config.token:
        print(f"Token: {config.token}")
    if config.host in ("0.0.0.0", "::"):  # noqa: S104 - nur der Vergleich
        # 0.0.0.0 ist die richtige Bind-Adresse, aber kein Ziel. Wer sie
        # aufs Handy tippt, landet nirgends -- also stehen hier die echten.
        print(f"Adresse (dieser Rechner): http://127.0.0.1:{config.port}/{frage}")
        adressen = lan_addresses()
        if adressen:
            print("Adresse (Handy, im selben WLAN):")
            for adresse in adressen:
                print(f"  http://{adresse}:{config.port}/{frage}")
        else:
            print("  ACHTUNG  Es war keine Netzwerkadresse zu ermitteln. "
                  "Der Server lauscht, aber ich kann dir nicht sagen, "
                  "unter welcher Adresse.", file=sys.stderr)
    else:
        print(f"Adresse: http://{config.host}:{config.port}/{frage}")
        if config.is_loopback:
            print("Nur von diesem Rechner erreichbar. Fürs Handy: "
                  "python -m jarvis --open-network")

    try:
        import uvicorn
    except ImportError:
        print("uvicorn fehlt. Installation: pip install -r requirements.txt",
              file=sys.stderr)
        return 1

    from .app import create_app
    uvicorn.run(create_app(config), host=config.host, port=config.port,
                log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
