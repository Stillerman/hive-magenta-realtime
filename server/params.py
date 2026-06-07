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

"""All live-tunable parameters for the Hive crowd instrument.

Every knob that shapes the sound or the crowd-mixing behaviour lives here. The
operator panel reads/writes these at runtime — "tuning the instrument."
"""

import dataclasses
from typing import Any


# Mix modes are retained for old clients; the mixer treats anchor as a silence
# fallback and never blends it over an active crowd.
MIX_ANCHOR_CROWD = "anchor_crowd"
MIX_PURE_CROWD = "pure_crowd"
MIX_MODES = (MIX_ANCHOR_CROWD, MIX_PURE_CROWD)

# Embedding normalization of the final blend.
NORM_AVERAGE = "average"   # weighted average (divide by total weight)
NORM_SUM = "sum"           # raw weighted sum (magnitude grows with crowd)
NORM_UNIT = "unit"         # weighted sum, then renormalized to unit length


@dataclasses.dataclass
class InstrumentParams:
    """The full tuning surface. All fields are hot-swappable at runtime."""

    # --- The anchor (persistent base prompt the operator seeds) ---
    base_prompt: str = "slow meditative ambient with deep sub bass and soft mallet percussion"
    anchor_weight: float = 1.0           # weight of the anchor in the blend

    # --- Per-prompt life (vote-to-survive timeout model) ---
    ramp_in_s: float = 1.5               # quick fade-in when a vibe first appears
    timeout_s: float = 20.0              # life without votes; a tap resets it to full
    ramp_out_s: float = 4.0              # fade-out over the final seconds before timeout

    # --- Crowd mixing ---
    mix_mode: str = MIX_PURE_CROWD       # legacy; anchor always fills only silence
    max_prompts: int = 100               # global cap; drop the ones nearest to timeout
    per_prompt_cap: float = 1.0          # each unique vibe maxes at 1 (no stacking)
    crowd_gain: float = 1.0              # global multiplier on crowd weights
    normalize_mode: str = NORM_AVERAGE

    # --- Model / sampling ---
    chunk_frames: int = 13               # frames per blend update (~0.5s; smoother morph)
    temperature: float = 1.1
    top_k: int = 50
    cfg_musiccoca: float = 1.6           # style strength
    cfg_drums: float = 4.0
    drums_on: bool = False               # add a steady drum conditioning track

    # --- Output / playback ---
    master_gain: float = 0.9
    max_buffer_s: float = 1.0            # generation lookahead cap (latency vs safety)

    # --- Moderation ---
    profanity_filter: bool = True

    def update(self, data: dict[str, Any]) -> None:
        """Apply a partial dict of updates, ignoring unknown keys, coercing types."""
        fields = {f.name: f.type for f in dataclasses.fields(self)}
        for key, value in data.items():
            if key not in fields:
                continue
            current = getattr(self, key)
            try:
                if isinstance(current, bool):
                    value = bool(value)
                elif isinstance(current, int):
                    value = int(value)
                elif isinstance(current, float):
                    value = float(value)
                elif isinstance(current, str):
                    value = str(value)
            except (TypeError, ValueError):
                continue
            setattr(self, key, value)

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)
