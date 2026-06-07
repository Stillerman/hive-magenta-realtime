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

"""The audio engine: streams MRT2 chunks shaped by the live crowd blend.

A generation thread loops forever, asking the :class:`Mixer` for the current
blended style embedding before each chunk, generating ``chunk_frames`` of audio,
and pushing it into a sample FIFO. A separate realtime audio callback drains the
FIFO to the speakers. The two are decoupled so a briefly-slow chunk never
glitches playback (as long as the lookahead buffer holds).
"""

import collections
import logging
import threading
import time
from typing import Optional

import numpy as np

from .mixer import Mixer
from .params import InstrumentParams

logger = logging.getLogger("hive.engine")

SAMPLE_RATE = 48_000
CHANNELS = 2


class AudioFifo:
    """Thread-safe stereo sample FIFO (float32, shape [N, 2])."""

    def __init__(self):
        self._chunks: collections.deque[np.ndarray] = collections.deque()
        self._lock = threading.Lock()
        self._available = 0  # frames

    def push(self, samples: np.ndarray) -> None:
        with self._lock:
            self._chunks.append(samples)
            self._available += len(samples)

    def available_seconds(self) -> float:
        with self._lock:
            return self._available / SAMPLE_RATE

    def clear(self) -> None:
        with self._lock:
            self._chunks.clear()
            self._available = 0

    def pull(self, n: int) -> np.ndarray:
        """Return exactly ``n`` frames, zero-padding on underrun."""
        out = np.zeros((n, CHANNELS), dtype=np.float32)
        filled = 0
        with self._lock:
            while filled < n and self._chunks:
                head = self._chunks[0]
                take = min(len(head), n - filled)
                out[filled:filled + take] = head[:take]
                filled += take
                if take == len(head):
                    self._chunks.popleft()
                else:
                    self._chunks[0] = head[take:]
                self._available -= take
        return out


class Engine:
    """Owns the model, the mixer, the generation thread, and audio output."""

    def __init__(self, params: InstrumentParams, size: str = "mrt2_small"):
        self.params = params
        self._size = size
        self.mrt = None
        self.mixer: Optional[Mixer] = None
        self._fifo = AudioFifo()
        self._worker: Optional[threading.Thread] = None
        self._running = threading.Event()   # whether to actively generate
        self._shutdown = threading.Event()  # final teardown of the worker
        self._state = None
        self.level = 0.0          # output RMS for the meter (0..1)
        self.steps_per_s = 0.0    # last measured generation speed
        self._stream = None
        self._loaded = threading.Event()

    # --- lifecycle -----------------------------------------------------------

    def load(self, timeout: float = 120.0) -> None:
        """Start the worker thread; it loads the model and then idles.

        The model MUST be built and run on a single thread: MLX GPU streams are
        thread-local, so loading on one thread and generating on another raises
        "There is no Stream(gpu, ...) in current thread". The worker owns both.
        """
        if self._worker is not None:
            return
        self._worker = threading.Thread(target=self._worker_main, daemon=True)
        self._worker.start()
        if not self._loaded.wait(timeout=timeout):
            raise RuntimeError("Model failed to load within timeout.")

    def _embed(self, text: str) -> np.ndarray:
        return np.asarray(self.mrt.embed_style(text), dtype=np.float32).reshape(-1)

    def start(self) -> None:
        if not self._loaded.is_set():
            raise RuntimeError("Engine.load() must finish before start().")
        if self._running.is_set():
            return
        self._open_stream()
        self._running.set()
        logger.info("Engine started.")

    def stop(self) -> None:
        """Pause generation and release the audio device (worker stays alive)."""
        self._running.clear()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        self._fifo.clear()
        self._state = None
        self.level = 0.0
        self.steps_per_s = 0.0
        logger.info("Engine paused.")

    def close(self) -> None:
        """Final teardown: stop the worker thread."""
        self.stop()
        self._shutdown.set()
        if self._worker:
            self._worker.join(timeout=5)
            self._worker = None

    @property
    def running(self) -> bool:
        return self._running.is_set()

    # --- audio output --------------------------------------------------------

    def _open_stream(self) -> None:
        try:
            import sounddevice as sd
        except Exception:
            logger.warning("sounddevice unavailable; running without local playback.")
            self._stream = None
            return

        def callback(outdata, frames, _time, status):
            if status:
                logger.debug("sounddevice status: %s", status)
            block = self._fifo.pull(frames) * float(self.params.master_gain)
            np.clip(block, -1.0, 1.0, out=block)
            outdata[:] = block
            # Cheap level meter (RMS of left+right).
            self.level = float(np.sqrt(np.mean(block ** 2))) if frames else 0.0

        try:
            self._stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                blocksize=0,
                callback=callback,
            )
            self._stream.start()
        except Exception:
            logger.warning("Could not open audio output device; no local playback.")
            self._stream = None

    # --- worker (load + generation, single thread) ---------------------------

    def _worker_main(self) -> None:
        from magenta_rt import MagentaRT2Mlxfn

        logger.info("Loading MRT2 model %s ...", self._size)
        self.mrt = MagentaRT2Mlxfn(
            size=self._size,
            temperature=self.params.temperature,
            top_k=self.params.top_k,
            cfg_musiccoca=self.params.cfg_musiccoca,
            cfg_drums=self.params.cfg_drums,
        )
        self.mixer = Mixer(embed_fn=self._embed, params=self.params)
        self._loaded.set()
        logger.info("Model loaded; anchor = %r", self.params.base_prompt)

        while not self._shutdown.is_set():
            if not self._running.is_set():
                time.sleep(0.05)
                continue
            # Throttle to the lookahead cap so we generate roughly at real-time.
            if self._fifo.available_seconds() >= self.params.max_buffer_s:
                time.sleep(0.01)
                continue

            embedding, _ = self.mixer.current_blend()
            drums = [1] if self.params.drums_on else None

            t0 = time.time()
            frames = max(1, int(self.params.chunk_frames))
            try:
                wav, self._state = self.mrt.generate(
                    style=embedding,
                    drums=drums,
                    cfg_musiccoca=self.params.cfg_musiccoca,
                    cfg_drums=self.params.cfg_drums,
                    temperature=self.params.temperature,
                    top_k=self.params.top_k,
                    frames=frames,
                    state=self._state,
                )
            except Exception:  # keep the show going on a transient error
                logger.exception("generation chunk failed")
                time.sleep(0.05)
                continue

            elapsed = time.time() - t0
            if elapsed > 0:
                self.steps_per_s = frames / elapsed
            self._fifo.push(np.ascontiguousarray(wav.samples, dtype=np.float32))
