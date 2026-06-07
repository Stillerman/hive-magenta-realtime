# Hive 🐝

**300 minds are better than one.** Harness [Magenta RealTime 2](https://github.com/magenta/magenta-realtime) so it can be played interactively by 100s of people in real time.

Put a QR code on the big screen. The room scans it, types musical vibes from their phones — *"reggae"*, *"sub bass"*, *"church organ"* — and every prompt is blended into one live style embedding that drives the streaming model. The music is whatever the crowd is feeling, right now. Vibes have countdown timers; tap one to keep it alive. Unloved vibes fade and die. One instrument, played by everyone.

## Run it

Requires an **Apple Silicon Mac**, plus [`uv`](https://docs.astral.sh/uv/) and [Node.js](https://nodejs.org).

```bash
./install.sh   # venv + Python deps + UI build + model download (~once)
```

```bash
./run.sh       # open http://localhost:8000 on the projector
```

Click **Start · Open the Room** to open a public Cloudflare tunnel — the QR code updates to a URL phones anywhere can scan. Press **`O`** on the board for the operator panel (every tuning knob as a live slider). Flags: `--no-audio`, `--host`, `--port`.

## How it works

```
 phones ──POST /api/prompt──▶  MusicCoCa embed ──▶  Mixer (time-weighted blend)
                                                         │ live style embedding
 board ◀──WS /ws/board──  FastAPI  ◀── ring buffer ◀──  Engine (MRT2 streaming)
                                                         │
                                                      speakers
```

- **`server/mixer.py`** — the instrument. Each unique vibe is one entry (deduped, capped at weight 1) with a vote-reset countdown and smooth fade in/out. `current_blend()` is the weighted-average embedding of the freshest active vibes; an anchor prompt fills silence.
- **`server/engine.py`** — one worker thread loads `mrt2_small` (230M) and loops: read blend → `generate()` → push audio to the speakers.
- **`server/app.py`** — FastAPI: prompt submission, board websocket, params, QR, static UI.
- **`server/moderation.py`** — profanity filter so nothing offensive hits the projector.
- **`ui/`** — Vite + React board (projector) and phone view.

`mrt2_small` runs faster than real-time on any M-series Mac. For the 2.4B `mrt2_base` (needs a Pro/Max chip), change `size=` in `server/engine.py`.

## Develop

```bash
npm --prefix ui run dev                 # Vite dev server on :5173, proxies to :8000
.venv/bin/python -m pytest tests        # mixer unit tests
.venv/bin/python -m server._smoke       # offline morph test -> /tmp/hive_morph.wav
```

Built on [Magenta RealTime 2](https://github.com/magenta/magenta-realtime) by Google DeepMind. Apache-2.0.
