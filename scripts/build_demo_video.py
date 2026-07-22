"""Build the reproducible 1080p M1.1 demonstration video.

Run with:
    uv run --with imageio-ffmpeg --with pillow \
        python scripts/build_demo_video.py
"""

from __future__ import annotations

import math
import re
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

import imageio_ffmpeg  # type: ignore[import-not-found]
from PIL import Image, ImageDraw, ImageFont  # type: ignore[import-not-found]

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "docs" / "assets"
CAPTURE_DIR = ASSET_DIR / "demo"
SRT_PATH = ROOT / "docs" / "demo-video-captions.srt"
OUTPUT_PATH = ASSET_DIR / "portfolio-analytics-demo.mp4"
VIDEO_SECONDS = 180.0
WIDTH = 1920
HEIGHT = 1080
FPS = 30
FONT_PATH = Path("/System/Library/Fonts/SFNS.ttf")
MONO_FONT_PATH = Path("/System/Library/Fonts/SFNSMono.ttf")


@dataclass(frozen=True)
class Caption:
    index: int
    start: float
    end: float
    text: str


@dataclass(frozen=True)
class Scene:
    start: float
    end: float
    image: Path


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, text=True, capture_output=True)


def _timestamp_seconds(value: str) -> float:
    hours, minutes, remainder = value.split(":")
    seconds, milliseconds = remainder.split(",")
    return (
        int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000
    )


def parse_captions(path: Path) -> list[Caption]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    captions: list[Caption] = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            raise ValueError(f"Invalid SRT block: {block!r}")
        start_text, end_text = lines[1].split(" --> ")
        captions.append(
            Caption(
                index=int(lines[0]),
                start=_timestamp_seconds(start_text),
                end=_timestamp_seconds(end_text),
                text=" ".join(lines[2:]),
            )
        )
    return captions


def validate_captions(captions: list[Caption]) -> int:
    if not captions or captions[0].start != 0:
        raise ValueError("Captions must start at 00:00:00,000")
    for expected_index, caption in enumerate(captions, start=1):
        if caption.index != expected_index:
            raise ValueError("Caption indexes must be contiguous")
        if caption.end <= caption.start:
            raise ValueError(f"Caption {caption.index} has an invalid interval")
    for previous, current in zip(captions, captions[1:], strict=False):
        if not math.isclose(previous.end, current.start, abs_tol=0.001):
            raise ValueError("Caption intervals must cover the video continuously")
    if not math.isclose(captions[-1].end, VIDEO_SECONDS, abs_tol=0.001):
        raise ValueError("Captions must end at exactly 00:03:00,000")

    word_count = sum(len(re.findall(r"\b[\w’'-]+\b", cue.text)) for cue in captions)
    if not 360 <= word_count <= 400:
        raise ValueError(f"Narration must contain 360–400 words, found {word_count}")
    return word_count


def media_duration(ffmpeg: str, path: Path) -> float:
    result = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-f", "null", "-"],
        check=False,
        text=True,
        capture_output=True,
    )
    match = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if match is None:
        raise ValueError(f"Could not read media duration for {path}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def create_narration(ffmpeg: str, captions: list[Caption], workdir: Path) -> Path:
    wav_files: list[Path] = []
    for caption in captions:
        duration = caption.end - caption.start
        aiff_path = workdir / f"voice-{caption.index:02d}.aiff"
        wav_path = workdir / f"voice-{caption.index:02d}.wav"
        _run(
            [
                "/usr/bin/say",
                "-v",
                "Samantha",
                "-r",
                "160",
                "-o",
                str(aiff_path),
                caption.text,
            ]
        )
        raw_duration = media_duration(ffmpeg, aiff_path)
        available = max(duration - 0.25, 0.5)
        tempo = max(raw_duration / available, 1.0)
        if tempo > 2.0:
            raise ValueError(f"Caption {caption.index} cannot fit its interval")
        filters = []
        if tempo > 1.001:
            filters.append(f"atempo={tempo:.6f}")
        filters.append(f"apad=pad_dur={duration:.3f}")
        _run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(aiff_path),
                "-af",
                ",".join(filters),
                "-t",
                f"{duration:.3f}",
                "-ar",
                "48000",
                "-ac",
                "1",
                "-c:a",
                "pcm_s16le",
                str(wav_path),
            ]
        )
        wav_files.append(wav_path)

    concat_path = workdir / "audio-concat.txt"
    concat_path.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in wav_files),
        encoding="utf-8",
    )
    narration_path = workdir / "narration.wav"
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c:a",
            "pcm_s16le",
            str(narration_path),
        ]
    )
    return narration_path


def _font(size: int, *, mono: bool = False) -> ImageFont.FreeTypeFont:
    path = MONO_FONT_PATH if mono else FONT_PATH
    return ImageFont.truetype(str(path), size=size)


def _draw_wrapped(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple[int, int],
    *,
    font: ImageFont.FreeTypeFont,
    fill: str,
    width: int,
    spacing: int = 12,
) -> int:
    lines = textwrap.wrap(text, width=width)
    x, y = xy
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += font.size + spacing
    return y


def create_title_card(path: Path, kind: str) -> None:
    image = Image.new("RGB", (WIDTH, HEIGHT), "#0b1220")
    draw = ImageDraw.Draw(image)
    for x in range(0, WIDTH, 72):
        draw.line((x, 0, x, HEIGHT), fill="#152035", width=1)
    for y in range(0, HEIGHT, 72):
        draw.line((0, y, WIDTH, y), fill="#152035", width=1)

    draw.rounded_rectangle((160, 100, 226, 166), radius=14, fill="#162338")
    draw.text((176, 119), "PA", font=_font(24, mono=True), fill="#6ee7b7")
    draw.text((250, 112), "PORTFOLIO ANALYTICS", font=_font(30), fill="#f8fafc")

    if kind == "architecture":
        draw.text((160, 230), "Restrained architecture", font=_font(72), fill="#f8fafc")
        draw.text(
            (164, 325),
            "Deterministic financial metrics. Explicit trust boundaries.",
            font=_font(32),
            fill="#a7f3d0",
        )
        boxes = [
            ("NEXT.JS BFF", "HttpOnly session", 160, 470),
            ("FASTAPI", "Owner-scoped use cases", 620, 470),
            ("DOMAIN", "Pure valuation + metrics", 1080, 470),
            ("POSTGRESQL", "Decimal ledger", 390, 720),
            ("REDIS", "Cache + rate limits", 850, 720),
            ("OPTIONAL LLM", "Explain only", 1310, 720),
        ]
        for title, subtitle, x, y in boxes:
            draw.rounded_rectangle(
                (x, y, x + 380, y + 145),
                radius=18,
                fill="#111c30",
                outline="#334155",
                width=2,
            )
            draw.text(
                (x + 28, y + 30),
                title,
                font=_font(25, mono=True),
                fill="#6ee7b7",
            )
            draw.text((x + 28, y + 82), subtitle, font=_font(24), fill="#cbd5e1")
        for start, end in [((540, 542), (620, 542)), ((1000, 542), (1080, 542))]:
            draw.line((*start, *end), fill="#6ee7b7", width=5)
    elif kind == "security":
        draw.text(
            (160, 230),
            "Security + delivery evidence",
            font=_font(68),
            fill="#f8fafc",
        )
        items = [
            "HttpOnly + Secure + SameSite=Lax BFF session",
            "Owner checks and indistinguishable missing/foreign 404s",
            "Idempotent transactions and HMAC-hashed rate-limit keys",
            "Offline unit tests, PostgreSQL, Redis, migration, and image smoke",
        ]
        y = 390
        for item in items:
            draw.ellipse((170, y + 8, 192, y + 30), fill="#6ee7b7")
            y = (
                _draw_wrapped(
                    draw,
                    item,
                    (225, y),
                    font=_font(34),
                    fill="#e2e8f0",
                    width=58,
                    spacing=14,
                )
                + 34
            )
        draw.rounded_rectangle((1420, 360, 1735, 680), radius=28, fill="#ecfdf5")
        draw.text((1505, 420), "CI", font=_font(86), fill="#065f46")
        draw.text((1478, 545), "PASS", font=_font(52, mono=True), fill="#047857")
    elif kind == "closing":
        draw.text(
            (160, 245),
            "Explain historical risk.",
            font=_font(78),
            fill="#f8fafc",
        )
        draw.text(
            (160, 340),
            "Never predict or advise.",
            font=_font(78),
            fill="#6ee7b7",
        )
        links = [
            "LIVE DEMO  portfolio-analytics-web-hazel.vercel.app",
            "BACKEND    github.com/RujingXu-bit/Ledger-Lens-api",
            "FRONTEND   github.com/RujingXu-bit/Ledger-Lens-web",
            "RELEASE    portfolio-analytics-api/releases/tag/v1.1.0",
        ]
        y = 535
        for link in links:
            draw.text((168, y), link, font=_font(27, mono=True), fill="#cbd5e1")
            y += 72
        draw.text(
            (160, 930),
            "Historical analysis · synthetic demo data · not investment advice",
            font=_font(27),
            fill="#94a3b8",
        )
    else:
        raise ValueError(f"Unknown title-card kind: {kind}")
    image.save(path)


def label_capture(source: Path, destination: Path, label: str) -> None:
    image = Image.open(source).convert("RGB")
    if image.size != (WIDTH, HEIGHT):
        image = image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((62, 960, 800, 1035), radius=16, fill="#0b1220")
    draw.text((90, 982), label, font=_font(23, mono=True), fill="#a7f3d0")
    image.save(destination)


def create_scene_video(ffmpeg: str, scene: Scene, index: int, workdir: Path) -> Path:
    duration = scene.end - scene.start
    output = workdir / f"scene-{index:02d}.mp4"
    fade_out = max(duration - 0.35, 0)
    video_filter = (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0b1220,"
        "format=yuv420p,"
        f"fade=t=in:st=0:d=0.35,fade=t=out:st={fade_out:.3f}:d=0.35"
    )
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(scene.image),
            "-t",
            f"{duration:.3f}",
            "-vf",
            video_filter,
            "-r",
            str(FPS),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ]
    )
    return output


def create_video(ffmpeg: str, narration: Path, workdir: Path) -> None:
    architecture = workdir / "architecture.png"
    security = workdir / "security.png"
    closing = workdir / "closing.png"
    create_title_card(architecture, "architecture")
    create_title_card(security, "security")
    create_title_card(closing, "closing")

    recorded_workflow = workdir / "recorded-workflow.png"
    recorded_analytics = workdir / "recorded-analytics.png"
    recorded_methodology = workdir / "recorded-methodology.png"
    recorded_risk = workdir / "recorded-risk.png"
    recorded_history = workdir / "recorded-history.png"
    label_capture(
        CAPTURE_DIR / "06-ledger.png",
        recorded_workflow,
        "PRE-RECORDED SYNTHETIC WORKFLOW",
    )
    label_capture(
        CAPTURE_DIR / "07-live-analytics.png",
        recorded_analytics,
        "PRE-RECORDED PROVIDER SUCCESS · 22 JUL 2026",
    )
    label_capture(
        CAPTURE_DIR / "09-methodology.png",
        recorded_methodology,
        "PRE-RECORDED PROVIDER SUCCESS · 22 JUL 2026",
    )
    label_capture(
        CAPTURE_DIR / "08-risk-history.png",
        recorded_risk,
        "PRE-RECORDED DETERMINISTIC FALLBACK",
    )
    label_capture(
        CAPTURE_DIR / "10-live-history.png",
        recorded_history,
        "PRE-RECORDED SNAPSHOT HISTORY",
    )

    scenes = [
        Scene(0, 20, CAPTURE_DIR / "01-landing.png"),
        Scene(20, 45, architecture),
        Scene(45, 55, CAPTURE_DIR / "04-register.png"),
        Scene(55, 65, CAPTURE_DIR / "05-create-portfolio.png"),
        Scene(65, 85, recorded_workflow),
        Scene(85, 107, recorded_analytics),
        Scene(107, 125, recorded_methodology),
        Scene(125, 138, recorded_risk),
        Scene(138, 150, recorded_history),
        Scene(150, 160, security),
        Scene(160, 170, CAPTURE_DIR / "03-ci-success.png"),
        Scene(170, 180, closing),
    ]
    if any(not scene.image.exists() for scene in scenes):
        missing = [str(scene.image) for scene in scenes if not scene.image.exists()]
        raise FileNotFoundError(f"Missing demo captures: {missing}")

    segments = [
        create_scene_video(ffmpeg, scene, index, workdir)
        for index, scene in enumerate(scenes, start=1)
    ]
    concat_path = workdir / "video-concat.txt"
    concat_path.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in segments),
        encoding="utf-8",
    )
    silent_video = workdir / "silent.mp4"
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_path),
            "-c",
            "copy",
            str(silent_video),
        ]
    )

    subtitle_filter = (
        f"subtitles=filename='{SRT_PATH.as_posix()}':"
        "force_style='FontName=Helvetica,FontSize=12,PrimaryColour=&H00FFFFFF,"
        "BackColour=&HC00B1220,BorderStyle=3,Outline=0,Shadow=0,"
        "MarginV=22,Alignment=2'"
    )
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(silent_video),
            "-i",
            str(narration),
            "-vf",
            subtitle_filter,
            "-t",
            f"{VIDEO_SECONDS:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(OUTPUT_PATH),
        ]
    )


def main() -> None:
    captions = parse_captions(SRT_PATH)
    word_count = validate_captions(captions)
    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory(prefix="portfolio-analytics-video-") as temp:
        workdir = Path(temp)
        narration = create_narration(ffmpeg, captions, workdir)
        create_video(ffmpeg, narration, workdir)

    duration = media_duration(ffmpeg, OUTPUT_PATH)
    if not 170 <= duration <= 185:
        raise ValueError(f"Video duration {duration:.2f}s is outside 2:50–3:05")
    print(f"Built {OUTPUT_PATH}")
    print(f"Narration words: {word_count}")
    print(f"Duration: {duration:.2f}s")
    print(f"Resolution: {WIDTH}x{HEIGHT} at {FPS} fps")


if __name__ == "__main__":
    main()
