"""Das Medien-Pack: Bild echt (Pillow ist immer da), Audio/Video echt wo
``ffmpeg``/``ffprobe`` installiert sind, sonst die ehrliche Fehlermeldung.

Synthetische Testdateien statt mitgelieferter Assets: ein Bild aus reinem
Pillow-Code, Audio/Video über ffmpegs eigene ``lavfi``-Testquellen
(Sinuston, Testbild) -- kein Netzwerk, keine Lizenzfragen, jederzeit
reproduzierbar.
"""

from __future__ import annotations

import shutil

import pytest

from jarvis.tools import build_registry
from jarvis.tools.base import ToolResult

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402


@pytest.fixture
def tools(config, store):
    registry = build_registry(config, store)

    def call(tool: str, /, **arguments) -> ToolResult:
        return registry.call(tool, arguments)

    call.registry = registry
    return call


def erfolg(result: ToolResult) -> ToolResult:
    assert result.ok, f"{result.tool} fehlgeschlagen: {result.summary}"
    return result


def fehler(result: ToolResult) -> ToolResult:
    assert not result.ok, f"{result.tool} hätte fehlschlagen müssen: {result.summary}"
    return result


_hat_ffmpeg = shutil.which("ffmpeg") is not None
_hat_ffprobe = shutil.which("ffprobe") is not None
_hat_tesseract = shutil.which("tesseract") is not None
braucht_ffmpeg = pytest.mark.skipif(not _hat_ffmpeg, reason="ffmpeg nicht installiert")
braucht_ffprobe = pytest.mark.skipif(not _hat_ffprobe, reason="ffprobe nicht installiert")
braucht_tesseract = pytest.mark.skipif(not _hat_tesseract, reason="tesseract nicht installiert")


@pytest.fixture
def bild(workspace):
    pfad = workspace / "foto.png"
    img = Image.new("RGB", (120, 80), "red")
    for x in range(60):
        for y in range(40):
            img.putpixel((x, y), (0, 0, 255))
    img.save(pfad)
    return pfad


@pytest.fixture
def zweites_bild(workspace):
    pfad = workspace / "zweites.png"
    Image.new("RGB", (120, 80), "green").save(pfad)
    return pfad


@pytest.fixture
def ton(workspace):
    """Zwei Sekunden 440-Hz-Sinuston -- über ffmpegs eigene Testquelle,
    ohne externe Datei."""
    pfad = workspace / "ton.wav"
    from jarvis.tools.catalog import run_process
    res = run_process(["ffmpeg", "-y", "-nostdin", "-hide_banner", "-f", "lavfi",
                       "-i", "sine=frequency=440:duration=2", str(pfad)], timeout=30)
    assert res.returncode == 0, res.stderr
    return pfad


@pytest.fixture
def clip(workspace):
    """Zwei Sekunden Testbild+Ton als .mp4 -- über ffmpegs lavfi-Quellen."""
    pfad = workspace / "clip.mp4"
    from jarvis.tools.catalog import run_process
    res = run_process(["ffmpeg", "-y", "-nostdin", "-hide_banner", "-f", "lavfi",
                       "-i", "testsrc=duration=2:size=160x120:rate=10", "-f", "lavfi",
                       "-i", "sine=frequency=440:duration=2", "-c:v", "libx264",
                       "-c:a", "aac", "-shortest", str(pfad)], timeout=60)
    assert res.returncode == 0, res.stderr
    return pfad


# ═══════════════════════════════════════════════════════════════ image.*
def test_image_info(tools, bild):
    res = erfolg(tools("image.info", path="foto.png"))
    assert res.evidence["breite"] == 120 and res.evidence["hoehe"] == 80


def test_image_resize_haelt_seitenverhaeltnis(tools, bild):
    res = erfolg(tools("image.resize", path="foto.png", output="klein.png", width=60))
    assert res.evidence["breite"] == 60 and res.evidence["hoehe"] == 40


def test_image_thumbnail(tools, bild):
    res = erfolg(tools("image.thumbnail", path="foto.png", output="thumb.png", max_size=50))
    assert max(res.evidence["breite"], res.evidence["hoehe"]) <= 50


def test_image_convert(tools, bild, workspace):
    erfolg(tools("image.convert", path="foto.png", output="foto.jpg"))
    assert Image.open(workspace / "foto.jpg").format == "JPEG"


def test_image_rotate(tools, bild, workspace):
    erfolg(tools("image.rotate", path="foto.png", output="gedreht.png", degrees=90))
    gedreht = Image.open(workspace / "gedreht.png")
    assert gedreht.width == 80 and gedreht.height == 120


def test_image_flip(tools, bild, workspace):
    erfolg(tools("image.flip", path="foto.png", output="gespiegelt.png", richtung="horizontal"))
    original, gespiegelt = Image.open(workspace / "foto.png"), Image.open(workspace / "gespiegelt.png")
    assert original.getpixel((0, 0)) == gespiegelt.getpixel((119, 0))


def test_image_crop(tools, bild):
    res = erfolg(tools("image.crop", path="foto.png", output="crop.png",
                       left=0, top=0, right=60, bottom=40))
    assert res.evidence["breite"] == 60 and res.evidence["hoehe"] == 40


def test_image_grayscale(tools, bild, workspace):
    erfolg(tools("image.grayscale", path="foto.png", output="grau.png"))
    assert Image.open(workspace / "grau.png").mode == "L"


def test_image_compress_wird_kleiner(tools, bild, workspace):
    res = erfolg(tools("image.compress", path="foto.png", output="komprimiert.jpg", quality=30))
    assert res.evidence["nachher_bytes"] > 0


def test_image_watermark_text(tools, bild, workspace):
    erfolg(tools("image.watermark.text", path="foto.png", output="marke.png",
                 text="Jarvis"))
    assert (workspace / "marke.png").exists()


def test_image_exif_read_ohne_exif(tools, bild):
    res = erfolg(tools("image.exif.read", path="foto.png"))
    assert res.payload == "(keine)"


def test_image_exif_strip(tools, bild, workspace):
    erfolg(tools("image.exif.strip", path="foto.png", output="sauber.png"))
    assert (workspace / "sauber.png").exists()


def test_image_dominant_color(tools, bild):
    res = erfolg(tools("image.dominant_color", path="foto.png"))
    assert res.evidence["hex"].startswith("#")


def test_image_compare_identisch_und_verschieden(tools, bild, zweites_bild, workspace):
    gleich = erfolg(tools("image.compare", path_a="foto.png", path_b="foto.png"))
    assert gleich.evidence["identisch"] is True

    Image.new("RGB", (120, 80), "green").save(workspace / "gruenklon.png")
    verschieden = erfolg(tools("image.compare", path_a="foto.png", path_b="gruenklon.png"))
    assert verschieden.evidence["abweichung_prozent"] > 0


def test_image_merge(tools, bild, zweites_bild):
    res = erfolg(tools("image.merge", paths=["foto.png", "zweites.png"],
                       output="zusammen.png", richtung="horizontal"))
    assert res.evidence["anzahl"] == 2


def test_image_border_add(tools, bild):
    res = erfolg(tools("image.border.add", path="foto.png", output="rahmen.png", width=5))
    assert res.ok


def test_image_brightness_und_contrast(tools, bild):
    erfolg(tools("image.brightness", path="foto.png", output="hell.png", factor=1.5))
    erfolg(tools("image.contrast", path="foto.png", output="kontrast.png", factor=1.5))


def test_image_blur_und_sharpen(tools, bild):
    erfolg(tools("image.blur", path="foto.png", output="blur.png", radius=3))
    erfolg(tools("image.sharpen", path="foto.png", output="scharf.png"))


def test_image_pixelate_nur_ausschnitt(tools, bild, workspace):
    erfolg(tools("image.pixelate", path="foto.png", output="pixel.png",
                 block_size=10, box=[0, 0, 60, 40]))
    pix = Image.open(workspace / "pixel.png")
    original = Image.open(workspace / "foto.png")
    # Außerhalb des Ausschnitts unverändert:
    assert pix.getpixel((100, 70)) == original.getpixel((100, 70))


def test_image_icon_create(tools, bild, workspace):
    res = erfolg(tools("image.icon.create", path="foto.png", output="icon.ico"))
    assert res.evidence["groessen"]
    assert (workspace / "icon.ico").exists()


@braucht_tesseract
def test_image_ocr_mit_tesseract(tools, workspace):
    text_bild = Image.new("RGB", (200, 60), "white")
    text_bild.save(workspace / "text.png")
    res = tools("image.ocr", path="text.png")
    assert res.ok


def test_image_ocr_ohne_tesseract_meldet_das_ehrlich(tools, bild, monkeypatch):
    if _hat_tesseract:
        pytest.skip("tesseract ist hier installiert -- der Fehlerfall lässt sich so nicht auslösen")
    fehler(tools("image.ocr", path="foto.png"))


# ═══════════════════════════════════════════════════════════════ Sicherheit
def test_output_wird_nicht_ohne_overwrite_ueberschrieben(tools, bild, workspace):
    (workspace / "belegt.png").write_bytes(b"schon da")
    fehler(tools("image.resize", path="foto.png", output="belegt.png", width=10))
    erfolg(tools("image.resize", path="foto.png", output="belegt.png", width=10,
                 overwrite=True))


def test_pfad_ausserhalb_des_arbeitsbereichs_wird_abgelehnt(tools):
    fehler(tools("image.info", path="/etc/hostname"))


def test_kaputte_bilddatei_wird_ehrlich_abgelehnt(tools, workspace):
    (workspace / "kaputt.png").write_bytes(b"das ist kein bild")
    fehler(tools("image.info", path="kaputt.png"))


# ═══════════════════════════════════════════════════════════════ audio.*
@braucht_ffprobe
def test_audio_info(tools, ton):
    res = erfolg(tools("audio.info", path="ton.wav"))
    assert 1.5 < res.evidence["dauer_sekunden"] < 2.5


def test_audio_info_ohne_ffprobe_meldet_das_ehrlich(tools, workspace, monkeypatch):
    if _hat_ffprobe:
        pytest.skip("ffprobe ist hier installiert")
    (workspace / "ton.wav").write_bytes(b"x")
    fehler(tools("audio.info", path="ton.wav"))


@braucht_ffmpeg
def test_audio_convert(tools, ton, workspace):
    erfolg(tools("audio.convert", path="ton.wav", output="ton.mp3"))
    assert (workspace / "ton.mp3").exists()


@braucht_ffmpeg
def test_audio_trim(tools, ton, workspace):
    erfolg(tools("audio.trim", path="ton.wav", output="kurz.wav", start="0", duration="1"))
    assert (workspace / "kurz.wav").exists()


@braucht_ffmpeg
def test_audio_volume(tools, ton, workspace):
    erfolg(tools("audio.volume", path="ton.wav", output="laut.wav", factor=2.0))
    assert (workspace / "laut.wav").exists()


@braucht_ffmpeg
def test_audio_normalize(tools, ton, workspace):
    erfolg(tools("audio.normalize", path="ton.wav", output="norm.wav"))
    assert (workspace / "norm.wav").exists()


@braucht_ffmpeg
def test_audio_merge(tools, ton, workspace):
    res = erfolg(tools("audio.merge", paths=["ton.wav", "ton.wav"], output="doppelt.wav"))
    assert res.evidence["anzahl"] == 2


@braucht_ffmpeg
def test_audio_speed_grenzen(tools, ton):
    erfolg(tools("audio.speed", path="ton.wav", output="schnell.wav", factor=1.5))
    fehler(tools("audio.speed", path="ton.wav", output="ungueltig.wav", factor=5.0))


@braucht_ffmpeg
def test_audio_fade(tools, ton, workspace):
    erfolg(tools("audio.fade", path="ton.wav", output="fade.wav", fade_in=0.5, fade_out=0.5))
    assert (workspace / "fade.wav").exists()


@braucht_ffmpeg
def test_audio_silence_detect(tools, workspace):
    from jarvis.tools.catalog import run_process
    stille = workspace / "stille.wav"
    res = run_process(["ffmpeg", "-y", "-nostdin", "-hide_banner", "-f", "lavfi",
                       "-i", "anullsrc=duration=2", str(stille)], timeout=30)
    assert res.returncode == 0
    ergebnis = erfolg(tools("audio.silence_detect", path="stille.wav"))
    assert ergebnis.evidence["anzahl"] >= 1


@braucht_ffmpeg
def test_audio_volume_detect(tools, ton):
    res = erfolg(tools("audio.volume_detect", path="ton.wav"))
    assert "volume" in res.payload.lower()


@braucht_ffmpeg
def test_audio_waveform_image(tools, ton, workspace):
    erfolg(tools("audio.waveform.image", path="ton.wav", output="wellenform.png"))
    assert (workspace / "wellenform.png").exists()


# ═══════════════════════════════════════════════════════════════ video.*
@braucht_ffprobe
def test_video_info(tools, clip):
    res = erfolg(tools("video.info", path="clip.mp4"))
    assert res.evidence["breite"] == 160 and res.evidence["hoehe"] == 120


@braucht_ffmpeg
def test_video_thumbnail(tools, clip, workspace):
    erfolg(tools("video.thumbnail", path="clip.mp4", output="frame.png", timestamp="00:00:01"))
    assert (workspace / "frame.png").exists()


@braucht_ffmpeg
def test_video_trim(tools, clip, workspace):
    erfolg(tools("video.trim", path="clip.mp4", output="kurz.mp4", start="0", duration="1"))
    assert (workspace / "kurz.mp4").exists()


@braucht_ffmpeg
def test_video_resize(tools, clip, workspace):
    erfolg(tools("video.resize", path="clip.mp4", output="klein.mp4", width=80))
    assert (workspace / "klein.mp4").exists()


@braucht_ffmpeg
def test_video_audio_remove(tools, clip, workspace):
    erfolg(tools("video.audio.remove", path="clip.mp4", output="stumm.mp4"))
    assert (workspace / "stumm.mp4").exists()


@braucht_ffmpeg
def test_video_audio_replace(tools, clip, ton, workspace):
    erfolg(tools("video.audio.replace", path="clip.mp4", audio_path="ton.wav",
                 output="neuerton.mp4"))
    assert (workspace / "neuerton.mp4").exists()


@braucht_ffmpeg
def test_video_rotate_ungueltiger_winkel(tools, clip):
    fehler(tools("video.rotate", path="clip.mp4", output="dreh.mp4", degrees=45))


@braucht_ffmpeg
def test_video_rotate(tools, clip, workspace):
    erfolg(tools("video.rotate", path="clip.mp4", output="dreh.mp4", degrees=90))
    assert (workspace / "dreh.mp4").exists()


@braucht_ffmpeg
def test_video_gif_create(tools, clip, workspace):
    erfolg(tools("video.gif.create", path="clip.mp4", output="anim.gif",
                 start="0", duration="1", fps=5, width=80))
    assert (workspace / "anim.gif").exists()


@braucht_ffmpeg
def test_video_merge(tools, clip, workspace):
    res = erfolg(tools("video.merge", paths=["clip.mp4", "clip.mp4"], output="doppelt.mp4"))
    assert res.evidence["anzahl"] == 2


@braucht_ffmpeg
def test_video_watermark_image(tools, clip, bild, workspace):
    erfolg(tools("video.watermark.image", path="clip.mp4", logo_path="foto.png",
                 output="logo.mp4"))
    assert (workspace / "logo.mp4").exists()


@braucht_ffmpeg
def test_video_frames_extract(tools, clip, workspace):
    res = erfolg(tools("video.frames.extract", path="clip.mp4", output_dir="frames", fps=2))
    assert res.evidence["anzahl"] >= 2
    assert list((workspace / "frames").glob("frame_*.png"))
