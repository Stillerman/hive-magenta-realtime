import numpy as np

from server.mixer import Mixer
from server.params import InstrumentParams, MIX_ANCHOR_CROWD


def test_anchor_is_silence_fallback_even_with_legacy_anchor_crowd_mode():
    vectors = {
        "anchor": np.array([1.0, 0.0], dtype=np.float32),
        "crowd": np.array([0.0, 1.0], dtype=np.float32),
    }
    now = [0.0]
    params = InstrumentParams(
        base_prompt="anchor",
        mix_mode=MIX_ANCHOR_CROWD,
        ramp_in_s=0.0,
        ramp_out_s=1.0,
        timeout_s=10.0,
    )
    mixer = Mixer(embed_fn=lambda text: vectors[text], params=params, clock=lambda: now[0])

    anchor_blend, anchor_snapshot = mixer.current_blend()
    assert np.allclose(anchor_blend, vectors["anchor"])
    assert anchor_snapshot == []

    mixer.add("crowd", "client")
    now[0] = 0.01
    crowd_blend, crowd_snapshot = mixer.current_blend()

    assert np.allclose(crowd_blend, vectors["crowd"])
    assert [p.text for p in crowd_snapshot] == ["crowd"]
