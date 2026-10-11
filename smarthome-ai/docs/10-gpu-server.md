# 10 – GPU-Server mit 2× Tesla P40 (optional, M12)

Ziel: ein zweites, größeres Gehirn (48 GB VRAM), das wie der PC **nur bei Bedarf**
läuft und den Gaming-PC frei lässt.

## Was es bringt

| | Gaming-PC (RX 7900 XTX) | GPU-Server (2× P40) |
|---|---|---|
| VRAM | 24 GB | 48 GB |
| Modellgröße (4-Bit) | bis ≈ 30–32 Mrd. Parameter | bis ≈ 70 Mrd. Parameter (kleiner Kontext) |
| Geschwindigkeit pro Token | schneller | langsamer (Architektur von 2016) |
| Blockiert Gaming | ja | nein |
| Strom Last / Leerlauf | ≈ 400 W / ≈ 90 W | ≈ 500–600 W / ≈ 60–100 W |

## Wichtig zu wissen, bevor du kaufst

1. **Software-Ende:** Die P40 (Pascal) wird von CUDA 13 nicht mehr unterstützt; die NVIDIA-Treiberreihe 580 ist die letzte für Pascal. Ollama/llama.cpp laufen weiter mit CUDA-12-Builds → Versionen bewusst festhalten.
2. **Passive Kühlung:** Die Karten haben keinen Lüfter. Sie brauchen einen Luftstrom → 🖨 Lüfterhutze + Radiallüfter pro Karte (druckst du auf dem X2D, PETG/ASA wegen Wärme).
3. **Stromstecker:** Die P40 hat einen 8-Pin-**EPS**-Anschluss (CPU-Stecker), nicht PCIe → passender Adapter nötig, sonst Schaden.
4. **Kein Bildausgang:** CPU mit integrierter Grafik nehmen (z. B. Ryzen 5 5600G), BIOS-Option „Above 4G Decoding“ an.
5. **Leerlauf-Falle:** Mit geladenem Modell bleibt die P40 oft in einem hohen Energiezustand (≈ 50 W pro Karte). Abhilfe: Tool, das die Karte in den Sparzustand zwingt, und Modelle schnell entladen.
6. **Schlaf:** Suspend-to-RAM mit Rechenzentrums-Karten klappt nicht immer. Plan B: Herunterfahren statt Schlafen, Wake-on-LAN bootet in ≈ 60–90 s.
7. **Alternative:** Eine gebrauchte RTX 3090 (24 GB) ist deutlich schneller, aktuell unterstützt und aktiv gekühlt – aber nur halb so viel VRAM. Wenn 70-Mrd.-Modelle nicht das Ziel sind, ist sie die bessere Wahl.

## Teileliste (gebraucht, stark schwankende Preise – vor dem Kauf prüfen)

| Teil | Preis |
|---|---|
| 2× Tesla P40 24 GB | 400–700 € |
| Mainboard AM4 mit 2× PCIe x16 mechanisch (x8/x8) | 80–150 € |
| Ryzen 5 5600G | 60–90 € |
| 32–64 GB DDR4 | 50–100 € |
| Netzteil 1000 W 80+ Gold, 2× EPS-Adapter | 100–150 € |
| Gehäuse mit starkem Frontluftstrom | 60–100 € |
| NVMe 1 TB | 50–70 € |
| 2× Radiallüfter + 🖨 Hutzen | 20–40 € |
| **Summe** | **≈ 820–1.400 €** |

## Software

Linux (Debian/Ubuntu Server), NVIDIA 580-Treiber, Ollama oder llama.cpp mit
CUDA 12, Whisper (Wyoming), `pc-agent` im Linux-Modus (hält wach per
`systemd-inhibit`, schläft/fährt herunter nach X min ohne Lease). Im
`brain_router` wird der Server als Backend mit höherer Priorität eingetragen –
sonst ändert sich nichts.
