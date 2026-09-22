"""Tool Pack: Medien -- Bild, Audio, Video.

``image.*`` läuft über Pillow (reiner Python-Code, keine Unterprozesse).
``audio.*``/``video.*`` läuft über ``ffmpeg``/``ffprobe`` -- externe
Programme, aber mit **fester** Filtergraph-Syntax je Werkzeug; nur Zahlen
und bereits auf den Arbeitsbereich geprüfte Pfade kommen vom Aufrufer rein.
Insbesondere gibt es hier keinen Text, der roh in einen ffmpeg-Filter
eingesetzt wird (``drawtext`` samt Escaping-Fallstricken) -- Textwasserzeichen
laufen stattdessen über Pillow, wo der Text ein normaler Python-String ist.

Jedes Werkzeug, das eine neue Datei erzeugt, verlangt einen eigenen
Zielpfad (nicht in-place) und verweigert ein bereits bestehendes Ziel ohne
``overwrite=true`` -- dieselbe Regel wie ``files.copy`` in ``fs.py``.
"""

from __future__ import annotations

import json as jsonlib
from pathlib import Path
from typing import Any

from ...permissions import PermissionLevel as P
from ..base import Tool, ToolError, ToolResult
from ..catalog import ToolContext, run_process
from ._base import flag, integer, number, ok, params, table, text

try:  # pragma: no cover
    from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageStat
    from PIL import ExifTags
except ImportError:  # pragma: no cover
    Image = None

MAX_OUTPUT = 20_000
FFMPEG_TIMEOUT = 300.0


def _clip(value: str) -> str:
    value = value or ""
    if len(value) <= MAX_OUTPUT:
        return value
    return value[:MAX_OUTPUT] + f"\n… gekürzt ({len(value) - MAX_OUTPUT} weitere Zeichen)"


def _pil():
    if Image is None:
        raise ToolError("Dafür fehlt das Paket 'Pillow': pip install Pillow")
    return Image


def build(ctx: ToolContext) -> list[Tool]:
    ws = ctx.workspace

    def quelle(raw: str) -> Path:
        pfad = ws.resolve(raw)
        if not pfad.is_file():
            raise ToolError(f"Datei existiert nicht: {pfad}")
        return pfad

    def ziel(raw: str, overwrite: bool) -> Path:
        pfad = ws.resolve(raw)
        if pfad.exists() and not overwrite:
            raise ToolError(f"Ziel existiert schon: {pfad}. Mit overwrite=true überschreiben.")
        pfad.parent.mkdir(parents=True, exist_ok=True)
        return pfad

    # ══════════════════════════════════════════════════════════ image.*
    def bild_oeffnen(raw: str):
        _pil()
        try:
            return Image.open(quelle(raw))
        except Exception as exc:  # noqa: BLE001 - Pillow wirft viele eigene Typen
            raise ToolError(f"Kein lesbares Bild: {raw} ({exc})") from exc

    def image_info(path: str) -> ToolResult:
        img = bild_oeffnen(path)
        datei = quelle(path)
        return ok("image.info",
                  f"{img.format or '?'} {img.width}×{img.height}, {img.mode}, "
                  f"{datei.stat().st_size} Bytes",
                  breite=img.width, hoehe=img.height, format=img.format,
                  modus=img.mode, bytes=datei.stat().st_size)

    def image_resize(path: str, output: str, width: int = 0, height: int = 0,
                     overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        if not width and not height:
            raise ToolError("Es wurde weder width noch height angegeben.")
        if width and not height:
            height = round(img.height * (width / img.width))
        elif height and not width:
            width = round(img.width * (height / img.height))
        neu = img.resize((max(1, int(width)), max(1, int(height))), Image.LANCZOS)
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.resize", f"{img.width}×{img.height} → {width}×{height}: {out.name}",
                  pfad=str(out), breite=width, hoehe=height)

    def image_thumbnail(path: str, output: str, max_size: int = 256,
                        overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        kopie = img.copy()
        kopie.thumbnail((max(1, int(max_size)), max(1, int(max_size))), Image.LANCZOS)
        out = ziel(output, overwrite)
        kopie.save(out)
        return ok("image.thumbnail", f"Thumbnail {kopie.width}×{kopie.height}: {out.name}",
                  pfad=str(out), breite=kopie.width, hoehe=kopie.height)

    def image_convert(path: str, output: str, overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        out = ziel(output, overwrite)
        speicher = img.convert("RGB") if out.suffix.lower() in (".jpg", ".jpeg") else img
        speicher.save(out)
        return ok("image.convert", f"{img.format or '?'} → {out.suffix.lstrip('.').upper()}: "
                  f"{out.name}", pfad=str(out))

    def image_rotate(path: str, output: str, degrees: float, overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        neu = img.rotate(-float(degrees), expand=True)
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.rotate", f"Um {degrees}° gedreht: {out.name}", pfad=str(out))

    def image_flip(path: str, output: str, richtung: str = "horizontal",
                   overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        art = (richtung or "horizontal").strip().lower()
        if art in ("horizontal", "h", "links-rechts"):
            neu = img.transpose(Image.FLIP_LEFT_RIGHT)
        elif art in ("vertical", "v", "oben-unten"):
            neu = img.transpose(Image.FLIP_TOP_BOTTOM)
        else:
            raise ToolError(f"Unbekannte Richtung: {richtung!r} (horizontal/vertical)")
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.flip", f"Gespiegelt ({art}): {out.name}", pfad=str(out))

    def image_crop(path: str, output: str, left: int, top: int, right: int, bottom: int,
                   overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        box = (int(left), int(top), int(right), int(bottom))
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ToolError(f"Ungültiger Ausschnitt: {box}")
        neu = img.crop(box)
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.crop", f"Zugeschnitten auf {neu.width}×{neu.height}: {out.name}",
                  pfad=str(out), breite=neu.width, hoehe=neu.height)

    def image_grayscale(path: str, output: str, overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        neu = img.convert("L")
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.grayscale", f"In Graustufen: {out.name}", pfad=str(out))

    def image_compress(path: str, output: str, quality: int = 75,
                       overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        vorher = quelle(path).stat().st_size
        out = ziel(output, overwrite)
        q = max(1, min(int(quality or 75), 95))
        speicher = img.convert("RGB") if out.suffix.lower() in (".jpg", ".jpeg") else img
        if out.suffix.lower() in (".jpg", ".jpeg"):
            speicher.save(out, quality=q, optimize=True)
        else:
            speicher.save(out, optimize=True)
        nachher = out.stat().st_size
        ersparnis = 100 - round(nachher / vorher * 100) if vorher else 0
        return ok("image.compress", f"{vorher} → {nachher} Bytes ({ersparnis}% kleiner): {out.name}",
                  pfad=str(out), vorher_bytes=vorher, nachher_bytes=nachher, ersparnis_prozent=ersparnis)

    def image_watermark_text(path: str, output: str, text: str,
                             position: str = "unten-rechts", size: int = 24,
                             color: str = "white", overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path).convert("RGBA")
        inhalt = (text or "").strip()
        if not inhalt:
            raise ToolError("Es wurde kein Text angegeben.")
        ebene = Image.new("RGBA", img.size, (0, 0, 0, 0))
        zeichner = ImageDraw.Draw(ebene)
        try:
            schrift = ImageFont.load_default(size=max(8, int(size or 24)))
        except TypeError:  # ältere Pillow-Versionen kennen 'size' nicht
            schrift = ImageFont.load_default()
        box = zeichner.textbbox((0, 0), inhalt, font=schrift)
        textbreite, texthoehe = box[2] - box[0], box[3] - box[1]
        rand = 10
        positionen = {
            "unten-rechts": (img.width - textbreite - rand, img.height - texthoehe - rand),
            "unten-links": (rand, img.height - texthoehe - rand),
            "oben-rechts": (img.width - textbreite - rand, rand),
            "oben-links": (rand, rand),
            "mitte": ((img.width - textbreite) // 2, (img.height - texthoehe) // 2),
        }
        xy = positionen.get((position or "unten-rechts").strip().lower(),
                            positionen["unten-rechts"])
        zeichner.text(xy, inhalt, font=schrift, fill=color)
        ergebnis = Image.alpha_composite(img, ebene)
        out = ziel(output, overwrite)
        (ergebnis.convert("RGB") if out.suffix.lower() in (".jpg", ".jpeg")
         else ergebnis).save(out)
        return ok("image.watermark.text", f"Wasserzeichen '{inhalt}' hinzugefügt: {out.name}",
                  pfad=str(out))

    def image_exif_read(path: str) -> ToolResult:
        img = bild_oeffnen(path)
        roh = img.getexif()
        if not roh:
            return ok("image.exif.read", "Keine EXIF-Daten vorhanden", payload="(keine)")
        eintraege = {}
        for tag_id, wert in roh.items():
            name = ExifTags.TAGS.get(tag_id, str(tag_id))
            eintraege[name] = str(wert)[:200]
        zeilen = "\n".join(f"{k}: {v}" for k, v in sorted(eintraege.items()))
        return ok("image.exif.read", f"{len(eintraege)} EXIF-Eintragung(en)",
                  payload=zeilen, anzahl=len(eintraege))

    def image_exif_strip(path: str, output: str, overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        # Ein frisches Image-Objekt, auf das nur die Pixel kopiert werden --
        # 'paste' fasst 'info'/EXIF gar nicht erst an, im Unterschied zu
        # 'save', das EXIF unter Umständen aus img.info mit rausschreibt.
        sauber = Image.new(img.mode, img.size)
        sauber.paste(img, (0, 0))
        out = ziel(output, overwrite)
        sauber.save(out)
        return ok("image.exif.strip", f"Metadaten entfernt: {out.name}", pfad=str(out))

    def image_dominant_color(path: str) -> ToolResult:
        img = bild_oeffnen(path).convert("RGB")
        klein = img.copy()
        klein.thumbnail((100, 100))
        quantisiert = klein.quantize(colors=8, method=Image.MEDIANCUT)
        palette = quantisiert.getpalette()
        haeufigkeit = sorted(quantisiert.getcolors(), reverse=True)
        index = haeufigkeit[0][1]
        rgb = tuple(palette[index * 3: index * 3 + 3])
        hexfarbe = "#{:02x}{:02x}{:02x}".format(*rgb)
        return ok("image.dominant_color", f"Dominante Farbe: {hexfarbe}",
                  payload=hexfarbe, rgb=list(rgb), hex=hexfarbe)

    def image_compare(path_a: str, path_b: str) -> ToolResult:
        a, b = bild_oeffnen(path_a).convert("RGB"), bild_oeffnen(path_b).convert("RGB")
        if a.size != b.size:
            return ok("image.compare",
                      f"Unterschiedliche Größe: {a.size[0]}×{a.size[1]} vs "
                      f"{b.size[0]}×{b.size[1]} -- nicht direkt vergleichbar",
                      identisch=False, groesse_gleich=False)
        diff = ImageChops.difference(a, b)
        mittel = ImageStat.Stat(diff).mean
        abweichung = round(sum(mittel) / len(mittel) / 255 * 100, 2)
        return ok("image.compare",
                  "Identisch" if abweichung == 0 else f"{abweichung}% Abweichung",
                  identisch=abweichung == 0, groesse_gleich=True, abweichung_prozent=abweichung)

    def image_merge(paths: list[str], output: str, richtung: str = "horizontal",
                    overwrite: bool = False) -> ToolResult:
        if not paths or len(paths) < 2:
            raise ToolError("Es werden mindestens zwei Bilder benötigt.")
        bilder = [bild_oeffnen(p).convert("RGB") for p in paths]
        art = (richtung or "horizontal").strip().lower()
        if art.startswith("h"):
            breite, hoehe = sum(b.width for b in bilder), max(b.height for b in bilder)
            canvas = Image.new("RGB", (breite, hoehe), "white")
            x = 0
            for b in bilder:
                canvas.paste(b, (x, 0))
                x += b.width
        else:
            breite, hoehe = max(b.width for b in bilder), sum(b.height for b in bilder)
            canvas = Image.new("RGB", (breite, hoehe), "white")
            y = 0
            for b in bilder:
                canvas.paste(b, (0, y))
                y += b.height
        out = ziel(output, overwrite)
        canvas.save(out)
        return ok("image.merge", f"{len(bilder)} Bilder zusammengefügt: {out.name}",
                  pfad=str(out), anzahl=len(bilder))

    def image_border_add(path: str, output: str, width: int = 10, color: str = "black",
                         overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path).convert("RGB")
        w = max(1, int(width or 10))
        neu = Image.new("RGB", (img.width + 2 * w, img.height + 2 * w), color)
        neu.paste(img, (w, w))
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.border.add", f"Rahmen ({w}px, {color}) hinzugefügt: {out.name}",
                  pfad=str(out))

    def image_brightness(path: str, output: str, factor: float = 1.2,
                         overwrite: bool = False) -> ToolResult:
        from PIL import ImageEnhance
        img = bild_oeffnen(path)
        neu = ImageEnhance.Brightness(img).enhance(float(factor))
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.brightness", f"Helligkeit ×{factor}: {out.name}", pfad=str(out))

    def image_contrast(path: str, output: str, factor: float = 1.2,
                       overwrite: bool = False) -> ToolResult:
        from PIL import ImageEnhance
        img = bild_oeffnen(path)
        neu = ImageEnhance.Contrast(img).enhance(float(factor))
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.contrast", f"Kontrast ×{factor}: {out.name}", pfad=str(out))

    def image_blur(path: str, output: str, radius: float = 2.0,
                   overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        neu = img.filter(ImageFilter.GaussianBlur(radius=float(radius)))
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.blur", f"Weichgezeichnet (Radius {radius}): {out.name}", pfad=str(out))

    def image_sharpen(path: str, output: str, overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        neu = img.filter(ImageFilter.SHARPEN)
        out = ziel(output, overwrite)
        neu.save(out)
        return ok("image.sharpen", f"Geschärft: {out.name}", pfad=str(out))

    def image_pixelate(path: str, output: str, block_size: int = 12,
                       box: list[int] | None = None, overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path)
        b = max(2, int(block_size or 12))
        bereich = tuple(int(v) for v in box) if box and len(box) == 4 else (0, 0, img.width, img.height)
        ausschnitt = img.crop(bereich)
        klein = ausschnitt.resize(
            (max(1, ausschnitt.width // b), max(1, ausschnitt.height // b)), Image.NEAREST)
        mosaik = klein.resize(ausschnitt.size, Image.NEAREST)
        ergebnis = img.copy()
        ergebnis.paste(mosaik, bereich)
        out = ziel(output, overwrite)
        ergebnis.save(out)
        return ok("image.pixelate", f"Verpixelt (Blockgröße {b}): {out.name}", pfad=str(out))

    def image_icon_create(path: str, output: str, overwrite: bool = False) -> ToolResult:
        img = bild_oeffnen(path).convert("RGBA")
        out = ziel(output, overwrite)
        groessen = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
        groessen = [g for g in groessen if g[0] <= max(img.width, img.height)] or [(16, 16)]
        img.save(out, format="ICO", sizes=groessen)
        return ok("image.icon.create", f".ico mit {len(groessen)} Größe(n): {out.name}",
                  pfad=str(out), groessen=[f"{w}x{h}" for w, h in groessen])

    def image_ocr(path: str, lang: str = "eng") -> ToolResult:
        datei = quelle(path)
        res = run_process(["tesseract", str(datei), "-", "-l", lang or "eng"], timeout=60)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "tesseract fehlgeschlagen").strip()))
        erkannt = (res.stdout or "").strip()
        return ok("image.ocr", f"{len(erkannt)} Zeichen erkannt" if erkannt else "Kein Text erkannt",
                  payload=_clip(erkannt) or "(nichts erkannt)", zeichen=len(erkannt))

    # ══════════════════════════════════════════════════════════ ffmpeg-Helfer
    def probe_info(datei: Path) -> dict:
        res = run_process(["ffprobe", "-v", "quiet", "-print_format", "json",
                           "-show_format", "-show_streams", str(datei)], timeout=30)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "ffprobe fehlgeschlagen").strip()))
        try:
            return jsonlib.loads(res.stdout or "{}")
        except ValueError as exc:
            raise ToolError(f"ffprobe-Ausgabe nicht lesbar: {exc}") from exc

    def ffmpeg_lauf(args: list[str], tool: str, summary: str, timeout: float = FFMPEG_TIMEOUT,
                    **evidence: Any) -> ToolResult:
        res = run_process(["ffmpeg", "-y", "-nostdin", "-hide_banner", *args], timeout=timeout)
        if res.returncode != 0:
            raise ToolError(_clip((res.stderr or "ffmpeg fehlgeschlagen").strip()))
        return ok(tool, summary, payload=_clip((res.stderr or "").strip()) or None, **evidence)

    # ══════════════════════════════════════════════════════════ audio.*
    def audio_info(path: str) -> ToolResult:
        datei = quelle(path)
        daten = probe_info(datei)
        fmt = daten.get("format", {})
        streams = [s for s in daten.get("streams", []) if s.get("codec_type") == "audio"]
        stream = streams[0] if streams else {}
        dauer = float(fmt.get("duration", 0) or 0)
        return ok("audio.info",
                  f"{dauer:.1f}s · {stream.get('codec_name', '?')} · "
                  f"{stream.get('sample_rate', '?')} Hz · {stream.get('channels', '?')} Kanäle",
                  dauer_sekunden=round(dauer, 2), codec=stream.get("codec_name", ""),
                  sample_rate=stream.get("sample_rate", ""), kanaele=stream.get("channels", ""),
                  bitrate=fmt.get("bit_rate", ""))

    def audio_convert(path: str, output: str, overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        return ffmpeg_lauf(["-i", str(quelle(path)), str(out)], "audio.convert",
                           f"Konvertiert: {out.name}", pfad=str(out))

    def audio_trim(path: str, output: str, start: str, duration: str = "",
                   overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-ss", str(start)]
        if duration:
            args += ["-t", str(duration)]
        args += ["-c", "copy", str(out)]
        return ffmpeg_lauf(args, "audio.trim", f"Ausschnitt ab {start}: {out.name}", pfad=str(out))

    def audio_volume(path: str, output: str, factor: float,
                     overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-filter:a", f"volume={float(factor)}", str(out)]
        return ffmpeg_lauf(args, "audio.volume", f"Lautstärke ×{factor}: {out.name}", pfad=str(out))

    def audio_normalize(path: str, output: str, overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-filter:a", "loudnorm", str(out)]
        return ffmpeg_lauf(args, "audio.normalize", f"Lautheit normalisiert: {out.name}",
                           pfad=str(out))

    def audio_merge(paths: list[str], output: str, overwrite: bool = False) -> ToolResult:
        if not paths or len(paths) < 2:
            raise ToolError("Es werden mindestens zwei Dateien benötigt.")
        dateien = [quelle(p) for p in paths]
        out = ziel(output, overwrite)
        args = []
        for d in dateien:
            args += ["-i", str(d)]
        args += ["-filter_complex", f"concat=n={len(dateien)}:v=0:a=1", str(out)]
        return ffmpeg_lauf(args, "audio.merge", f"{len(dateien)} Dateien zusammengefügt: {out.name}",
                           pfad=str(out), anzahl=len(dateien))

    def audio_extract_from_video(path: str, output: str, overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-vn", str(out)]
        return ffmpeg_lauf(args, "audio.extract_from_video", f"Ton extrahiert: {out.name}",
                           pfad=str(out))

    def audio_speed(path: str, output: str, factor: float,
                    overwrite: bool = False) -> ToolResult:
        f = float(factor)
        if not 0.5 <= f <= 2.0:
            raise ToolError("factor muss zwischen 0.5 und 2.0 liegen (Grenze des atempo-Filters).")
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-filter:a", f"atempo={f}", str(out)]
        return ffmpeg_lauf(args, "audio.speed", f"Geschwindigkeit ×{f}: {out.name}", pfad=str(out))

    def audio_fade(path: str, output: str, fade_in: float = 0, fade_out: float = 0,
                   overwrite: bool = False) -> ToolResult:
        if not fade_in and not fade_out:
            raise ToolError("Es wurde weder fade_in noch fade_out angegeben.")
        out = ziel(output, overwrite)
        teile = []
        if fade_in:
            teile.append(f"afade=t=in:d={float(fade_in)}")
        if fade_out:
            # Die Startzeit eines Fade-outs bräuchte die Gesamtdauer -- also
            # ffprobe, das dieses Werkzeug nicht als Abhängigkeit verspricht
            # (Tool.requires nennt nur ffmpeg). Der bekannte Trick kommt ganz
            # ohne aus: rückwärts abspielen, dort am (jetzt vorne liegenden)
            # Ende einblenden, wieder umdrehen -- Ergebnis: ein Ausblenden
            # exakt am echten Ende, ohne die Dauer je gekannt zu haben.
            teile.append(f"areverse,afade=t=in:d={float(fade_out)},areverse")
        args = ["-i", str(quelle(path)), "-filter:a", ",".join(teile), str(out)]
        return ffmpeg_lauf(args, "audio.fade", f"Fade angewendet: {out.name}", pfad=str(out))

    def audio_silence_detect(path: str, noise_db: float = -30.0,
                             min_duration: float = 0.5) -> ToolResult:
        args = ["-i", str(quelle(path)), "-af",
               f"silencedetect=noise={float(noise_db)}dB:d={float(min_duration)}", "-f", "null", "-"]
        res = run_process(["ffmpeg", "-nostdin", "-hide_banner", *args], timeout=FFMPEG_TIMEOUT)
        zeilen = [z for z in (res.stderr or "").splitlines() if "silence_" in z]
        return ok("audio.silence_detect", f"{len(zeilen)} Fundstelle(n)",
                  payload="\n".join(zeilen) or "(keine Stille erkannt)", anzahl=len(zeilen))

    def audio_volume_detect(path: str) -> ToolResult:
        args = ["-i", str(quelle(path)), "-af", "volumedetect", "-f", "null", "-"]
        res = run_process(["ffmpeg", "-nostdin", "-hide_banner", *args], timeout=FFMPEG_TIMEOUT)
        zeilen = [z.split("]", 1)[-1].strip() for z in (res.stderr or "").splitlines()
                 if "mean_volume" in z or "max_volume" in z]
        return ok("audio.volume_detect", "; ".join(zeilen) or "Keine Angabe",
                  payload="\n".join(zeilen) or "(keine Angabe)")

    def audio_waveform_image(path: str, output: str, width: int = 800, height: int = 200,
                             overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-filter_complex",
               f"showwavespic=s={int(width)}x{int(height)}", "-frames:v", "1", str(out)]
        return ffmpeg_lauf(args, "audio.waveform.image", f"Wellenform gerendert: {out.name}",
                           pfad=str(out))

    # ══════════════════════════════════════════════════════════ video.*
    def video_info(path: str) -> ToolResult:
        datei = quelle(path)
        daten = probe_info(datei)
        fmt = daten.get("format", {})
        streams = [s for s in daten.get("streams", []) if s.get("codec_type") == "video"]
        stream = streams[0] if streams else {}
        dauer = float(fmt.get("duration", 0) or 0)
        fps_roh = stream.get("avg_frame_rate", "0/0")
        try:
            zaehler, nenner = fps_roh.split("/")
            fps = round(float(zaehler) / float(nenner), 2) if float(nenner) else 0
        except (ValueError, ZeroDivisionError):
            fps = 0
        return ok("video.info",
                  f"{dauer:.1f}s · {stream.get('width', '?')}×{stream.get('height', '?')} · "
                  f"{fps} fps · {stream.get('codec_name', '?')}",
                  dauer_sekunden=round(dauer, 2), breite=stream.get("width", 0),
                  hoehe=stream.get("height", 0), fps=fps, codec=stream.get("codec_name", ""),
                  bitrate=fmt.get("bit_rate", ""))

    def video_convert(path: str, output: str, overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        return ffmpeg_lauf(["-i", str(quelle(path)), str(out)], "video.convert",
                           f"Konvertiert: {out.name}", pfad=str(out))

    def video_trim(path: str, output: str, start: str, duration: str = "",
                   overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-ss", str(start)]
        if duration:
            args += ["-t", str(duration)]
        args += ["-c", "copy", str(out)]
        return ffmpeg_lauf(args, "video.trim", f"Ausschnitt ab {start}: {out.name}", pfad=str(out))

    def video_thumbnail(path: str, output: str, timestamp: str = "00:00:01",
                        overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-ss", str(timestamp), "-i", str(quelle(path)), "-frames:v", "1", str(out)]
        return ffmpeg_lauf(args, "video.thumbnail", f"Frame bei {timestamp}: {out.name}",
                           pfad=str(out))

    def video_resize(path: str, output: str, width: int = 0, height: int = -2,
                     overwrite: bool = False) -> ToolResult:
        if not width:
            raise ToolError("Es wurde keine width angegeben.")
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-vf", f"scale={int(width)}:{int(height)}", str(out)]
        return ffmpeg_lauf(args, "video.resize", f"Skaliert auf Breite {width}: {out.name}",
                           pfad=str(out))

    def video_compress(path: str, output: str, crf: int = 28,
                       overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        wert = max(0, min(int(crf or 28), 51))
        args = ["-i", str(quelle(path)), "-c:v", "libx264", "-crf", str(wert),
               "-c:a", "copy", str(out)]
        return ffmpeg_lauf(args, "video.compress", f"Komprimiert (CRF {wert}): {out.name}",
                           pfad=str(out), timeout=max(FFMPEG_TIMEOUT, 600.0))

    def video_audio_remove(path: str, output: str, overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-an", "-c:v", "copy", str(out)]
        return ffmpeg_lauf(args, "video.audio.remove", f"Ton entfernt: {out.name}", pfad=str(out))

    def video_audio_replace(path: str, audio_path: str, output: str,
                            overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-i", str(quelle(audio_path)),
               "-c:v", "copy", "-map", "0:v:0", "-map", "1:a:0", "-shortest", str(out)]
        return ffmpeg_lauf(args, "video.audio.replace", f"Ton ersetzt: {out.name}", pfad=str(out))

    def video_rotate(path: str, output: str, degrees: int,
                     overwrite: bool = False) -> ToolResult:
        zuordnung = {90: "transpose=1", 180: "transpose=1,transpose=1", 270: "transpose=2",
                    -90: "transpose=2"}
        filt = zuordnung.get(int(degrees))
        if filt is None:
            raise ToolError("degrees muss 90, 180, 270 oder -90 sein.")
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-vf", filt, str(out)]
        return ffmpeg_lauf(args, "video.rotate", f"Um {degrees}° gedreht: {out.name}", pfad=str(out))

    def video_speed(path: str, output: str, factor: float,
                    overwrite: bool = False) -> ToolResult:
        f = float(factor)
        if f <= 0:
            raise ToolError("factor muss größer als 0 sein.")
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-vf", f"setpts={1 / f}*PTS",
               "-filter:a", f"atempo={min(2.0, max(0.5, f))}", str(out)]
        return ffmpeg_lauf(args, "video.speed", f"Geschwindigkeit ×{f}: {out.name}", pfad=str(out))

    def video_gif_create(path: str, output: str, start: str = "0", duration: str = "3",
                         fps: int = 10, width: int = 480, overwrite: bool = False) -> ToolResult:
        out = ziel(output, overwrite)
        filt = f"fps={int(fps)},scale={int(width)}:-1:flags=lanczos"
        args = ["-ss", str(start), "-t", str(duration), "-i", str(quelle(path)),
               "-vf", filt, str(out)]
        return ffmpeg_lauf(args, "video.gif.create", f"GIF erstellt: {out.name}", pfad=str(out))

    def video_merge(paths: list[str], output: str, overwrite: bool = False) -> ToolResult:
        if not paths or len(paths) < 2:
            raise ToolError("Es werden mindestens zwei Dateien benötigt.")
        dateien = [quelle(p) for p in paths]
        out = ziel(output, overwrite)
        args = []
        for d in dateien:
            args += ["-i", str(d)]
        args += ["-filter_complex", f"concat=n={len(dateien)}:v=1:a=1", str(out)]
        return ffmpeg_lauf(args, "video.merge", f"{len(dateien)} Videos zusammengefügt: {out.name}",
                           pfad=str(out), anzahl=len(dateien),
                           timeout=max(FFMPEG_TIMEOUT, 600.0))

    def video_watermark_image(path: str, logo_path: str, output: str,
                              position: str = "unten-rechts",
                              overwrite: bool = False) -> ToolResult:
        positionen = {
            "unten-rechts": "W-w-10:H-h-10", "unten-links": "10:H-h-10",
            "oben-rechts": "W-w-10:10", "oben-links": "10:10",
            "mitte": "(W-w)/2:(H-h)/2",
        }
        overlay = positionen.get((position or "unten-rechts").strip().lower(),
                                 positionen["unten-rechts"])
        out = ziel(output, overwrite)
        args = ["-i", str(quelle(path)), "-i", str(quelle(logo_path)),
               "-filter_complex", f"overlay={overlay}", str(out)]
        return ffmpeg_lauf(args, "video.watermark.image", f"Logo eingeblendet: {out.name}",
                           pfad=str(out), timeout=max(FFMPEG_TIMEOUT, 600.0))

    def video_frames_extract(path: str, output_dir: str, fps: float = 1.0,
                             overwrite: bool = False) -> ToolResult:
        ordner = ws.resolve(output_dir)
        if ordner.exists() and any(ordner.iterdir()) and not overwrite:
            raise ToolError(f"Zielordner ist nicht leer: {ordner}. Mit overwrite=true fortsetzen.")
        ordner.mkdir(parents=True, exist_ok=True)
        muster = str(ordner / "frame_%05d.png")
        args = ["-i", str(quelle(path)), "-vf", f"fps={float(fps)}", muster]
        ergebnis = ffmpeg_lauf(args, "video.frames.extract", "", pfad=str(ordner))
        anzahl = len(list(ordner.glob("frame_*.png")))
        return ok("video.frames.extract", f"{anzahl} Bild(er) extrahiert nach {ordner.name}",
                  pfad=str(ordner), anzahl=anzahl)

    _img_out = text("Zielpfad im Arbeitsbereich")
    _ov = flag("Bestehendes Ziel überschreiben")

    return [
        # ── image.* -- Analyse ────────────────────────────────────────────
        Tool("image.info", "Format, Größe und Farbmodus eines Bildes.",
             params("path", path=text("Pfad zum Bild")), image_info, level=P.SAFE,
             requires=("pillow",), tags=("bild", "info")),
        Tool("image.exif.read", "Liest die EXIF-Metadaten eines Bildes (Kamera, "
             "Aufnahmedatum, ggf. GPS).",
             params("path", path=text("Pfad zum Bild")), image_exif_read, level=P.SAFE,
             requires=("pillow",), tags=("bild", "exif", "metadaten")),
        Tool("image.dominant_color", "Die auffälligste Farbe eines Bildes.",
             params("path", path=text("Pfad zum Bild")), image_dominant_color, level=P.SAFE,
             requires=("pillow",), tags=("bild", "farbe")),
        Tool("image.compare", "Vergleicht zwei gleich große Bilder pixelweise.",
             params("path_a", "path_b", path_a=text("Erstes Bild"), path_b=text("Zweites Bild")),
             image_compare, level=P.SAFE, requires=("pillow",), tags=("bild", "vergleich")),
        Tool("image.ocr", "Liest Text aus einem Bild (Tesseract OCR).",
             params("path", path=text("Pfad zum Bild"), lang=text("Sprachcode, Vorgabe eng")),
             image_ocr, level=P.READ, requires=("tesseract",), tags=("bild", "ocr", "text"),
             phrases=("lies den text aus dem bild", "ocr")),

        # ── image.* -- verändernd ─────────────────────────────────────────
        Tool("image.resize", "Ändert die Bildgröße (eine Angabe genügt, das "
             "Seitenverhältnis bleibt erhalten).",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    width=integer("Zielbreite in Pixeln"), height=integer("Zielhöhe in Pixeln"),
                    overwrite=_ov),
             image_resize, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.thumbnail", "Erstellt eine verkleinerte Vorschau.",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    max_size=integer("Längste Seite in Pixeln, Vorgabe 256"), overwrite=_ov),
             image_thumbnail, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.convert", "Wandelt ein Bild in ein anderes Format um "
             "(anhand der Zielendung).",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    overwrite=_ov), image_convert, level=P.WRITE, requires=("pillow",),
             tags=("bild", "format")),
        Tool("image.rotate", "Dreht ein Bild um einen beliebigen Winkel.",
             params("path", "output", "degrees", path=text("Pfad zum Bild"), output=_img_out,
                    degrees=number("Grad, im Uhrzeigersinn"), overwrite=_ov),
             image_rotate, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.flip", "Spiegelt ein Bild horizontal oder vertikal.",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    richtung=text("horizontal oder vertical"), overwrite=_ov),
             image_flip, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.crop", "Schneidet einen rechteckigen Ausschnitt aus.",
             params("path", "output", "left", "top", "right", "bottom",
                    path=text("Pfad zum Bild"), output=_img_out, left=integer("Links"),
                    top=integer("Oben"), right=integer("Rechts"), bottom=integer("Unten"),
                    overwrite=_ov),
             image_crop, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.grayscale", "Wandelt ein Bild in Graustufen um.",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    overwrite=_ov), image_grayscale, level=P.WRITE, requires=("pillow",),
             tags=("bild",)),
        Tool("image.compress", "Speichert ein Bild verlustbehaftet kleiner.",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    quality=integer("1-95, Vorgabe 75"), overwrite=_ov),
             image_compress, level=P.WRITE, requires=("pillow",), tags=("bild", "komprimieren")),
        Tool("image.watermark.text", "Fügt einen Textzusatz in eine Bildecke ein.",
             params("path", "output", "text", path=text("Pfad zum Bild"), output=_img_out,
                    text=text("Der Text"), position=text("unten-rechts/unten-links/"
                                                          "oben-rechts/oben-links/mitte"),
                    size=integer("Schriftgröße, Vorgabe 24"), color=text("Farbe, Vorgabe white"),
                    overwrite=_ov),
             image_watermark_text, level=P.WRITE, requires=("pillow",),
             tags=("bild", "wasserzeichen")),
        Tool("image.exif.strip", "Entfernt alle Metadaten aus einem Bild (Datenschutz).",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    overwrite=_ov), image_exif_strip, level=P.WRITE, requires=("pillow",),
             tags=("bild", "exif", "datenschutz"),
             phrases=("entferne die metadaten", "exif löschen")),
        Tool("image.merge", "Fügt mehrere Bilder nebeneinander oder übereinander zusammen.",
             params("paths", "output", paths={"type": "array", "items": {"type": "string"}},
                    output=_img_out, richtung=text("horizontal oder vertical"), overwrite=_ov),
             image_merge, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.border.add", "Fügt einen einfarbigen Rahmen hinzu.",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    width=integer("Rahmenbreite in Pixeln, Vorgabe 10"),
                    color=text("Farbe, Vorgabe black"), overwrite=_ov),
             image_border_add, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.brightness", "Ändert die Helligkeit (Faktor: 1.0 = unverändert).",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    factor=number("z. B. 1.2 für heller, 0.8 für dunkler"), overwrite=_ov),
             image_brightness, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.contrast", "Ändert den Kontrast (Faktor: 1.0 = unverändert).",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    factor=number("z. B. 1.3 für mehr Kontrast"), overwrite=_ov),
             image_contrast, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.blur", "Weichzeichnen (Gauß-Filter).",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    radius=number("Stärke, Vorgabe 2.0"), overwrite=_ov),
             image_blur, level=P.WRITE, requires=("pillow",), tags=("bild",)),
        Tool("image.sharpen", "Schärft ein Bild.",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    overwrite=_ov), image_sharpen, level=P.WRITE, requires=("pillow",),
             tags=("bild",)),
        Tool("image.pixelate", "Verpixelt ein Bild oder einen Ausschnitt daraus -- "
             "z. B. um ein Gesicht oder Kennzeichen unkenntlich zu machen.",
             params("path", "output", path=text("Pfad zum Bild"), output=_img_out,
                    block_size=integer("Größe der Pixelblöcke, Vorgabe 12"),
                    box={"type": "array", "items": {"type": "integer"},
                        "description": "[left, top, right, bottom], leer = ganzes Bild"},
                    overwrite=_ov),
             image_pixelate, level=P.WRITE, requires=("pillow",), tags=("bild", "datenschutz"),
             phrases=("mach das gesicht unkenntlich", "verpixel das")),
        Tool("image.icon.create", "Erstellt eine .ico-Datei mit mehreren Auflösungen.",
             params("path", "output", path=text("Pfad zum Quellbild (möglichst groß/quadratisch)"),
                    output=text("Zielpfad, endet auf .ico"), overwrite=_ov),
             image_icon_create, level=P.WRITE, requires=("pillow",), tags=("bild", "icon")),

        # ── audio.* -- Analyse ─────────────────────────────────────────────
        Tool("audio.info", "Dauer, Codec, Samplerate und Kanäle einer Audiodatei.",
             params("path", path=text("Pfad zur Audiodatei")), audio_info, level=P.READ,
             requires=("ffprobe",), tags=("audio", "info")),
        Tool("audio.silence_detect", "Findet stille Abschnitte in einer Audiodatei.",
             params("path", path=text("Pfad zur Audiodatei"),
                    noise_db=number("Schwelle in dB, Vorgabe -30"),
                    min_duration=number("Mindestdauer in Sekunden, Vorgabe 0.5")),
             audio_silence_detect, level=P.READ, requires=("ffmpeg",), tags=("audio", "analyse")),
        Tool("audio.volume_detect", "Misst mittlere und maximale Lautstärke.",
             params("path", path=text("Pfad zur Audiodatei")), audio_volume_detect,
             level=P.READ, requires=("ffmpeg",), tags=("audio", "analyse")),

        # ── audio.* -- verändernd ──────────────────────────────────────────
        Tool("audio.convert", "Wandelt eine Audiodatei in ein anderes Format um.",
             params("path", "output", path=text("Pfad zur Audiodatei"), output=_img_out,
                    overwrite=_ov), audio_convert, level=P.WRITE, requires=("ffmpeg",),
             tags=("audio", "format"), timeout=FFMPEG_TIMEOUT),
        Tool("audio.trim", "Schneidet einen Ausschnitt aus einer Audiodatei.",
             params("path", "output", "start", path=text("Pfad zur Audiodatei"), output=_img_out,
                    start=text("Start, z. B. 00:00:05 oder 5"),
                    duration=text("Dauer, leer = bis zum Ende"), overwrite=_ov),
             audio_trim, level=P.WRITE, requires=("ffmpeg",), tags=("audio",),
             timeout=FFMPEG_TIMEOUT),
        Tool("audio.volume", "Ändert die Lautstärke (Faktor: 1.0 = unverändert, 2.0 = doppelt).",
             params("path", "output", "factor", path=text("Pfad zur Audiodatei"), output=_img_out,
                    factor=number("z. B. 1.5"), overwrite=_ov),
             audio_volume, level=P.WRITE, requires=("ffmpeg",), tags=("audio",),
             timeout=FFMPEG_TIMEOUT),
        Tool("audio.normalize", "Gleicht die Lautheit auf einen Standardpegel an.",
             params("path", "output", path=text("Pfad zur Audiodatei"), output=_img_out,
                    overwrite=_ov), audio_normalize, level=P.WRITE, requires=("ffmpeg",),
             tags=("audio",), timeout=FFMPEG_TIMEOUT),
        Tool("audio.merge", "Fügt mehrere Audiodateien nacheinander zusammen.",
             params("paths", "output", paths={"type": "array", "items": {"type": "string"}},
                    output=_img_out, overwrite=_ov), audio_merge, level=P.WRITE,
             requires=("ffmpeg",), tags=("audio",), timeout=FFMPEG_TIMEOUT),
        Tool("audio.extract_from_video", "Extrahiert die Tonspur aus einer Videodatei.",
             params("path", "output", path=text("Pfad zur Videodatei"), output=_img_out,
                    overwrite=_ov), audio_extract_from_video, level=P.WRITE,
             requires=("ffmpeg",), tags=("audio", "video"), timeout=FFMPEG_TIMEOUT),
        Tool("audio.speed", "Ändert die Wiedergabegeschwindigkeit ohne die Tonhöhe zu ändern "
             "(0.5-2.0).",
             params("path", "output", "factor", path=text("Pfad zur Audiodatei"), output=_img_out,
                    factor=number("0.5-2.0"), overwrite=_ov),
             audio_speed, level=P.WRITE, requires=("ffmpeg",), tags=("audio",),
             timeout=FFMPEG_TIMEOUT),
        Tool("audio.fade", "Blendet eine Audiodatei ein und/oder aus.",
             params("path", "output", path=text("Pfad zur Audiodatei"), output=_img_out,
                    fade_in=number("Sekunden, 0 = kein Einblenden"),
                    fade_out=number("Sekunden, 0 = kein Ausblenden"), overwrite=_ov),
             audio_fade, level=P.WRITE, requires=("ffmpeg",), tags=("audio",),
             timeout=FFMPEG_TIMEOUT),
        Tool("audio.waveform.image", "Rendert die Wellenform als Bild.",
             params("path", "output", path=text("Pfad zur Audiodatei"), output=_img_out,
                    width=integer("Breite in Pixeln, Vorgabe 800"),
                    height=integer("Höhe in Pixeln, Vorgabe 200"), overwrite=_ov),
             audio_waveform_image, level=P.WRITE, requires=("ffmpeg",), tags=("audio", "bild"),
             timeout=FFMPEG_TIMEOUT),

        # ── video.* -- Analyse ─────────────────────────────────────────────
        Tool("video.info", "Dauer, Auflösung, Bildrate und Codec einer Videodatei.",
             params("path", path=text("Pfad zur Videodatei")), video_info, level=P.READ,
             requires=("ffprobe",), tags=("video", "info")),

        # ── video.* -- verändernd ──────────────────────────────────────────
        Tool("video.convert", "Wandelt eine Videodatei in ein anderes Format um.",
             params("path", "output", path=text("Pfad zur Videodatei"), output=_img_out,
                    overwrite=_ov), video_convert, level=P.WRITE, requires=("ffmpeg",),
             tags=("video", "format"), timeout=max(FFMPEG_TIMEOUT, 600.0)),
        Tool("video.trim", "Schneidet einen Ausschnitt aus einer Videodatei.",
             params("path", "output", "start", path=text("Pfad zur Videodatei"), output=_img_out,
                    start=text("Start, z. B. 00:00:05"), duration=text("Dauer, leer = bis Ende"),
                    overwrite=_ov), video_trim, level=P.WRITE, requires=("ffmpeg",),
             tags=("video",), timeout=max(FFMPEG_TIMEOUT, 600.0)),
        Tool("video.thumbnail", "Extrahiert ein einzelnes Bild aus einem Video.",
             params("path", "output", path=text("Pfad zur Videodatei"), output=_img_out,
                    timestamp=text("Zeitpunkt, Vorgabe 00:00:01"), overwrite=_ov),
             video_thumbnail, level=P.WRITE, requires=("ffmpeg",), tags=("video", "bild"),
             timeout=FFMPEG_TIMEOUT),
        Tool("video.resize", "Skaliert die Auflösung eines Videos.",
             params("path", "output", "width", path=text("Pfad zur Videodatei"), output=_img_out,
                    width=integer("Zielbreite in Pixeln"),
                    height=integer("Zielhöhe, -2 = proportional (Vorgabe)"), overwrite=_ov),
             video_resize, level=P.WRITE, requires=("ffmpeg",), tags=("video",),
             timeout=max(FFMPEG_TIMEOUT, 600.0)),
        Tool("video.compress", "Verkleinert die Dateigröße durch stärkere Kompression "
             "(CRF: niedriger = größer/besser, höher = kleiner/schlechter).",
             params("path", "output", path=text("Pfad zur Videodatei"), output=_img_out,
                    crf=integer("0-51, Vorgabe 28"), overwrite=_ov),
             video_compress, level=P.WRITE, requires=("ffmpeg",), tags=("video", "komprimieren"),
             timeout=600.0),
        Tool("video.audio.remove", "Entfernt die Tonspur eines Videos.",
             params("path", "output", path=text("Pfad zur Videodatei"), output=_img_out,
                    overwrite=_ov), video_audio_remove, level=P.WRITE, requires=("ffmpeg",),
             tags=("video", "audio"), timeout=FFMPEG_TIMEOUT),
        Tool("video.audio.replace", "Ersetzt die Tonspur eines Videos durch eine andere Datei.",
             params("path", "audio_path", "output", path=text("Pfad zur Videodatei"),
                    audio_path=text("Pfad zur neuen Audiodatei"), output=_img_out, overwrite=_ov),
             video_audio_replace, level=P.WRITE, requires=("ffmpeg",), tags=("video", "audio"),
             timeout=max(FFMPEG_TIMEOUT, 600.0)),
        Tool("video.rotate", "Dreht ein Video um 90/180/270 Grad.",
             params("path", "output", "degrees", path=text("Pfad zur Videodatei"),
                    output=_img_out, degrees=integer("90, 180, 270 oder -90"), overwrite=_ov),
             video_rotate, level=P.WRITE, requires=("ffmpeg",), tags=("video",),
             timeout=max(FFMPEG_TIMEOUT, 600.0)),
        Tool("video.speed", "Ändert die Wiedergabegeschwindigkeit eines Videos.",
             params("path", "output", "factor", path=text("Pfad zur Videodatei"),
                    output=_img_out, factor=number("z. B. 2.0 für doppelte Geschwindigkeit"),
                    overwrite=_ov), video_speed, level=P.WRITE, requires=("ffmpeg",),
             tags=("video",), timeout=max(FFMPEG_TIMEOUT, 600.0)),
        Tool("video.gif.create", "Erstellt ein animiertes GIF aus einem Videoausschnitt.",
             params("path", "output", path=text("Pfad zur Videodatei"), output=_img_out,
                    start=text("Start, Vorgabe 0"), duration=text("Dauer in Sekunden, Vorgabe 3"),
                    fps=integer("Bilder pro Sekunde, Vorgabe 10"),
                    width=integer("Breite in Pixeln, Vorgabe 480"), overwrite=_ov),
             video_gif_create, level=P.WRITE, requires=("ffmpeg",), tags=("video", "gif"),
             timeout=FFMPEG_TIMEOUT, phrases=("mach ein gif aus dem video",)),
        Tool("video.merge", "Fügt mehrere Videodateien nacheinander zusammen.",
             params("paths", "output", paths={"type": "array", "items": {"type": "string"}},
                    output=_img_out, overwrite=_ov), video_merge, level=P.WRITE,
             requires=("ffmpeg",), tags=("video",), timeout=600.0),
        Tool("video.watermark.image", "Blendet ein Logo/Bild in ein Video ein.",
             params("path", "logo_path", "output", path=text("Pfad zur Videodatei"),
                    logo_path=text("Pfad zum Logo/Bild"), output=_img_out,
                    position=text("unten-rechts/unten-links/oben-rechts/oben-links/mitte"),
                    overwrite=_ov),
             video_watermark_image, level=P.WRITE, requires=("ffmpeg",), tags=("video", "logo"),
             timeout=600.0),
        Tool("video.frames.extract", "Extrahiert Einzelbilder aus einem Video in einen Ordner.",
             params("path", "output_dir", path=text("Pfad zur Videodatei"),
                    output_dir=text("Zielordner im Arbeitsbereich"),
                    fps=number("Bilder pro Sekunde, Vorgabe 1.0"), overwrite=_ov),
             video_frames_extract, level=P.WRITE, requires=("ffmpeg",), tags=("video", "bild"),
             timeout=max(FFMPEG_TIMEOUT, 600.0)),
    ]
