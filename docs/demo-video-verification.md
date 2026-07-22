# M1.1 Demo Video Verification

Verification date: 2026-07-22 (Europe/Dublin)

## Final media

- Public asset: [GitHub Release download](https://github.com/RujingXu-bit/portfolio-analytics-api/releases/download/v1.1.0/portfolio-analytics-demo.mp4)
- Local build output: `docs/assets/portfolio-analytics-demo.mp4` (ignored because
  the 10 MB final binary is stored as a Release asset rather than duplicated in
  Git history)
- Duration: `00:03:00.00`
- Video: H.264 High, `1920×1080`, 16:9, 30 fps
- Audio: AAC LC, 48 kHz, mono
- Narration: 373 English words
- Captions: 18 continuous cues, burned into the image and also available as SRT
- Size: 10,165,227 bytes
- SHA-256: `fbca3448e8d36113b055554f431fa95485475b7f0f16912d4440dbec9b86e05d`

The media was built from the checked-in SRT and verified public captures with:

```bash
uv run --with imageio-ffmpeg --with pillow \
  python scripts/build_demo_video.py
```

## Three consecutive rehearsals

The final MP4 was decoded from beginning to end three consecutive times after
the last subtitle-size correction. All three completed with zero decoder errors:

| Rehearsal | Result | Evidence reviewed |
|---|---|---|
| 1 | PASS | Full 180-second audio/video decode; opening, architecture, registration, ledger, analytics, risk, CI, and closing timeline checkpoints |
| 2 | PASS | Full 180-second audio/video decode; English subtitle readability and pre-recorded Provider labels |
| 3 | PASS | Full 180-second audio/video decode; 16:9 composition, disclaimer, public links, and closing boundary statement |

The command used for each full-file pass was:

```bash
ffmpeg -v error -i docs/assets/portfolio-analytics-demo.mp4 -f null -
```

Visual QA sampled frames at 0, 25, 50, 70, 90, 115, 130, 145, 155, 165,
and 175 seconds. An initial render was rejected because its burned subtitles
were too large; the final render uses the corrected subtitle scale.

## Provider-failure fallback rehearsal

A controlled fallback rehearsal switched from the Provider-backed storyline to
the public `/demo` route and verified the visible statement:

> Deterministic offline fixture — This page makes no network or provider calls.
> Every value is a fixed synthetic sample for demonstration and outage fallback,
> not a live portfolio result.

The fallback then showed the fixed metrics, allocation, deterministic summary,
ledger, and snapshot provenance before moving to the clearly labelled
`PRE-RECORDED PROVIDER SUCCESS · 22 JUL 2026` frame and the successful GitHub
Actions frame. At no point was a fixture, cached value, or recorded frame
described as a current Provider result.

## Claim boundaries

- The public analytics capture is an observed demo result, not a benchmark or
  production-capacity claim.
- Lighthouse and local cache comparisons remain single-environment measurements,
  not an SLA.
- The video does not claim forecasting, investment advice, automatic trading,
  high availability, or a second real market-data Provider.
