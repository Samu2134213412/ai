"""Shows the saved links of the running PC Remote and copies the public one to the clipboard."""
import sys
from pathlib import Path

import server

f = Path.home() / ".pc-remote-links.txt"
if not f.exists():
    sys.exit("Noch keine Links. Läuft PC Remote? (Nach dem Anmelden ca. 1 Minute warten.)")
text = f.read_text(encoding="utf-8")
print("\n" + text)
public = [l.split(": ", 1)[1].strip() for l in text.splitlines() if l.startswith("OEFFENTLICH")]
if public and server.copy_link(public[0]):
    print(">>> Der oeffentliche Link wurde KOPIERT (in WhatsApp/Notizen einfuegen).")
elif not public:
    print("Noch kein oeffentlicher Link: install-fixed-link.bat ausfuehren (einmalig).")
