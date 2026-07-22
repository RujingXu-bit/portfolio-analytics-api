from __future__ import annotations

import re
from pathlib import Path


def _milliseconds(timestamp: str) -> int:
    hours, minutes, remainder = timestamp.split(":")
    seconds, milliseconds = remainder.split(",")
    return (
        int(hours) * 3_600_000
        + int(minutes) * 60_000
        + int(seconds) * 1_000
        + int(milliseconds)
    )


def test_demo_video_narration_matches_contiguous_captions() -> None:
    script = Path("docs/demo-video-script.md").read_text(encoding="utf-8")
    srt = Path("docs/demo-video-captions.srt").read_text(encoding="utf-8")

    narration = " ".join(
        line.removeprefix("> ").strip()
        for line in script.splitlines()
        if line.startswith("> ")
    )
    blocks = re.split(r"\n\s*\n", srt.strip())
    intervals: list[tuple[int, int]] = []
    caption_text: list[str] = []
    for expected_index, block in enumerate(blocks, start=1):
        lines = block.splitlines()
        assert int(lines[0]) == expected_index
        start_text, end_text = lines[1].split(" --> ")
        intervals.append((_milliseconds(start_text), _milliseconds(end_text)))
        caption_text.append(" ".join(lines[2:]))

    assert narration == " ".join(caption_text)
    assert intervals[0][0] == 0
    assert intervals[-1][1] == 180_000
    assert all(
        previous[1] == current[0]
        for previous, current in zip(intervals, intervals[1:], strict=False)
    )
    assert all(start < end for start, end in intervals)

    word_count = len(re.findall(r"\b[\w’'-]+\b", narration))
    assert 360 <= word_count <= 400


def test_demo_video_portfolio_captures_are_tracked() -> None:
    for asset in (
        "dashboard-demo.png",
        "demo/01-landing.png",
        "demo/02-offline-demo.png",
        "demo/03-ci-success.png",
        "demo/04-register.png",
        "demo/05-create-portfolio.png",
        "demo/06-ledger.png",
        "demo/07-live-analytics.png",
        "demo/08-risk-history.png",
        "demo/09-methodology.png",
        "demo/10-live-history.png",
    ):
        path = Path("docs/assets") / asset
        assert path.stat().st_size > 10_000


def test_readme_exposes_portfolio_entry_points() -> None:
    readme = Path("README.md").read_text(encoding="utf-8")

    for required in (
        "https://portfolio-analytics-web-hazel.vercel.app",
        "releases/download/v1.1.0/portfolio-analytics-demo.mp4",
        "docs/assets/dashboard-demo.png",
        "docs/demo-video-script.md",
        "docs/demo-video-captions.srt",
        "https://github.com/RujingXu-bit/Ledger-Lens-web",
        "releases/tag/v1.2.0",
        "docs/interview-guide.md",
    ):
        assert required in readme
