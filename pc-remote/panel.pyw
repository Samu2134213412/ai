"""PC Remote - Kontrollfenster. Doppelklick genügt, keine Befehle nötig."""
import os
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import panel_logic as L  # noqa: E402

SERVER_PY = HERE / "server.py"
IS_WIN = sys.platform == "win32"
GREEN, RED, GREY = "#1a9c3c", "#d62828", "#888"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PC Remote")
        self.geometry("560x720")
        self.minsize(520, 640)
        self.cfg = L.load_config()
        st = ttk.Style(self)
        st.configure("TButton", padding=6)
        st.configure("Big.TButton", padding=10, font=("Segoe UI", 11, "bold"))
        pad = {"padx": 12, "pady": 6}

        # ---- status + start/stop
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        self.dot = tk.Canvas(top, width=22, height=22, highlightthickness=0)
        self.dot.pack(side="left")
        self.status = ttk.Label(top, text="…", font=("Segoe UI", 14, "bold"))
        self.status.pack(side="left", padx=8)
        self.btn_start = ttk.Button(top, text="Starten", style="Big.TButton", command=self.start)
        self.btn_start.pack(side="right")
        self.btn_stop = ttk.Button(top, text="Stoppen", style="Big.TButton", command=self.stop)
        self.btn_stop.pack(side="right", padx=6)

        # ---- links
        box = ttk.LabelFrame(self, text="Verbindung vom Handy")
        box.pack(fill="x", **pad)
        self.link_vars, self.link_rows = {}, {}
        for key, title in (("public", "Fester Link (von überall)"), ("wlan", "Im WLAN")):
            ttk.Label(box, text=title).pack(anchor="w", padx=8, pady=(6, 0))
            row = ttk.Frame(box)
            row.pack(fill="x", padx=8, pady=(0, 4))
            var = tk.StringVar()
            self.link_vars[key] = var
            ttk.Entry(row, textvariable=var, state="readonly").pack(side="left", fill="x", expand=True)
            ttk.Button(row, text="Kopieren", command=lambda k=key: self.copy(k)).pack(side="left", padx=4)
            ttk.Button(row, text="QR-Code", command=lambda k=key: self.qr(k)).pack(side="left")
        self.btn_fixed = ttk.Button(box, text="Festen Link einrichten (Tailscale) …", command=self.setup_fixed)
        self.btn_fixed.pack(anchor="w", padx=8, pady=(2, 8))

        # ---- settings
        sett = ttk.LabelFrame(self, text="Einstellungen")
        sett.pack(fill="x", **pad)
        self.v_auto = tk.BooleanVar(value=L.autostart_enabled())
        self.v_overlay = tk.BooleanVar(value=self.cfg["overlay"])
        self.v_exec = tk.BooleanVar(value=self.cfg["allow_exec"])
        ttk.Checkbutton(sett, text="Beim Windows-Start automatisch (unsichtbar) starten", variable=self.v_auto,
                        command=self.toggle_auto).pack(anchor="w", padx=8, pady=3)
        ttk.Checkbutton(sett, text="Blau leuchtenden Kreis am PC zeigen, wenn das Handy steuert",
                        variable=self.v_overlay, command=self.save_settings).pack(anchor="w", padx=8, pady=3)
        ttk.Checkbutton(sett, text="Befehls-Tab erlauben (Vorsicht: volle Kontrolle über den PC)",
                        variable=self.v_exec, command=self.save_settings).pack(anchor="w", padx=8, pady=3)
        ttk.Label(sett, text="Änderungen gelten nach „Neu starten“.", foreground=GREY).pack(anchor="w", padx=8)
        ttk.Button(sett, text="Neu starten", command=self.restart).pack(anchor="w", padx=8, pady=(4, 8))

        # ---- tools
        tools = ttk.LabelFrame(self, text="Werkzeuge")
        tools.pack(fill="x", **pad)
        row = ttk.Frame(tools)
        row.pack(fill="x", padx=8, pady=6)
        ttk.Button(row, text="Neuen Zugangscode", command=self.renew_token).pack(side="left")
        ttk.Button(row, text="Protokoll öffnen", command=lambda: self.open_file(L.LOG_FILE)).pack(side="left", padx=6)
        ttk.Button(row, text="Desktop-Verknüpfung", command=self.shortcut).pack(side="left")
        self.btn_deps = ttk.Button(tools, text="Fehlende Programmteile installieren", command=self.install_deps)
        self.btn_deps.pack(anchor="w", padx=8, pady=(0, 8))

        # ---- log
        self.out = tk.Text(self, height=8, state="disabled", bg="#f4f4f4", font=("Consolas", 9))
        self.out.pack(fill="both", expand=True, **pad)

        self.protocol("WM_DELETE_WINDOW", self.destroy)  # closing the panel never stops the server
        self.tick()

    # ---------- helpers
    def log(self, text):
        self.out.configure(state="normal")
        self.out.insert("end", text.rstrip("\n") + "\n")
        self.out.see("end")
        self.out.configure(state="disabled")

    def run_bg(self, cmd, done=None):
        def work():
            try:
                kw = {"creationflags": L.CREATE_NO_WINDOW} if IS_WIN else {}
                p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                     stdin=subprocess.DEVNULL, **kw)
                for line in p.stdout:
                    self.after(0, self.log, line)
                p.wait()
                self.after(0, self.log, "— fertig —" if p.returncode == 0 else f"— Fehler (Code {p.returncode}) —")
            except OSError as e:
                self.after(0, self.log, f"Fehler: {e}")
            if done:
                self.after(0, done)
        threading.Thread(target=work, daemon=True).start()

    def open_file(self, path):
        try:
            os.startfile(path) if IS_WIN else subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            self.log(f"Konnte nicht öffnen: {e}")

    # ---------- actions
    def start(self):
        if L.missing_modules():
            messagebox.showinfo("PC Remote", "Es fehlen Programmteile. Bitte unten auf „Fehlende Programmteile installieren“ klicken.")
            return
        L.start_server(L.pythonw_path(), SERVER_PY)
        self.log("Server wird gestartet …")

    def stop(self):
        self.log("Server gestoppt." if L.stop_server(self.cfg["port"]) else "Server lief nicht.")

    def restart(self):
        self.stop()
        self.after(1200, self.start)

    def toggle_auto(self):
        try:
            L.set_autostart(self.v_auto.get(), L.pythonw_path(), SERVER_PY)
            self.log("Autostart " + ("eingeschaltet." if self.v_auto.get() else "ausgeschaltet."))
        except OSError as e:
            self.v_auto.set(not self.v_auto.get())
            messagebox.showerror("PC Remote", f"Autostart konnte nicht geändert werden:\n{e}")

    def save_settings(self):
        if self.v_exec.get() and not messagebox.askyesno(
                "Vorsicht", "Damit kann jeder mit deinem Link Befehle auf dem PC ausführen.\nWirklich erlauben?"):
            self.v_exec.set(False)
        self.cfg.update(overlay=self.v_overlay.get(), allow_exec=self.v_exec.get())
        L.save_config(self.cfg)

    def renew_token(self):
        if messagebox.askyesno("Neuer Zugangscode", "Alle bisherigen Links werden ungültig.\nDie Handys müssen den neuen Link einmal öffnen.\nFortfahren?"):
            self.stop()
            L.new_token()
            self.after(1200, self.start)
            self.log("Neuer Zugangscode wird erzeugt …")

    def install_deps(self):
        req = HERE / "requirements.txt"
        self.log("Installiere Programmteile … (kann 1–2 Minuten dauern)")
        self.run_bg([L.pythonw_path(), "-m", "pip", "install", "-r", str(req)])

    def setup_fixed(self):
        bat = HERE / "install-fixed-link.bat"
        if IS_WIN and bat.exists():
            os.startfile(bat)
        else:
            messagebox.showinfo("PC Remote", "Nur unter Windows verfügbar.")

    def shortcut(self):
        if not IS_WIN:
            return
        desk = Path(os.path.expanduser("~")) / "Desktop" / "PC Remote.lnk"
        ps = ("$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%s');$s.TargetPath='%s';"
              "$s.Arguments='\"%s\"';$s.WorkingDirectory='%s';$s.Save()") % (
            desk, L.pythonw_path(), HERE / "panel.pyw", HERE)
        self.run_bg(["powershell", "-NoProfile", "-Command", ps], done=lambda: self.log(f"Verknüpfung: {desk}"))

    def copy(self, key):
        val = self.link_vars[key].get()
        if val:
            self.clipboard_clear()
            self.clipboard_append(val)
            self.log("Link kopiert.")

    def qr(self, key):
        val = self.link_vars[key].get()
        if not val:
            return
        try:
            import qrcode
            from PIL import ImageTk
            img = qrcode.make(val).resize((360, 360))
        except Exception:
            messagebox.showinfo("PC Remote", "QR-Code nicht verfügbar (qrcode/Pillow fehlt). Link kopieren und selbst senden.")
            return
        win = tk.Toplevel(self)
        win.title("QR-Code - mit dem Handy scannen")
        photo = ImageTk.PhotoImage(img)
        lab = tk.Label(win, image=photo)
        lab.image = photo
        lab.pack(padx=12, pady=12)

    # ---------- periodic refresh
    def tick(self):
        running = L.server_running(self.cfg["port"])
        self.dot.delete("all")
        self.dot.create_oval(3, 3, 19, 19, fill=GREEN if running else RED, outline="")
        self.status.configure(text="Server läuft" if running else "Server gestoppt")
        self.btn_start.state(["disabled"] if running else ["!disabled"])
        self.btn_stop.state(["!disabled"] if running else ["disabled"])
        links = L.read_links()
        for key in ("public", "wlan"):
            self.link_vars[key].set(links.get(key, ""))
        self.btn_fixed.state(["disabled"] if links.get("public") else ["!disabled"])
        miss = L.missing_modules()
        self.btn_deps.state(["!disabled"] if miss else ["disabled"])
        self.btn_deps.configure(text="Fehlende Programmteile installieren (" + ", ".join(miss) + ")" if miss
                                else "Alle Programmteile vorhanden ✓")
        self.after(2000, self.tick)


if __name__ == "__main__":
    App().mainloop()
