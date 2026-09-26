"""Baut Website-Installer.bat aus den Dateien in src/.

Das Ergebnis ist EINE Datei, die man auf einem Windows-PC doppelklickt. Sie
enthaelt den PowerShell-Installer (Base64) und alle Programmdateien.

    python build.py
"""
import base64
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
SRC = HERE / "src"
OUT = HERE / "Website-Installer.bat"

STUB = r"""@echo off
REM ==================================================================
REM  Website-Installer - einfach doppelklicken.
REM  Richtet auf diesem PC eine eigene Website ein - einfach oder mit
REM  WordPress, lokal oder unter deiner Domain. Der Rest dieser Datei ist der
REM  eigentliche Installer in verpackter Form - bitte nicht aendern.
REM ==================================================================
setlocal
set "WI_SELF=%~f0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t=[IO.File]::ReadAllText($env:WI_SELF); $i=$t.LastIndexOf('::PAY'+'LOAD::'); $s=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($t.Substring($i+11))); $f=Join-Path $env:TEMP 'website-installer.ps1'; [IO.File]::WriteAllText($f,$s,(New-Object Text.UTF8Encoding $true)); & $f"
echo.
pause
exit /b
::PAYLOAD::
"""


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def main() -> None:
    installer = (SRC / "install.ps1").read_text(encoding="utf-8")
    for name in ("server.ps1", "host.ps1", "uninstall.ps1", "admin.html", "login.html", "start.html",
                 "wordpress/wp-config.php", "wordpress/wp-setup.php", "wordpress/website-schutz.php",
                 "wordpress/Caddyfile"):
        placeholder = f"__B64_{name}__"
        assert placeholder in installer, placeholder
        installer = installer.replace(placeholder, b64((SRC / name).read_bytes()))

    payload = b64(installer.encode("utf-8"))
    lines = [payload[i:i + 76] for i in range(0, len(payload), 76)]
    text = STUB + "\n".join(lines) + "\n"
    # Batch-Dateien brauchen Windows-Zeilenenden.
    OUT.write_bytes(text.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii"))
    print(f"{OUT.name}: {OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
