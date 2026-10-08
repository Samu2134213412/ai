"""Glowing blue pointer on the PC itself, shown only while the phone is controlling.

Click-through, always on top, no taskbar entry; hidden from screen capture on
Windows so it does not show up twice in the phone's view. Needs tkinter
(bundled with python.org Python on Windows).
"""
import math
import sys
import threading
import time

SIZE = 120
KEY = "#010101"  # transparent colour key
HOLD_S = 2.5      # stay visible this long after the last phone action
POLL_MS = 15


def visible(now, last_action, hold=HOLD_S):
    """True while the phone controlled the PC within the last `hold` seconds."""
    return last_action > 0 and 0 <= now - last_action <= hold


def ring_colors(phase):
    """Concentric glow rings (outer -> inner) as hex colours; phase 0..1 pulses the brightness."""
    k = 0.75 + 0.25 * math.sin(phase * 2 * math.pi)
    stops = [(10, 30, 110), (20, 60, 170), (40, 100, 235), (90, 150, 255), (170, 205, 255)]
    return ["#%02x%02x%02x" % tuple(min(255, int(c * k)) for c in s) for s in stops]


class Overlay:
    def __init__(self, last_action, pointer):
        """last_action(): timestamp of the last phone action; pointer(): (x, y) in screen pixels or None."""
        self.last_action, self.pointer = last_action, pointer
        self._t = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._t.start()
        return self

    def _run(self):
        try:
            import tkinter as tk
        except ImportError:
            print("(tkinter fehlt - blauer Cursor am PC deaktiviert)")
            return
        root = tk.Tk()
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        root.configure(bg=KEY)
        if sys.platform == "win32":
            root.attributes("-transparentcolor", KEY)
            root.attributes("-alpha", 0.85)
        cv = tk.Canvas(root, width=SIZE, height=SIZE, bg=KEY, highlightthickness=0)
        cv.pack()
        c = SIZE // 2
        radii = [58, 44, 32, 20, 9]
        ids = [cv.create_oval(c - r, c - r, c + r, c + r, fill=KEY, outline="") for r in radii]
        root.withdraw()
        shown = [False]
        click_through(root)

        def tick():
            now = time.time()
            p = self.pointer()
            if p and visible(now, self.last_action()):
                for i, col in zip(ids, ring_colors((now * 0.8) % 1.0)):
                    cv.itemconfigure(i, fill=col)
                root.geometry(f"{SIZE}x{SIZE}+{int(p[0]) - c}+{int(p[1]) - c}")
                if not shown[0]:
                    root.deiconify()
                    click_through(root)
                    shown[0] = True
            elif shown[0]:
                root.withdraw()
                shown[0] = False
            root.after(POLL_MS, tick)

        tick()
        root.mainloop()


def click_through(root):
    """Windows: mouse clicks pass through, no focus, no taskbar button, excluded from screenshots."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        root.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
        GWL_EXSTYLE, LAYERED, TRANSPARENT, TOOLWINDOW, NOACTIVATE = -20, 0x80000, 0x20, 0x80, 0x08000000
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | LAYERED | TRANSPARENT | TOOLWINDOW | NOACTIVATE)
        user32.SetWindowDisplayAffinity(hwnd, 0x11)  # WDA_EXCLUDEFROMCAPTURE (Win10 2004+), ignored if unsupported
    except Exception:
        pass
