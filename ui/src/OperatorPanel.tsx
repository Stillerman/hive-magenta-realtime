// Copyright 2026 Google LLC. Apache-2.0.
import { useState } from "react";
import { api } from "./api";
import type { BoardState, Params } from "./types";

interface SliderDef {
  key: keyof Params;
  label: string;
  min: number;
  max: number;
  step: number;
}

const ENVELOPE: SliderDef[] = [
  { key: "timeout_s", label: "Timeout (s)", min: 3, max: 60, step: 1 },
  { key: "ramp_in_s", label: "Fade in (s)", min: 0, max: 10, step: 0.1 },
  { key: "ramp_out_s", label: "Fade out (s)", min: 0, max: 15, step: 0.1 },
];

const MIX: SliderDef[] = [
  { key: "anchor_weight", label: "Anchor weight", min: 0, max: 5, step: 0.05 },
  { key: "crowd_gain", label: "Crowd gain", min: 0, max: 4, step: 0.05 },
  { key: "per_prompt_cap", label: "Per-prompt cap", min: 0, max: 3, step: 0.05 },
  { key: "max_prompts", label: "Max live prompts", min: 1, max: 100, step: 1 },
];

const SOUND: SliderDef[] = [
  { key: "cfg_musiccoca", label: "Style strength", min: 0, max: 5, step: 0.1 },
  { key: "temperature", label: "Temperature", min: 0.1, max: 2, step: 0.05 },
  { key: "top_k", label: "Top-k", min: 1, max: 200, step: 1 },
  { key: "chunk_frames", label: "Chunk frames (latency)", min: 5, max: 50, step: 1 },
  { key: "master_gain", label: "Master gain", min: 0, max: 1.5, step: 0.01 },
  { key: "max_buffer_s", label: "Buffer lookahead (s)", min: 1, max: 8, step: 0.5 },
];

export function OperatorPanel({ state, onClose }: { state: BoardState; onClose: () => void }) {
  const p = state.params;
  const [anchorText, setAnchorText] = useState(p.base_prompt);

  const set = (key: keyof Params, value: number | string | boolean) =>
    api.setParams({ [key]: value } as Partial<Params>);

  const Sliders = ({ defs }: { defs: SliderDef[] }) => (
    <>
      {defs.map((d) => (
        <label className="op-row" key={d.key as string}>
          <span>{d.label}</span>
          <input
            type="range"
            min={d.min}
            max={d.max}
            step={d.step}
            defaultValue={p[d.key] as number}
            onChange={(e) => set(d.key, Number(e.target.value))}
          />
          <span className="op-val">{(p[d.key] as number)}</span>
        </label>
      ))}
    </>
  );

  return (
    <div className="op-panel">
      <div className="op-head">
        <strong>Operator · tune the instrument</strong>
        <button onClick={onClose}>✕</button>
      </div>

      <div className="op-section">
        <div className="op-title">Anchor</div>
        <div className="op-anchor">
          <input
            value={anchorText}
            onChange={(e) => setAnchorText(e.target.value)}
            placeholder="base prompt…"
          />
          <button onClick={() => api.control("set_anchor", { text: anchorText })}>Set</button>
        </div>
      </div>

      <div className="op-section">
        <div className="op-title">Blend</div>
        <div className="op-note">Anchor fills silence only.</div>
        <div className="op-modes">
          {["average", "sum", "unit"].map((m) => (
            <button
              key={m}
              className={p.normalize_mode === m ? "active" : ""}
              onClick={() => set("normalize_mode", m)}
            >
              norm: {m}
            </button>
          ))}
        </div>
      </div>

      <div className="op-section"><div className="op-title">Envelope</div><Sliders defs={ENVELOPE} /></div>
      <div className="op-section"><div className="op-title">Crowd mix</div><Sliders defs={MIX} /></div>
      <div className="op-section"><div className="op-title">Sound</div><Sliders defs={SOUND} /></div>

      <div className="op-section">
        <div className="op-title">Toggles</div>
        <label className="op-toggle">
          <input type="checkbox" defaultChecked={p.drums_on} onChange={(e) => set("drums_on", e.target.checked)} />
          Drums conditioning
        </label>
        <label className="op-toggle">
          <input type="checkbox" defaultChecked={p.profanity_filter} onChange={(e) => set("profanity_filter", e.target.checked)} />
          Profanity filter
        </label>
      </div>

      <div className="op-section">
        <div className="op-title">Crowd control</div>
        <div className="op-controls">
          <button onClick={() => api.control("smoke", { n: 300 })}>Smoke test (300)</button>
          <button onClick={() => api.control("clear")}>Clear all prompts</button>
          {state.running
            ? <button onClick={() => api.control("stop_audio")}>Stop audio</button>
            : <button onClick={() => api.control("start_audio")}>Start audio</button>}
          {state.tunnel_open
            ? <button onClick={() => api.control("close_tunnel")}>Close room</button>
            : <button onClick={() => api.control("open_tunnel")}>Open room</button>}
        </div>
        <div className="op-kick">
          <div className="op-title">Mute a player</div>
          {[...new Set(state.active.map((a) => a.client_id))].map((cid) => (
            <button key={cid} onClick={() => api.control("kick", { client_id: cid })}>
              mute {cid.slice(0, 6)}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
