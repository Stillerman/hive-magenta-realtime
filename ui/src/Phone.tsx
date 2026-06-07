// Copyright 2026 Google LLC. Apache-2.0.
import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { api, subscribeBoard } from "./api";
import type { ActivePrompt } from "./types";

const SUGGEST = [
  "deep house", "ambient pads", "sub bass", "church organ", "disco funk", "lo-fi hip hop",
  "trap drums", "flamenco guitar", "jazz saxophone", "gospel choir", "drum and bass", "sitar",
  "808 bass", "steel drums", "gregorian chant", "synthwave", "minimal techno", "warm rhodes",
];

const VOICE_COLORS = ["#d7c9a2", "#9fb5aa", "#c18466", "#a9a0b8", "#b2a56c", "#8aa6b0"];
const voiceColor = (id: number) => VOICE_COLORS[Math.abs(id) % VOICE_COLORS.length];

function clientId(): string {
  let id = localStorage.getItem("hive_cid");
  if (!id) { id = Math.random().toString(36).slice(2); localStorage.setItem("hive_cid", id); }
  return id;
}

export function Phone() {
  const cid = useRef(clientId());
  const [text, setText] = useState("");
  const [last, setLast] = useState("");
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);
  const [active, setActive] = useState<ActivePrompt[]>([]);
  const [participants, setParticipants] = useState(0);
  const [presetSeed, setPresetSeed] = useState(() => Math.floor(Math.random() * SUGGEST.length));

  useEffect(() => {
    const beat = () => api.heartbeat(cid.current).catch(() => {});
    beat();
    const t = setInterval(beat, 5000);
    const unsub = subscribeBoard((s) => {
      setActive(s.active);
      setParticipants(s.participants);
    });
    return () => { clearInterval(t); unsub(); };
  }, []);

  const live = useMemo(
    () => [...active].sort((a, b) => b.weight - a.weight).slice(0, 4),
    [active],
  );

  const presets = useMemo(
    () => Array.from({ length: 6 }, (_, i) => SUGGEST[(presetSeed + i * 3) % SUGGEST.length]),
    [presetSeed],
  );

  const send = async (value: string) => {
    const v = value.trim();
    if (!v) return;
    setLast(v);
    const d = await api.submitPrompt(v, cid.current);
    if (d.ok) {
      setToast({ msg: `"${v}" entered the mix`, ok: true });
      setText("");
      setPresetSeed((seed) => (seed + 5) % SUGGEST.length);
    }
    else { setToast({ msg: d.message || "try again", ok: false }); }
  };

  const keepAlive = (p: ActivePrompt) => {
    api.vote(p.id, cid.current);
    setToast({ msg: `"${p.text}" held`, ok: true });
  };

  return (
    <div className="phone">
      <header className="phone-head">
        <div>
          <h1 className="logo">Hive</h1>
        </div>
        <div className="phone-count">
          <span>{active.length} voices</span>
          <span>{participants} players</span>
        </div>
      </header>

      <main className="phone-main">
        <section className="phone-live" aria-label="Live voices">
          <div className="section-title">hold a voice</div>
          {live.length > 0 ? (
            <div className="live-grid">
              {live.map((p) => (
                <button key={p.id} className="live-chip" onClick={() => keepAlive(p)}
                        style={{ "--voice-color": voiceColor(p.id), "--life": `${p.life_frac * 100}%` } as CSSProperties & Record<string, string>}>
                  <span className="live-chip-text">{p.text}</span>
                  <span className="live-chip-meta">{Math.ceil(p.remaining)}s</span>
                  <span className="live-bar-track">
                    <span className="live-bar" />
                  </span>
                </button>
              ))}
              {active.length > live.length && (
                <div className="live-more">+{active.length - live.length} more in the room</div>
              )}
            </div>
          ) : (
            <div className="phone-empty">waiting for the first voice</div>
          )}
        </section>

        <section className="phone-presets" aria-label="Presets">
          <div className="section-title">presets</div>
          <div className="chips">
            {presets.map((c) => (
              <button key={c} className="chip" onClick={() => send(c)}>{c}</button>
            ))}
          </div>
        </section>
      </main>

      <footer className="phone-composer">
        <div className={"phone-toast " + (toast ? (toast.ok ? "ok" : "err") : "")}>
          {toast?.msg || (last ? `Last: ${last}` : " ")}
        </div>
        <form className="phone-form" onSubmit={(e) => { e.preventDefault(); send(text); }}>
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="add a style"
            maxLength={80}
            autoComplete="off"
          />
          <button type="submit">Send</button>
        </form>
      </footer>
    </div>
  );
}
