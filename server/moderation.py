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

"""Content moderation for crowd-submitted prompts.

A live, public, projector-facing demo must never display slurs or hate speech.
This is a deliberately conservative substring filter with light obfuscation
normalization (leetspeak, repeated chars, stripped separators). It is a hook:
swap in a classifier later without touching callers.

``check(text)`` returns ``(allowed, reason)``.
"""

import re
from typing import Optional

# Core blocklist: slurs and hate terms that must never appear on stage, plus a
# little strong profanity. Kept compact; extend via add_terms() or a file.
_BLOCKED = {
    # racial / ethnic slurs
    "nigger", "nigga", "n1gger", "chink", "spic", "kike", "gook", "wetback",
    "coon", "raghead", "beaner", "paki", "sandnigger",
    # homophobic / transphobic slurs
    "faggot", "fag", "dyke", "tranny",
    # ableist slur
    "retard",
    # strong sexual profanity (keep the screen classy)
    "cunt", "rape", "rapist",
}

# Map common leetspeak substitutions back to letters before matching.
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s"})


def _normalize(text: str) -> str:
    t = text.lower().translate(_LEET)
    t = re.sub(r"[^a-z]", "", t)          # drop spaces/punct so "n i g g a" collapses
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)   # collapse 3+ repeats (niiiigga -> niigga)
    return t


# Precompute normalized blocked forms for substring search.
_BLOCKED_NORM = {_normalize(w) for w in _BLOCKED}


def add_terms(*terms: str) -> None:
    for t in terms:
        n = _normalize(t)
        if n:
            _BLOCKED_NORM.add(n)


def check(text: str) -> tuple[bool, Optional[str]]:
    """Return (allowed, reason). reason is a user-facing message when blocked."""
    if not text or not text.strip():
        return False, "Say something!"
    if len(text) > 80:
        return False, "Keep it under 80 characters."
    norm = _normalize(text)
    for bad in _BLOCKED_NORM:
        if bad and bad in norm:
            return False, "That word isn't welcome here. Try a music vibe instead."
    return True, None
