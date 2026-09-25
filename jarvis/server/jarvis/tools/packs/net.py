"""Tool Pack: Netzwerk.

Ausdrücklich **keine** offensiven Werkzeuge. Kein Portscanner über fremde
Bereiche, kein Paketinjektor, kein Passwortversuch. Was hier steht, ist
Diagnose: Läuft der Dienst? Kommt das Paket an? Wohin zeigt der Name?
Warum ist die Verbindung langsam?

Die Grenze ist nicht willkürlich, sie ist praktisch: Jarvis läuft auf dem
Rechner seines Nutzers und soll dessen Probleme lösen. Ein Werkzeug, mit dem
sich fremde Netze durchsuchen lassen, löst keines davon.

``port.check`` prüft **einen** Port an **einem** Host -- die Frage „läuft
mein Minecraft-Server noch". ``local.ports`` zeigt die offenen Ports des
eigenen Rechners. Ein Bereichsscan über fremde Adressen gibt es nicht.
"""

from __future__ import annotations

import ipaddress
import json
import re
import shutil
import socket
import ssl
import time
import urllib.parse
from pathlib import Path

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, current_platform, run_process
from ._base import (INT, NO_PARAMS, STR, human_bytes, integer, ok,
                    params, table, text)

try:  # pragma: no cover
    import httpx
except ImportError:  # pragma: no cover
    httpx = None

try:  # pragma: no cover
    import psutil
except ImportError:  # pragma: no cover
    psutil = None

#: Obergrenze für einen Download über ``http.download`` -- ein Werkzeug, das
#: unbegrenzt zieht, füllt irgendwann die Platte.
MAX_DOWNLOAD = 50 * 1024 * 1024
DEFAULT_TIMEOUT = 10.0


def _httpx():
    if httpx is None:
        raise ToolError("Dafür fehlt das Paket 'httpx': pip install httpx")
    return httpx


def _host(value: str) -> str:
    host = (value or "").strip()
    if not host:
        raise ToolError("Es wurde kein Host angegeben.")
    # Ein Hostname mit Leerzeichen oder Steuerzeichen ist keiner -- und
    # wäre der Weg, aus einem Argument einen zweiten Befehl zu machen.
    if re.search(r"[\s;|&`$<>]", host):
        raise ToolError(f"Kein gültiger Hostname: {host!r}")
    return host


def _url(value: str) -> str:
    url = (value or "").strip()
    if not url:
        raise ToolError("Es wurde keine URL angegeben.")
    if "://" not in url:
        url = "https://" + url
    teile = urllib.parse.urlparse(url)
    if teile.scheme not in ("http", "https"):
        raise ToolError(f"Nur http und https, nicht {teile.scheme!r}.")
    if not teile.netloc:
        raise ToolError(f"Die URL hat keinen Host: {value!r}")
    return url


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    # ══════════════════════════════════════════════════════════════ Namen
    def dns_lookup(host: str, record: str = "A") -> ToolResult:
        name = _host(host)
        art = (record or "A").upper()
        if art in ("A", "AAAA", "ANY"):
            familie = {"A": socket.AF_INET, "AAAA": socket.AF_INET6,
                       "ANY": 0}[art]
            try:
                infos = socket.getaddrinfo(name, None, family=familie,
                                           type=socket.SOCK_STREAM)
            except socket.gaierror as exc:
                raise ToolError(f"Name nicht auflösbar: {name} ({exc.strerror})") from exc
            adressen = sorted({i[4][0] for i in infos})
            return ok("net.dns.lookup", f"{name} → {', '.join(adressen)}",
                      payload="\n".join(adressen), host=name, adressen=len(adressen),
                      art=art)
        # Andere Satzarten brauchen ein echtes DNS-Werkzeug.
        if not shutil.which("dig"):
            raise ToolError(f"Für {art}-Einträge fehlt 'dig' (Paket dnsutils). "
                            "A und AAAA gehen auch ohne.")
        res = run_process(["dig", "+short", name, art], timeout=15)
        werte = [z for z in res.stdout.splitlines() if z.strip()]
        return ok("net.dns.lookup", f"{len(werte)} {art}-Einträge für {name}",
                  payload="\n".join(werte) or "(keine)", host=name, art=art,
                  eintraege=len(werte))

    def dns_reverse(ip: str) -> ToolResult:
        try:
            adresse = str(ipaddress.ip_address((ip or "").strip()))
        except ValueError as exc:
            raise ToolError(f"Keine gültige IP-Adresse: {ip!r}") from exc
        try:
            name, _, _ = socket.gethostbyaddr(adresse)
        except (socket.herror, socket.gaierror) as exc:
            raise ToolError(f"Kein Rückwärtseintrag für {adresse}: {exc}") from exc
        return ok("net.dns.reverse", f"{adresse} → {name}", payload=name,
                  ip=adresse, name=name)

    def dns_servers() -> ToolResult:
        conf = Path("/etc/resolv.conf")
        if conf.is_file():
            server = [l.split()[1] for l in conf.read_text(errors="replace").splitlines()
                      if l.strip().startswith("nameserver") and len(l.split()) > 1]
            return ok("net.dns.servers", f"{len(server)} DNS-Server",
                      payload="\n".join(server), quelle=str(conf), anzahl=len(server))
        if current_platform() == "windows":
            res = run_process(["powershell", "-NoProfile", "-Command",
                               "Get-DnsClientServerAddress | "
                               "Select-Object InterfaceAlias,ServerAddresses | "
                               "Format-Table -Auto"], timeout=30)
            if res.returncode == 0:
                return ok("net.dns.servers", "DNS-Server gelesen",
                          payload=res.stdout[:3000], quelle="Get-DnsClientServerAddress")
        raise ToolError("Die DNS-Server lassen sich auf diesem System nicht lesen.")

    # ═══════════════════════════════════════════════════════ Erreichbarkeit
    def ping_host(host: str, count: int = 4, timeout: int = 5) -> ToolResult:
        name = _host(host)
        anzahl = max(1, min(int(count or 4), 20))
        if not shutil.which("ping"):
            raise ToolError("Auf diesem System gibt es kein 'ping'.")
        if current_platform() == "windows":
            args = ["ping", "-n", str(anzahl), "-w", str(int(timeout or 5) * 1000), name]
        else:
            args = ["ping", "-c", str(anzahl), "-W", str(max(1, int(timeout or 5))), name]
        res = run_process(args, timeout=anzahl * max(1, int(timeout or 5)) + 10)
        zeiten = [float(m) for m in re.findall(r"time[=<]\s*([\d.]+)\s*ms", res.stdout)]
        verlust = re.search(r"([\d.]+)\s*%\s*(?:packet\s+)?loss|"
                            r"\((\d+)%\s*Verlust\)", res.stdout)
        erreichbar = bool(zeiten)
        if not erreichbar:
            raise ToolError(f"{name} antwortet nicht auf ping. "
                            f"Ausgabe: {(res.stdout or res.stderr).strip()[:200]}")
        return ok("net.ping", f"{name}: {len(zeiten)}/{anzahl} Antworten, "
                              f"im Mittel {sum(zeiten) / len(zeiten):.1f} ms",
                  payload=res.stdout[:2000], host=name, antworten=len(zeiten),
                  gesendet=anzahl,
                  mittel_ms=round(sum(zeiten) / len(zeiten), 2),
                  bestes_ms=round(min(zeiten), 2), schlechtestes_ms=round(max(zeiten), 2),
                  verlust_prozent=float(verlust.group(1) or verlust.group(2))
                  if verlust else None)

    def port_check(host: str, port: int, timeout: float = 3.0) -> ToolResult:
        """Ein Port, ein Host -- die Frage 'läuft mein Server noch'. Kein
        Bereichsscan: dafür gibt es hier bewusst kein Werkzeug."""
        name = _host(host)
        nummer = int(port or 0)
        if not 1 <= nummer <= 65535:
            raise ToolError(f"Kein gültiger Port: {port}")
        frist = max(0.2, min(float(timeout or 3.0), 30.0))
        begonnen = time.perf_counter()
        try:
            with socket.create_connection((name, nummer), timeout=frist):
                dauer = (time.perf_counter() - begonnen) * 1000
        except socket.timeout:
            return ok("net.port.check",
                      f"{name}:{nummer} antwortet nicht (Zeitüberschreitung nach {frist} s)",
                      host=name, port=nummer, offen=False, grund="timeout")
        except OSError as exc:
            return ok("net.port.check", f"{name}:{nummer} ist zu ({exc.strerror or exc})",
                      host=name, port=nummer, offen=False, grund=str(exc.strerror or exc))
        return ok("net.port.check", f"{name}:{nummer} ist offen ({dauer:.0f} ms)",
                  host=name, port=nummer, offen=True, dauer_ms=round(dauer, 1))

    def trace_route(host: str, max_hops: int = 20) -> ToolResult:
        name = _host(host)
        programm = ("tracert" if current_platform() == "windows"
                    else "traceroute" if shutil.which("traceroute") else "")
        if not programm or not shutil.which(programm):
            raise ToolError("Weder 'traceroute' noch 'tracert' ist vorhanden.")
        sprünge = max(1, min(int(max_hops or 20), 40))
        args = ([programm, "-h", str(sprünge), name] if programm == "tracert"
                else [programm, "-m", str(sprünge), "-w", "2", name])
        res = run_process(args, timeout=sprünge * 4 + 20)
        zeilen = [l for l in res.stdout.splitlines() if l.strip()]
        return ok("net.traceroute", f"{len(zeilen)} Zeilen bis {name}",
                  payload=res.stdout[:4000], host=name, zeilen=len(zeilen))

    def latency_monitor(host: str, samples: int = 5, delay: float = 0.5) -> ToolResult:
        """Mehrere TCP-Verbindungsversuche hintereinander -- zeigt Schwankungen,
        die ein einzelner ping nicht sichtbar macht."""
        name = _host(host)
        anzahl = max(2, min(int(samples or 5), 30))
        pause = max(0.0, min(float(delay or 0.5), 5.0))
        zeiten, fehler = [], 0
        for i in range(anzahl):
            begonnen = time.perf_counter()
            try:
                with socket.create_connection((name, 443), timeout=3.0):
                    zeiten.append((time.perf_counter() - begonnen) * 1000)
            except OSError:
                fehler += 1
            if i < anzahl - 1:
                time.sleep(pause)
        if not zeiten:
            raise ToolError(f"{name}:443 war bei keinem von {anzahl} Versuchen "
                            "erreichbar.")
        schnitt = sum(zeiten) / len(zeiten)
        schwankung = max(zeiten) - min(zeiten)
        return ok("net.latency.monitor",
                  f"{name}: {schnitt:.0f} ms im Mittel, Schwankung {schwankung:.0f} ms, "
                  f"{fehler} Fehlversuche",
                  host=name, versuche=anzahl, erfolge=len(zeiten), fehler=fehler,
                  mittel_ms=round(schnitt, 1), schwankung_ms=round(schwankung, 1),
                  bestes_ms=round(min(zeiten), 1), schlechtestes_ms=round(max(zeiten), 1))

    # ═══════════════════════════════════════════════════════ Eigener Rechner
    def local_ip() -> ToolResult:
        # Ein UDP-"Verbindungsaufbau" verschickt nichts, wählt aber die
        # Route -- so kommt man an die Adresse, über die der Rechner
        # tatsächlich nach draußen geht.
        adresse = ""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("192.0.2.1", 53))  # TEST-NET-1, erreicht niemanden
                adresse = s.getsockname()[0]
        except OSError:
            adresse = socket.gethostbyname(socket.gethostname())
        return ok("net.local.ip", f"Lokale IP: {adresse}", payload=adresse,
                  ip=adresse, rechner=socket.gethostname())

    def public_ip(timeout: float = 8.0) -> ToolResult:
        """Die öffentliche Adresse lässt sich nur von außen erfahren -- dafür
        wird ein fremder Dienst gefragt. Das ist eine Netzverbindung nach
        draußen, deshalb READ und nicht SAFE."""
        client = _httpx()
        for url in ("https://api.ipify.org", "https://ifconfig.me/ip"):
            try:
                res = client.get(url, timeout=float(timeout or 8.0))
                if res.status_code == 200 and res.text.strip():
                    wert = res.text.strip()[:64]
                    return ok("net.public.ip", f"Öffentliche IP: {wert}", payload=wert,
                              ip=wert, quelle=url)
            except Exception:  # noqa: BLE001 - nächster Dienst
                continue
        raise ToolError("Die öffentliche IP war über keinen der geprüften "
                        "Dienste zu erfahren (kein Internet?).")

    def interfaces() -> ToolResult:
        if psutil is None:
            raise ToolError("Dafür fehlt 'psutil': pip install psutil")
        rows = []
        zustaende = psutil.net_if_stats()
        for name, adressen in psutil.net_if_addrs().items():
            stat = zustaende.get(name)
            ipv4 = next((a.address for a in adressen if a.family == socket.AF_INET), "—")
            mac = next((a.address for a in adressen
                        if getattr(a.family, "name", "") == "AF_PACKET"
                        or int(a.family) == 17), "—")
            rows.append([name, ipv4, mac,
                         "oben" if stat and stat.isup else "unten",
                         f"{stat.speed} Mbit/s" if stat and stat.speed else "—"])
        return ok("net.interfaces", f"{len(rows)} Netzwerkadapter",
                  payload=table(rows, ["adapter", "ipv4", "mac", "zustand", "tempo"]),
                  anzahl=len(rows),
                  aktiv=sum(1 for r in rows if r[3] == "oben"))

    def local_ports(limit: int = 40) -> ToolResult:
        if psutil is None:
            raise ToolError("Dafür fehlt 'psutil': pip install psutil")
        rows = []
        for verbindung in psutil.net_connections(kind="inet"):
            if verbindung.status != psutil.CONN_LISTEN or not verbindung.laddr:
                continue
            name = "?"
            if verbindung.pid:
                try:
                    name = psutil.Process(verbindung.pid).name()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    name = "(kein Zugriff)"
            rows.append([verbindung.laddr.port, verbindung.laddr.ip,
                         verbindung.pid or "—", name])
        rows.sort(key=lambda r: r[0])
        return ok("net.local.ports", f"{len(rows)} lauschende Ports",
                  payload=table(rows[:max(1, int(limit or 40))],
                                ["port", "adresse", "pid", "programm"]),
                  anzahl=len(rows))

    def connections(limit: int = 40, state: str = "") -> ToolResult:
        if psutil is None:
            raise ToolError("Dafür fehlt 'psutil': pip install psutil")
        rows = []
        for v in psutil.net_connections(kind="inet"):
            if state and v.status != state.upper():
                continue
            if not v.raddr:
                continue
            rows.append([f"{v.laddr.ip}:{v.laddr.port}",
                         f"{v.raddr.ip}:{v.raddr.port}", v.status, v.pid or "—"])
        return ok("net.connections", f"{len(rows)} bestehende Verbindungen",
                  payload=table(rows[:max(1, int(limit or 40))],
                                ["lokal", "entfernt", "status", "pid"]),
                  anzahl=len(rows))

    def traffic() -> ToolResult:
        if psutil is None:
            raise ToolError("Dafür fehlt 'psutil': pip install psutil")
        io = psutil.net_io_counters()
        return ok("net.traffic",
                  f"{human_bytes(io.bytes_recv)} empfangen, "
                  f"{human_bytes(io.bytes_sent)} gesendet (seit dem Systemstart)",
                  empfangen_bytes=io.bytes_recv, gesendet_bytes=io.bytes_sent,
                  pakete_rein=io.packets_recv, pakete_raus=io.packets_sent,
                  fehler=io.errin + io.errout, verworfen=io.dropin + io.dropout)

    def traffic_rate(seconds: float = 2.0) -> ToolResult:
        """Zwei Messungen mit Pause dazwischen. Die Zählerstände allein sagen
        nichts über die aktuelle Rate -- erst die Differenz tut das."""
        if psutil is None:
            raise ToolError("Dafür fehlt 'psutil': pip install psutil")
        spanne = max(0.5, min(float(seconds or 2.0), 10.0))
        vorher = psutil.net_io_counters()
        time.sleep(spanne)
        nachher = psutil.net_io_counters()
        rein = (nachher.bytes_recv - vorher.bytes_recv) / spanne
        raus = (nachher.bytes_sent - vorher.bytes_sent) / spanne
        return ok("net.traffic.rate",
                  f"{human_bytes(rein)}/s rein, {human_bytes(raus)}/s raus",
                  gemessen_s=spanne, rein_bytes_s=round(rein),
                  raus_bytes_s=round(raus))

    def arp_table(limit: int = 40) -> ToolResult:
        programm = "arp"
        if not shutil.which(programm):
            if not shutil.which("ip"):
                raise ToolError("Weder 'arp' noch 'ip' ist vorhanden.")
            res = run_process(["ip", "neigh"], timeout=15)
        else:
            res = run_process([programm, "-a"], timeout=15)
        zeilen = [l for l in res.stdout.splitlines() if l.strip()]
        return ok("net.arp.table", f"{len(zeilen)} Nachbarn im lokalen Netz",
                  payload="\n".join(zeilen[:max(1, int(limit or 40))]),
                  anzahl=len(zeilen))

    def gateway() -> ToolResult:
        if shutil.which("ip"):
            res = run_process(["ip", "route", "show", "default"], timeout=10)
            treffer = re.search(r"default via (\S+) dev (\S+)", res.stdout)
            if treffer:
                return ok("net.gateway",
                          f"Gateway {treffer.group(1)} über {treffer.group(2)}",
                          gateway=treffer.group(1), adapter=treffer.group(2))
        if current_platform() == "windows":
            res = run_process(["route", "print", "0.0.0.0"], timeout=20)
            if res.returncode == 0:
                return ok("net.gateway", "Standardroute gelesen",
                          payload=res.stdout[:2000])
        raise ToolError("Die Standardroute lässt sich auf diesem System nicht lesen.")

    def wifi_networks() -> ToolResult:
        if current_platform() == "windows":
            res = run_process(["netsh", "wlan", "show", "networks", "mode=bssid"],
                              timeout=30)
            if res.returncode:
                raise ToolError(f"netsh schlug fehl: {res.stderr.strip()[:200]}")
            return ok("net.wifi.networks", "WLAN-Netze gelesen",
                      payload=res.stdout[:6000])
        if shutil.which("nmcli"):
            res = run_process(["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY",
                               "device", "wifi", "list"], timeout=30)
            zeilen = [l for l in res.stdout.splitlines() if l.strip()]
            rows = [l.split(":")[:3] for l in zeilen]
            return ok("net.wifi.networks", f"{len(rows)} WLAN-Netze",
                      payload=table(rows, ["ssid", "signal", "sicherheit"]),
                      anzahl=len(rows))
        raise ToolError("Weder 'netsh' (Windows) noch 'nmcli' (Linux) vorhanden -- "
                        "WLAN-Netze lassen sich hier nicht auflisten.")

    def dns_flush() -> ToolResult:
        system = current_platform()
        if system == "windows":
            res = run_process(["ipconfig", "/flushdns"], timeout=30)
        elif shutil.which("resolvectl"):
            res = run_process(["resolvectl", "flush-caches"], timeout=30)
        else:
            raise ToolError("Kein bekannter DNS-Zwischenspeicher auf diesem System.")
        if res.returncode:
            raise ToolError(f"Leeren fehlgeschlagen: "
                            f"{(res.stderr or res.stdout).strip()[:200]}")
        return ok("net.dns.flush", "DNS-Zwischenspeicher geleert",
                  system=system)

    # ══════════════════════════════════════════════════════════════ HTTP
    def http_status(url: str, timeout: float = DEFAULT_TIMEOUT) -> ToolResult:
        client = _httpx()
        ziel = _url(url)
        begonnen = time.perf_counter()
        try:
            res = client.head(ziel, timeout=float(timeout or DEFAULT_TIMEOUT),
                              follow_redirects=True)
            if res.status_code >= 400:  # manche Server mögen HEAD nicht
                res = client.get(ziel, timeout=float(timeout or DEFAULT_TIMEOUT),
                                 follow_redirects=True)
        except Exception as exc:  # noqa: BLE001 - httpx kennt viele Fehlerarten
            raise ToolError(f"{ziel} war nicht erreichbar: {exc}") from exc
        dauer = (time.perf_counter() - begonnen) * 1000
        return ok("net.http.status",
                  f"{res.status_code} {res.reason_phrase} in {dauer:.0f} ms",
                  url=ziel, status=res.status_code, erreichbar=res.status_code < 400,
                  dauer_ms=round(dauer), endziel=str(res.url),
                  umleitungen=len(res.history))

    def http_headers(url: str, timeout: float = DEFAULT_TIMEOUT) -> ToolResult:
        client = _httpx()
        ziel = _url(url)
        try:
            res = client.get(ziel, timeout=float(timeout or DEFAULT_TIMEOUT),
                             follow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"{ziel} war nicht erreichbar: {exc}") from exc
        rows = [[k, v[:120]] for k, v in res.headers.items()]
        return ok("net.http.headers", f"{len(rows)} Kopfzeilen von {ziel}",
                  payload=table(rows, ["kopfzeile", "wert"]),
                  url=ziel, status=res.status_code, anzahl=len(rows))

    def http_get(url: str, timeout: float = DEFAULT_TIMEOUT,
                 max_chars: int = 20000) -> ToolResult:
        client = _httpx()
        ziel = _url(url)
        try:
            res = client.get(ziel, timeout=float(timeout or DEFAULT_TIMEOUT),
                             follow_redirects=True)
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"{ziel} war nicht erreichbar: {exc}") from exc
        grenze = max(500, min(int(max_chars or 20000), 200_000))
        inhalt = res.text[:grenze]
        return ok("net.http.get", f"{res.status_code}, {len(res.text)} Zeichen",
                  payload=inhalt, url=ziel, status=res.status_code,
                  typ=res.headers.get("content-type", ""),
                  gekuerzt=len(res.text) > grenze)

    def http_download(url: str, path: str, timeout: float = 60.0) -> ToolResult:
        """Lädt in den Arbeitsbereich -- und nur dorthin. Die Größe ist
        begrenzt, damit ein Werkzeug nicht die Platte füllt."""
        client = _httpx()
        ziel_url = _url(url)
        ziel = ws.resolve(path)
        geschrieben = 0
        try:
            with client.stream("GET", ziel_url, follow_redirects=True,
                               timeout=float(timeout or 60.0)) as res:
                if res.status_code >= 400:
                    raise ToolError(f"{ziel_url} antwortete mit {res.status_code}.")
                ziel.parent.mkdir(parents=True, exist_ok=True)
                with open(ziel, "wb") as fh:
                    for brocken in res.iter_bytes():
                        geschrieben += len(brocken)
                        if geschrieben > MAX_DOWNLOAD:
                            fh.close()
                            ziel.unlink(missing_ok=True)
                            raise ToolError(
                                f"Abgebrochen: die Datei ist größer als "
                                f"{human_bytes(MAX_DOWNLOAD)}. Nichts wurde behalten.")
                        fh.write(brocken)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            ziel.unlink(missing_ok=True)
            raise ToolError(f"Download fehlgeschlagen: {exc}") from exc
        # Der Beleg kommt von der Festplatte, nicht vom Zähler.
        tatsaechlich = ziel.stat().st_size
        return ok("net.http.download",
                  f"{human_bytes(tatsaechlich)} nach {ziel.name} geladen",
                  url=ziel_url, pfad=str(ziel), bytes=tatsaechlich)

    def url_parse(url: str) -> ToolResult:
        teile = urllib.parse.urlparse(_url(url))
        werte = {"schema": teile.scheme, "host": teile.hostname or "",
                 "port": teile.port or ("443" if teile.scheme == "https" else "80"),
                 "pfad": teile.path or "/", "abfrage": teile.query or "",
                 "fragment": teile.fragment or ""}
        parameter = urllib.parse.parse_qs(teile.query)
        return ok("net.url.parse", f"{werte['host']}{werte['pfad']}",
                  payload="\n".join(f"{k}: {v}" for k, v in werte.items())
                  + ("\n\nParameter:\n" + "\n".join(f"  {k} = {', '.join(v)}"
                                                    for k, v in parameter.items())
                     if parameter else ""),
                  **werte, parameter=len(parameter))

    def ssl_certificate(host: str, port: int = 443,
                        timeout: float = 8.0) -> ToolResult:
        name = _host(host)
        kontext = ssl.create_default_context()
        try:
            with socket.create_connection((name, int(port or 443)),
                                          timeout=float(timeout or 8.0)) as roh:
                with kontext.wrap_socket(roh, server_hostname=name) as sicher:
                    zertifikat = sicher.getpeercert()
                    protokoll = sicher.version()
        except ssl.SSLCertVerificationError as exc:
            raise ToolError(f"Das Zertifikat von {name} ist nicht gültig: "
                            f"{exc.verify_message or exc}") from exc
        except OSError as exc:
            raise ToolError(f"{name}:{port} war nicht erreichbar: {exc}") from exc
        bis = zertifikat.get("notAfter", "")
        rest_tage = None
        try:
            rest_tage = int((ssl.cert_time_to_seconds(bis) - time.time()) // 86400)
        except (ValueError, TypeError):
            pass
        aussteller = dict(x[0] for x in zertifikat.get("issuer", []) if x)
        return ok("net.ssl.certificate",
                  f"{name}: gültig bis {bis}"
                  + (f" (noch {rest_tage} Tage)" if rest_tage is not None else ""),
                  payload=json.dumps(zertifikat, ensure_ascii=False, indent=2,
                                     default=str)[:4000],
                  host=name, gueltig_bis=bis, rest_tage=rest_tage,
                  aussteller=aussteller.get("organizationName", ""),
                  protokoll=protokoll)

    def hostname() -> ToolResult:
        name = socket.gethostname()
        return ok("net.hostname", name, payload=name, rechner=name,
                  fqdn=socket.getfqdn())

    return [
        # Namen
        Tool("net.dns.lookup", "Löst einen Hostnamen zu IP-Adressen auf.",
             params("host", host=text("Der Hostname"),
                    record=text("A (Vorgabe), AAAA, ANY, MX, TXT, NS …")),
             dns_lookup, level=P.READ, tags=("dns", "netzwerk"),
             phrases=("welche ip hat", "dns auflösen", "nslookup")),
        Tool("net.dns.reverse", "Findet den Hostnamen zu einer IP-Adresse.",
             params("ip", ip=text("Die IP-Adresse")), dns_reverse, level=P.READ,
             tags=("dns", "netzwerk")),
        Tool("net.dns.servers", "Welche DNS-Server dieser Rechner benutzt.",
             NO_PARAMS, dns_servers, level=P.READ, tags=("dns",)),
        Tool("net.dns.flush", "Leert den DNS-Zwischenspeicher des Systems.",
             NO_PARAMS, dns_flush, level=P.SYSTEM, tags=("dns", "reparatur"),
             phrases=("dns cache leeren",)),

        # Erreichbarkeit
        Tool("net.ping", "Prüft mit ping, ob ein Host antwortet, und wie schnell.",
             params("host", host=STR, count=integer("Pakete, Vorgabe 4"), timeout=INT),
             ping_host, level=P.READ, tags=("netzwerk", "diagnose"),
             returns="Antwortzahl, mittlere, beste und schlechteste Zeit",
             phrases=("ping mal", "ist der server erreichbar", "antwortet der host")),
        Tool("net.port.check", "Prüft, ob ein bestimmter Port erreichbar ist.",
             params("host", "port", host=STR, port=integer("1–65535"),
                    timeout=text("Sekunden, Vorgabe 3")),
             port_check, level=P.READ, tags=("netzwerk", "port", "diagnose"),
             returns="offen ja/nein mit Grund",
             phrases=("läuft der server auf port", "ist der port offen",
                      "läuft mein minecraft server")),
        Tool("net.traceroute", "Zeigt den Weg der Pakete zu einem Host.",
             params("host", host=STR, max_hops=INT), trace_route, level=P.READ,
             tags=("netzwerk", "diagnose")),
        Tool("net.latency.monitor",
             "Misst die Antwortzeit mehrfach und zeigt die Schwankung.",
             params("host", host=STR, samples=INT, delay=text("Pause in Sekunden")),
             latency_monitor, level=P.READ, tags=("netzwerk", "diagnose"),
             phrases=("ist meine verbindung stabil", "warum laggt das internet")),

        # Eigener Rechner
        Tool("net.local.ip", "Die lokale IP-Adresse dieses Rechners.",
             NO_PARAMS, local_ip, level=P.READ, tags=("netzwerk",),
             phrases=("welche ip habe ich", "meine ip")),
        Tool("net.public.ip", "Die öffentliche IP-Adresse (fragt einen Dienst).",
             params(timeout=INT), public_ip, level=P.READ, requires=("httpx",),
             tags=("netzwerk",), phrases=("öffentliche ip", "wie sieht mich das internet")),
        Tool("net.hostname", "Rechnername und vollständiger Domainname.",
             NO_PARAMS, hostname, level=P.SAFE, tags=("netzwerk",)),
        Tool("net.interfaces", "Alle Netzwerkadapter mit Adresse und Zustand.",
             NO_PARAMS, interfaces, level=P.READ, requires=("psutil",),
             tags=("netzwerk", "hardware"),
             phrases=("netzwerkadapter", "welche netzwerkkarten")),
        Tool("net.local.ports", "Welche Ports dieser Rechner geöffnet hat.",
             params(limit=INT), local_ports, level=P.READ, requires=("psutil",),
             tags=("netzwerk", "port"),
             phrases=("welche ports sind offen", "was lauscht auf port")),
        Tool("net.connections", "Bestehende Netzwerkverbindungen.",
             params(limit=INT, state=text("z. B. ESTABLISHED")),
             connections, level=P.READ, requires=("psutil",), tags=("netzwerk",),
             phrases=("wer ist verbunden", "offene verbindungen")),
        Tool("net.traffic", "Gesendete und empfangene Bytes seit dem Systemstart.",
             NO_PARAMS, traffic, level=P.READ, requires=("psutil",), tags=("netzwerk",)),
        Tool("net.traffic.rate", "Misst die aktuelle Übertragungsrate.",
             params(seconds=text("Messdauer, Vorgabe 2")), traffic_rate,
             level=P.READ, requires=("psutil",), tags=("netzwerk",),
             phrases=("wie viel lädt gerade", "netzwerklast")),
        Tool("net.arp.table", "Die Nachbarn im lokalen Netz (ARP).",
             params(limit=INT), arp_table, level=P.READ, tags=("netzwerk",)),
        Tool("net.gateway", "Das Standard-Gateway dieses Rechners.",
             NO_PARAMS, gateway, level=P.READ, tags=("netzwerk",),
             phrases=("welches gateway", "router adresse")),
        Tool("net.wifi.networks", "Sichtbare WLAN-Netze mit Signalstärke.",
             NO_PARAMS, wifi_networks, level=P.READ, tags=("netzwerk", "wlan"),
             phrases=("welche wlans", "wlan netze")),

        # HTTP
        Tool("net.http.status", "Prüft, ob eine Adresse antwortet, und wie schnell.",
             params("url", url=text("Die Adresse"), timeout=INT),
             http_status, level=P.READ, requires=("httpx",), tags=("http", "diagnose"),
             phrases=("ist die seite online", "antwortet die webseite")),
        Tool("net.http.headers", "Die HTTP-Kopfzeilen einer Adresse.",
             params("url", url=STR, timeout=INT), http_headers, level=P.READ,
             requires=("httpx",), tags=("http",)),
        Tool("net.http.get", "Holt den Inhalt einer Adresse als Text.",
             params("url", url=STR, timeout=INT, max_chars=INT),
             http_get, level=P.READ, requires=("httpx",), tags=("http",),
             phrases=("hol die seite", "was steht auf der url")),
        Tool("net.http.download", "Lädt eine Datei in den Arbeitsbereich.",
             params("url", "path", url=STR, path=text("Zielpfad im Arbeitsbereich"),
                    timeout=INT),
             http_download, level=P.WRITE, requires=("httpx",),
             tags=("http", "datei"), undoable=True,
             phrases=("lad die datei runter", "download")),
        Tool("net.url.parse", "Zerlegt eine URL in ihre Bestandteile.",
             params("url", url=STR), url_parse, level=P.SAFE, tags=("http", "url")),
        Tool("net.ssl.certificate",
             "Zeigt das TLS-Zertifikat eines Hosts samt Restlaufzeit.",
             params("host", host=STR, port=INT, timeout=INT),
             ssl_certificate, level=P.READ, tags=("https", "zertifikat"),
             returns="Aussteller, Gültigkeit und verbleibende Tage",
             phrases=("läuft mein zertifikat ab", "ssl zertifikat prüfen")),
    ]
