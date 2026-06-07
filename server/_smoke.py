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

"""Phase-1 smoke test: prove the mixer blend morphs the generated audio.

Generates anchor-only audio, then injects a contrasting crowd prompt and lets it
ramp in / hold / ramp out, writing one continuous WAV so the morph is audible.
No audio device required (writes a file). Run from the repo root:

    .venv/bin/python -m server._smoke
"""

import logging
import time

import numpy as np

from magenta_rt import audio

from server.engine import SAMPLE_RATE
from server.mixer import Mixer
from server.params import InstrumentParams

logging.basicConfig(level=logging.INFO, force=True)


def main():
    from magenta_rt import MagentaRT2Mlxfn

    params = InstrumentParams(
        base_prompt="lone gentle grand piano, sparse",
        ramp_in_s=2.0, hold_s=2.0, ramp_out_s=2.0, chunk_frames=25,
    )
    mrt = MagentaRT2Mlxfn(size="mrt2_small", temperature=params.temperature,
                          top_k=params.top_k, cfg_musiccoca=params.cfg_musiccoca)

    # Drive the mixer with a virtual clock so the test is deterministic and fast:
    # each generated second advances the clock by exactly one second.
    clock = {"t": 0.0}
    mixer = Mixer(embed_fn=lambda s: np.asarray(mrt.embed_style(s), np.float32).reshape(-1),
                  params=params, clock=lambda: clock["t"])

    timeline = []  # (second, event)
    timeline_at = {3: ("add", "loud aggressive heavy metal distorted electric guitar")}

    state = None
    chunks = []
    total_seconds = 9
    gen_t0 = time.time()
    for sec in range(total_seconds):
        if sec in timeline_at and timeline_at[sec][0] == "add":
            mixer.add(timeline_at[sec][1], client_id="tester")
            print(f"[t={sec}s] crowd prompt added: {timeline_at[sec][1]!r}")

        emb, snap = mixer.current_blend()
        weights = ", ".join(f"{a.text[:14]}={a.weight:.2f}" for a in snap) or "(anchor only)"
        print(f"[t={sec}s] blend -> {weights}")

        wav, state = mrt.generate(style=emb, frames=params.chunk_frames, state=state)
        chunks.append(wav.samples)
        clock["t"] += 1.0  # advance virtual clock by the generated duration

    gen_elapsed = time.time() - gen_t0
    audio_seconds = total_seconds
    print(f"\nGenerated {audio_seconds}s of audio in {gen_elapsed:.1f}s "
          f"({audio_seconds / gen_elapsed:.2f}x real-time).")
    assert gen_elapsed < audio_seconds, "NOT real-time on this machine!"

    out = np.concatenate(chunks, axis=0)
    path = "/tmp/hive_morph.wav"
    audio.Waveform(out, SAMPLE_RATE).write(path)
    print(f"Wrote morph to {path}  (anchor piano -> metal -> back to piano)")


if __name__ == "__main__":
    main()
