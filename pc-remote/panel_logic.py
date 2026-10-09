"""Logic behind the control panel (panel.pyw): config, server start/stop, autostart, links.
No GUI imports here so it can be tested without a display."""
import importlib.util
import json
import os
import signal
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

HOME = Path.home()
CONFIG_FILE = HOME / ".pc-remote-config.json"
PID_FILE = HOME / ".pc-remote.pid"
LINKS_FILE = HOME / ".pc-remote-links.txt"
TOKEN_FILE = HOME / ".pc-remote-token"
LOG_FILE = HOME / ".pc-remote.log"
DEFAULTS = {"port": 8765, "overlay": True, "allow_exec": False}
REQUIRED_MODULES = ["pynput", "mss", "PIL"]
CREATE_NO_WINDOW, DETACHED_PROCESS = 0x08000000, 0x00000008


def load_config(path=CONFIG_FILE):
    cfg = dict(DEFAULTS)
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        for k, v in DEFAULTS.items():
            if isinstance(data.get(k), type(v)):
                cfg[k] = data[k]
    except (OSError, ValueError):
        pass
    return cfg


def save_config(cfg, path=CONFIG_FILE):
    Path(path).write_text(json.dumps({k: cfg[k] for k in DEFAULTS}, indent=2), encoding="utf-8")


def server_running(port, opener=urllib.request.urlopen):
    try:
        with opener(f"http://127.0.0.1:{int(port)}/", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def pythonw_path():
    exe = Path(sys.executable)
    w = exe.with_name("pythonw.exe")
    return str(w) if sys.platform == "win32" and w.exists() else str(exe)


def start_server(python_exe, server_py, popen=subprocess.Popen):
    kw = {}
    if sys.platform == "win32":
        kw["creationflags"] = CREATE_NO_WINDOW | DETACHED_PROCESS
    return popen([python_exe, str(server_py)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL, **kw)


def read_pid(path=PID_FILE):
    try:
        return int(Path(path).read_text().strip())
    except (OSError, ValueError):
        return None


def default_killer(pid):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True,
                       creationflags=CREATE_NO_WINDOW)
    else:
        os.kill(pid, signal.SIGTERM)


def stop_server(port, pid_path=PID_FILE, killer=default_killer, running=server_running):
    """Stops the server recorded in the pid file. Returns True if a process was killed."""
    pid = read_pid(pid_path)
    killed = False
    if pid and running(port):  # only kill if something really answers: guards against a reused pid
        try:
            killer(pid)
            killed = True
        except OSError:
            pass
    Path(pid_path).unlink(missing_ok=True)
    return killed


def startup_dir():
    base = os.environ.get("APPDATA") or str(HOME)
    return Path(base) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _vbs(pythonw, server_py):
    return f'CreateObject("WScript.Shell").Run """{pythonw}"" ""{server_py}""", 0, False\r\n'


def autostart_enabled(folder=None):
    return ((folder or startup_dir()) / "PCRemote.vbs").exists()


def set_autostart(enabled, pythonw, server_py, folder=None):
    f = (folder or startup_dir()) / "PCRemote.vbs"
    if enabled:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(_vbs(pythonw, server_py), encoding="utf-8")
    else:
        f.unlink(missing_ok=True)


def read_links(path=LINKS_FILE):
    out = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            key, _, val = line.partition(":")
            val = val.strip()
            if key.startswith("WLAN"):
                out["wlan"] = val
            elif key.startswith("OEFFENTLICH"):
                out["public"] = val
    except OSError:
        pass
    return out


def missing_modules(modules=REQUIRED_MODULES):
    return [m for m in modules if importlib.util.find_spec(m) is None]


def new_token():
    """Delete the saved access code; the server creates a fresh one on next start."""
    TOKEN_FILE.unlink(missing_ok=True)


def autologin_enabled():
    """True if Windows signs in automatically at boot (needed so the server starts after a power-on)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon") as k:
            return str(winreg.QueryValueEx(k, "AutoAdminLogon")[0]) == "1"
    except OSError:
        return False


def parse_getmac(text):
    """`getmac /fo csv /nh` -> MAC addresses of adapters that are connected."""
    macs = []
    for line in text.splitlines():
        parts = [p.strip().strip('"') for p in line.split('",')]
        if len(parts) >= 2 and "Tcpip_" in parts[1] and parts[0].count("-") == 5:
            macs.append(parts[0].upper())
    return macs


def local_macs(run=subprocess.run):
    if sys.platform == "win32":
        try:
            out = run(["getmac", "/fo", "csv", "/nh"], capture_output=True, text=True, timeout=10,
                      creationflags=CREATE_NO_WINDOW).stdout
            return parse_getmac(out)
        except Exception:
            return []
    import uuid
    n = uuid.getnode()
    return ["-".join(f"{(n >> s) & 0xff:02X}" for s in range(40, -8, -8))]


def acquire_single_instance(port=48765):
    """Only one control panel at a time: returns the bound socket (keep a reference) or None if taken."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        return sock
    except OSError:
        sock.close()
        return None
