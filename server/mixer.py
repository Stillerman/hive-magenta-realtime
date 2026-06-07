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

"""The crowd mixer — vote-to-survive blending of everyone's prompts.

Each *unique* vibe is one entry, capped at weight 1 (no stacking ten flamencos).
Every entry has a countdown timer (``timeout_s``); when it runs out the vibe
fades and dies, letting the song evolve. Anyone can "vote" for a vibe — tap it
on their phone, or re-type it — which resets its timer to full. The anchor only
fills the room when the crowd goes silent.

The engine reads ``current_blend()`` before each generation chunk.
"""

import dataclasses
import itertools
import re
import threading
import time
from typing import Callable, Optional

import numpy as np

from .params import InstrumentParams, NORM_SUM, NORM_UNIT

_id_counter = itertools.count(1)


def normalize_key(text: str) -> str:
    """Dedup key: lowercase, alphanumerics only — collapses 'Flamenco!' == 'flamenco'."""
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclasses.dataclass
class Contribution:
    """One unique vibe and its life in the mix."""

    id: int
    text: str
    key: str
    embedding: np.ndarray  # (768,)
    t_start: float         # first appearance (drives fade-in)
    expires_at: float      # death time; a vote pushes this forward
    client_id: str
    votes: int = 1


@dataclasses.dataclass
class ActivePrompt:
    """A snapshot of a live vibe for the board / phone UI."""

    id: int
    text: str
    client_id: str
    weight: float
    remaining: float   # seconds of life left
    timeout: float     # full life span (for the countdown bar)
    life_frac: float   # remaining / timeout, clamped to [0, 1]
    votes: int


class Mixer:
    """Thread-safe blend of voted crowd vibes, with anchor as silence fallback."""

    def __init__(
        self,
        embed_fn: Callable[[str], np.ndarray],
        params: InstrumentParams,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._embed = embed_fn
        self.params = params
        self._clock = clock
        self._lock = threading.RLock()
        self._embed_lock = threading.Lock()  # serialize TFLite (not concurrency-safe)
        self._contribs: list[Contribution] = []
        self._by_key: dict[str, Contribution] = {}
        self._cache: dict[str, np.ndarray] = {}
        self._anchor_text: Optional[str] = None
        self._anchor_embed: Optional[np.ndarray] = None
        self.set_anchor(params.base_prompt)

    # --- embedding cache -----------------------------------------------------

    def _embed_cached(self, text: str) -> np.ndarray:
        key = normalize_key(text)
        emb = self._cache.get(key)
        if emb is not None:
            return emb
        # Embedding (TFLite) is ~350ms and not thread-safe; serialize it.
        with self._embed_lock:
            emb = self._cache.get(key)  # another thread may have filled it
            if emb is None:
                emb = np.asarray(self._embed(text), dtype=np.float32).reshape(-1)
                self._cache[key] = emb
        return emb

    def prewarm(self, texts: list[str]) -> None:
        """Pre-embed a vocabulary so common vibes (and the smoke test) are instant."""
        for t in texts:
            if t.strip():
                self._embed_cached(t)

    # --- mutation ------------------------------------------------------------

    def set_anchor(self, text: str) -> None:
        with self._lock:
            self._anchor_text = text
            self._anchor_embed = self._embed_cached(text) if text.strip() else None

    def add(self, text: str, client_id: str = "anon") -> Contribution:
        """Add a new vibe, or — if it already exists — vote for it (reset timer)."""
        key = normalize_key(text)
        now = self._clock()
        with self._lock:
            existing = self._by_key.get(key)
            if existing is not None and existing.expires_at > now:
                existing.expires_at = now + self.params.timeout_s
                existing.votes += 1
                return existing
        # Embed outside the fast path's existence check (cached after first time).
        emb = self._embed_cached(text)
        with self._lock:
            existing = self._by_key.get(key)  # re-check after embedding
            if existing is not None and existing.expires_at > now:
                existing.expires_at = now + self.params.timeout_s
                existing.votes += 1
                return existing
            contrib = Contribution(
                id=next(_id_counter), text=text, key=key, embedding=emb,
                t_start=now, expires_at=now + self.params.timeout_s,
                client_id=client_id,
            )
            self._contribs.append(contrib)
            self._by_key[key] = contrib
            return contrib

    def vote(self, contrib_id: int) -> bool:
        """Reset a vibe's countdown by id (a tap on the phone). Returns success."""
        now = self._clock()
        with self._lock:
            for c in self._contribs:
                if c.id == contrib_id and c.expires_at > now:
                    c.expires_at = now + self.params.timeout_s
                    c.votes += 1
                    return True
        return False

    def clear(self) -> None:
        with self._lock:
            self._contribs.clear()
            self._by_key.clear()

    def remove_client(self, client_id: str) -> None:
        with self._lock:
            self._contribs = [c for c in self._contribs if c.client_id != client_id]
            self._by_key = {c.key: c for c in self._contribs}

    # --- envelope ------------------------------------------------------------

    def _weight(self, c: Contribution, now: float) -> float:
        """Fade in after birth, hold at 1, fade out over the final ramp_out_s."""
        p = self.params
        remaining = c.expires_at - now
        if remaining <= 0:
            return 0.0
        age = now - c.t_start
        fade_in = min(1.0, age / max(p.ramp_in_s, 1e-6))
        fade_out = min(1.0, remaining / max(p.ramp_out_s, 1e-6))
        return min(fade_in, fade_out)

    # --- query ---------------------------------------------------------------

    def _active(self, now: float) -> list[tuple[Contribution, float]]:
        """Return (contrib, weight) for live vibes; prune dead ones."""
        alive: list[tuple[Contribution, float]] = []
        survivors: list[Contribution] = []
        for c in self._contribs:
            if c.expires_at > now:
                alive.append((c, self._weight(c, now)))
                survivors.append(c)
        if len(survivors) != len(self._contribs):
            self._contribs = survivors
            self._by_key = {c.key: c for c in survivors}
        return alive

    def _build_crowd(self, now: float) -> list[tuple[Contribution, float]]:
        """Live vibes with final weights, capped to the freshest ``max_prompts``."""
        p = self.params
        crowd = [
            (c, min(w * p.crowd_gain, p.per_prompt_cap))
            for c, w in self._active(now)
        ]
        if p.max_prompts > 0 and len(crowd) > p.max_prompts:
            # Keep the ones with the most life left; the rest were dying anyway.
            crowd.sort(key=lambda cw: cw[0].expires_at, reverse=True)
            crowd = crowd[: p.max_prompts]
        return crowd

    def _snapshot(self, crowd: list[tuple[Contribution, float]], now: float) -> list[ActivePrompt]:
        timeout = max(self.params.timeout_s, 1e-6)
        snap = [
            ActivePrompt(
                id=c.id, text=c.text, client_id=c.client_id, weight=float(w),
                remaining=float(c.expires_at - now), timeout=float(self.params.timeout_s),
                life_frac=max(0.0, min(1.0, (c.expires_at - now) / timeout)),
                votes=c.votes,
            )
            for c, w in crowd
        ]
        snap.sort(key=lambda a: a.weight, reverse=True)
        return snap

    def ui_snapshot(self) -> tuple[list[ActivePrompt], dict]:
        """Lightweight board/phone update: active vibes + stats, no embedding math."""
        now = self._clock()
        with self._lock:
            crowd = self._build_crowd(now)
            snap = self._snapshot(crowd, now)
            clients = {c.client_id for c, _ in crowd}
            stats = {
                "active_count": len(crowd),
                "unique_clients": len(clients),
                "anchor": self._anchor_text,
            }
        return snap, stats

    def current_blend(self) -> tuple[Optional[np.ndarray], list[ActivePrompt]]:
        """Compute the live style embedding and the active-vibe snapshot.

        Returns (embedding | None, active_prompts). ``None`` means fully masked
        (no anchor, no crowd) — the engine should generate unconditionally.
        """
        p = self.params
        now = self._clock()
        with self._lock:
            crowd = self._build_crowd(now)
            pairs: list[tuple[np.ndarray, float]] = []
            if not crowd and self._anchor_embed is not None and p.anchor_weight > 0:
                pairs.append((self._anchor_embed, p.anchor_weight))
            for c, w in crowd:
                if w > 0:
                    pairs.append((c.embedding, w))

            snapshot = self._snapshot(crowd, now)

        if not pairs:
            return None, snapshot

        embs = np.stack([e for e, _ in pairs])
        weights = np.asarray([w for _, w in pairs], dtype=np.float32)

        blended = (embs * weights[:, None]).sum(axis=0)
        total = float(weights.sum())
        if p.normalize_mode == NORM_SUM:
            pass  # raw weighted sum
        elif p.normalize_mode == NORM_UNIT:
            norm = float(np.linalg.norm(blended))
            blended = blended / norm if norm > 0 else blended
        else:  # NORM_AVERAGE (default)
            blended = blended / total if total > 0 else blended

        return blended.astype(np.float32), snapshot
