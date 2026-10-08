#!/usr/bin/env python3
"""Boot guard for Windows autologin.

With autologin on, the PC always signs itself in. This runs at logon and
LOCKS the PC again unless the phone woke it through the wake relay (wake.py)
shortly before. So: woken from the phone -> straight to the desktop;
power button -> password needed. Any error / unreachable relay -> lock.

  pythonw boot_guard.py --url http://PI-IP:8766 --token TOKEN
"""
import argparse
import json
import sys
import urllib.request

MAX_UPTIME_S = 600  # only guard fresh boots, never later manual logins


def was_woken(url, token, opener=urllib.request.urlopen):
    req = urllib.request.Request(url.rstrip("/") + "/woken", data=b"", headers={"X-Token": token})
    try:
        with opener(req, timeout=5) as r:
            return bool(json.load(r).get("woken"))
    except Exception:
        return False  # fail safe: lock


def guard(url, token, uptime_s, lock, opener=urllib.request.urlopen):
    """Returns True if the PC was left unlocked."""
    if uptime_s > MAX_UPTIME_S:
        return True
    if was_woken(url, token, opener):
        return True
    lock()
    return False


def main():
    if sys.platform != "win32":
        sys.exit("Windows only")
    import ctypes
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True)
    ap.add_argument("--token", required=True)
    a = ap.parse_args()
    up = ctypes.windll.kernel32.GetTickCount64() / 1000
    guard(a.url, a.token, up, ctypes.windll.user32.LockWorkStation)


if __name__ == "__main__":
    main()
