"""Start: ``python -m jarvis``.

Der erste Start legt die Konfiguration an und sagt, was noch fehlt — statt mit
Standardwerten loszulaufen, von denen der Nutzer nichts weiß.
"""

from __future__ import annotations

import argparse
import secrets
import sys

from .config import Config


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

    if args.init or not config.config_path.is_file():
        path = config.save()
        print(f"Konfiguration: {path}")
        print(f"Arbeitsbereich: {', '.join(config.roots) or '(leer)'}")
        print(f"Gedächtnis: {config.db_path}")
        if args.init:
            return 0

    for problem in config.validate():
        print(f"  ACHTUNG  {problem}", file=sys.stderr)

    if config.token:
        print(f"Token: {config.token}")
        print(f"Adresse: http://{config.host}:{config.port}/?token={config.token}")
    else:
        print(f"Adresse: http://{config.host}:{config.port}/")

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
