# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""FastAPI server: the board, the phone, and the bridge to the audio engine."""

import asyncio
import contextlib
import logging
import pathlib
import socket
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import moderation
from .engine import Engine
from .params import InstrumentParams
from .tunnel import Tunnel

logger = logging.getLogger("hive.app")

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
UI_DIST = ROOT / "ui" / "dist"
STATIC = ROOT / "static"
PARTICIPANT_WINDOW = 30.0  # seconds a phone counts as "present" after last contact


class Hub:
    """Holds all shared runtime state (engine, tunnel, params, participants)."""

    def __init__(self, port: int):
        self.port = port
        self.params = InstrumentParams()
        self.engine = Engine(self.params)
        self.tunnel = Tunnel(port)
        self.seen: dict[str, float] = {}     # client_id -> last contact (monotonic)
        self.banned: set[str] = set()

    # --- participants --------------------------------------------------------

    def touch(self, client_id: str) -> None:
        if client_id:
            self.seen[client_id] = time.monotonic()

    def participant_count(self) -> int:
        now = time.monotonic()
        return sum(1 for t in self.seen.values() if now - t < PARTICIPANT_WINDOW)

    # --- URLs ----------------------------------------------------------------

    def lan_url(self) -> str:
        return f"http://{_lan_ip()}:{self.port}/join"

    def join_url(self) -> str:
        return (self.tunnel.url + "/join") if self.tunnel.url else self.lan_url()

    # --- state snapshot ------------------------------------------------------

    def state(self) -> dict:
        active, stats = (self.engine.mixer.ui_snapshot()
                         if self.engine.mixer else ([], {}))
        return {
            "running": self.engine.running,
            "tunnel_open": self.tunnel.url is not None,
            "join_url": self.join_url(),
            "lan_url": self.lan_url(),
            "participants": self.participant_count(),
            "level": round(self.engine.level, 4),
            "steps_per_s": round(self.engine.steps_per_s, 1),
            "anchor": stats.get("anchor"),
            "active": [
                {"id": a.id, "text": a.text, "weight": round(a.weight, 3),
                 "remaining": round(a.remaining, 2), "timeout": round(a.timeout, 2),
                 "life_frac": round(a.life_frac, 3), "votes": a.votes,
                 "client_id": a.client_id}
                for a in active
            ],
            "params": self.params.to_dict(),
        }


def _lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def print_terminal_qr(url: str) -> None:
    """Print a scannable ASCII QR of the join URL to the terminal."""
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        print(f"\n  Scan to join: {url}\n", flush=True)
        qr.print_ascii(invert=True)
        print(flush=True)
    except Exception:
        logger.warning("Could not render terminal QR for %s", url)


# Fixed smoke-test / suggestion vocabulary. Pre-warmed at startup so the smoke
# button and common vibes are instant (each unique embed is ~350ms otherwise).
SMOKE_VOCAB = [
    "reggae", "deep house", "techno", "trap", "jazz", "ambient", "drum and bass",
    "gospel choir", "disco", "funk", "heavy metal", "flamenco", "synthwave", "dub",
    "afrobeat", "bossa nova", "gregorian chant", "drill", "bluegrass", "opera",
    "lo-fi hip hop", "psytrance", "salsa", "k-pop", "country", "punk rock", "soul",
    "sub bass", "808 bass", "church organ", "saxophone", "sitar", "steel drums",
    "distorted guitar", "marimba", "violin", "synth pads", "kick drum", "tabla",
    "dark techno", "dreamy ambient", "aggressive metal", "lush strings", "gritty funk",
    "icy synths", "hypnotic groove", "epic orchestra", "minimal house", "warm rhodes",
    "banjo", "didgeridoo", "vaporwave", "phonk", "cumbia", "bhangra", "ska",
    "trip hop", "hardstyle", "shoegaze", "math rock", "doom metal", "chiptune", "grime",
]


def seed_smoke_prompts(hub: "Hub", n: int) -> None:
    """Inject n prompts from random fake users — stress test / live demo seed."""
    import random
    for _ in range(n):
        text = random.choice(SMOKE_VOCAB)
        cid = f"smoke{random.randint(0, 250)}"
        hub.touch(cid)
        hub.engine.mixer.add(text, client_id=cid)


def create_app(port: int = 8000, autostart_audio: bool = True,
               open_tunnel_on_boot: bool = True) -> FastAPI:
    hub = Hub(port)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI):
        # Load the model and start the baseline music immediately.
        await asyncio.to_thread(hub.engine.load)
        if autostart_audio:
            hub.engine.start()
        # Warm the common-vibe cache in the background so the smoke test and
        # popular prompts don't pay the ~350ms embed cost live.
        asyncio.create_task(asyncio.to_thread(hub.engine.mixer.prewarm, SMOKE_VOCAB))
        # Open the public room on boot and print the join QR to the terminal.
        if open_tunnel_on_boot:
            async def _boot_tunnel():
                await asyncio.to_thread(hub.tunnel.start)
                print_terminal_qr(hub.join_url())
            asyncio.create_task(_boot_tunnel())
        yield
        hub.engine.close()
        hub.tunnel.stop()

    app = FastAPI(title="Hive", lifespan=lifespan)
    app.state.hub = hub

    # --- REST ----------------------------------------------------------------

    @app.post("/api/prompt")
    async def submit_prompt(payload: dict):
        text = (payload.get("text") or "").strip()
        client_id = payload.get("client_id") or "anon"
        hub.touch(client_id)
        if client_id in hub.banned:
            return JSONResponse({"ok": False, "message": "You've been muted."}, status_code=403)
        if hub.params.profanity_filter:
            allowed, reason = moderation.check(text)
        else:
            allowed, reason = (bool(text) and len(text) <= 80), "Say something (<=80 chars)."
        if not allowed:
            return JSONResponse({"ok": False, "message": reason}, status_code=400)
        # Embedding is ~350ms and not thread-safe; run it off the event loop.
        contrib = await asyncio.to_thread(hub.engine.mixer.add, text, client_id)
        return {"ok": True, "id": contrib.id}

    @app.post("/api/vote")
    async def vote(payload: dict):
        hub.touch(payload.get("client_id") or "anon")
        ok = hub.engine.mixer.vote(int(payload.get("id", -1)))
        return {"ok": ok}

    @app.post("/api/heartbeat")
    async def heartbeat(payload: dict):
        hub.touch(payload.get("client_id") or "anon")
        return {"ok": True, "running": hub.engine.running,
                "tunnel_open": hub.tunnel.url is not None,
                "participants": hub.participant_count()}

    @app.get("/api/state")
    async def get_state():
        return hub.state()

    @app.get("/api/qr.png")
    async def qr_png(data: Optional[str] = None):
        import io
        import qrcode
        from fastapi.responses import Response
        img = qrcode.make(data or hub.join_url())
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(buf.getvalue(), media_type="image/png",
                        headers={"Cache-Control": "no-store"})

    @app.get("/api/params")
    async def get_params():
        return hub.params.to_dict()

    @app.post("/api/params")
    async def set_params(payload: dict):
        old_anchor = hub.params.base_prompt
        hub.params.update(payload)
        if hub.params.base_prompt != old_anchor and hub.engine.mixer:
            await asyncio.to_thread(hub.engine.mixer.set_anchor, hub.params.base_prompt)
        return hub.params.to_dict()

    @app.post("/api/control")
    async def control(payload: dict):
        action = payload.get("action")
        if action == "open_tunnel":
            url = await asyncio.to_thread(hub.tunnel.start)
            print_terminal_qr(hub.join_url())
            return {"ok": True, "join_url": hub.join_url(), "tunnel_open": url is not None}
        if action == "smoke":
            n = int(payload.get("n", 300))
            await asyncio.to_thread(seed_smoke_prompts, hub, n)
            return {"ok": True, "added": n}
        if action == "close_tunnel":
            hub.tunnel.stop()
            return {"ok": True}
        if action == "start_audio":
            hub.engine.start()
            return {"ok": True}
        if action == "stop_audio":
            hub.engine.stop()
            return {"ok": True}
        if action == "clear":
            hub.engine.mixer.clear()
            return {"ok": True}
        if action == "set_anchor":
            text = (payload.get("text") or "").strip()
            hub.params.base_prompt = text
            hub.engine.mixer.set_anchor(text)
            return {"ok": True}
        if action == "kick":
            cid = payload.get("client_id")
            if cid:
                hub.banned.add(cid)
                hub.engine.mixer.remove_client(cid)
            return {"ok": True}
        return JSONResponse({"ok": False, "message": f"unknown action {action!r}"}, status_code=400)

    # --- WebSocket: live board feed -----------------------------------------

    @app.websocket("/ws/board")
    async def ws_board(ws: WebSocket):
        await ws.accept()
        try:
            while True:
                await ws.send_json(hub.state())
                await asyncio.sleep(0.1)
        except WebSocketDisconnect:
            pass
        except Exception:
            logger.exception("board websocket error")

    # --- Static / SPA --------------------------------------------------------

    if UI_DIST.exists():
        app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    def _page(board: bool):
        if UI_DIST.exists():
            return FileResponse(UI_DIST / "index.html")
        name = "board.html" if board else "phone.html"
        return FileResponse(STATIC / name)

    @app.get("/")
    async def board_page():
        return _page(board=True)

    @app.get("/join")
    async def phone_page():
        return _page(board=False)

    return app
