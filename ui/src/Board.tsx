// Copyright 2026 Google LLC. Apache-2.0.
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { subscribeBoard, api } from "./api";
import type { BoardState } from "./types";
import { OperatorPanel } from "./OperatorPanel";
import { Visualizer } from "./Visualizer";

const VOICE_COLORS = ["#d7c9a2", "#9fb5aa", "#c18466", "#a9a0b8", "#b2a56c", "#8aa6b0"];
const voiceColor = (id: number) => VOICE_COLORS[Math.abs(id) % VOICE_COLORS.length];

export function Board() {
  const [s, setState] = useState<BoardState | null>(null);
  const [panel, setPanel] = useState(false);
  const levelRef = useRef(0);

  useEffect(() => subscribeBoard((st) => { setState(st); levelRef.current = st.level; }), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "o" || e.key === "O") setPanel((p) => !p);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!s) return <div className="boot">warming up the hive…</div>;

  const top = [...s.active].sort((a, b) => b.weight - a.weight);
  const activeCount = s.active.length;
  const featuredLimit = activeCount > 48 ? 6 : activeCount > 16 ? 8 : 10;
  const featured = top.slice(0, featuredLimit);
  const ensemble = top.slice(0, 100);
  const hiddenCount = Math.max(0, activeCount - ensemble.length);
  const level = Math.min(100, s.level * 300);
  const anchorVisible = activeCount === 0 && Boolean(s.anchor);

  return (
    <div className="board">
      <Visualizer levelRef={levelRef} count={s.active.length} />

      <header className="board-head">
        <div className="brand-lockup">
          <div className="eyebrow">group instrument</div>
          <h1 className="logo">Hive</h1>
        </div>
        <div className="board-status">
          <span className={"status-light " + (s.tunnel_open ? "on" : "")} />
          <span>{s.tunnel_open ? "room open" : "room closed"}</span>
        </div>
      </header>

      <main className="board-main">
        <section className="score" aria-label="Live musical voices" data-density={activeCount > 48 ? "high" : activeCount > 16 ? "medium" : "low"}>
          <div className="score-meta">
            <span>{activeCount} voices</span>
            <span>{s.participants} players</span>
            <span>{s.steps_per_s.toFixed(0)} steps/s</span>
          </div>

          {anchorVisible && (
            <div className="anchor-line" key="anchor">
              <span className="line-label">idle anchor</span>
              <span className="anchor-text">{s.anchor}</span>
            </div>
          )}

          <div className="featured-voices">
          {featured.map((p) => {
            const w = Math.min(1, p.weight);
            return (
              <button
                key={p.id}
                className="voice-row"
                onClick={() => api.vote(p.id, "board")}
                aria-label={`Keep ${p.text} in the mix`}
                style={{
                  "--voice-color": voiceColor(p.id),
                  "--presence": w,
                  "--life": `${p.life_frac * 100}%`,
                } as CSSProperties & Record<string, string | number>}
              >
                <span className="voice-index">{String(p.id).padStart(2, "0").slice(-2)}</span>
                <span className="voice-name">
                  <span
                    className="voice-name-text"
                    style={{
                      transform: `scale(${1 + w * 0.045})`,
                    }}
                  >
                    {p.text}
                  </span>
                </span>
                <span className="voice-stats">
                  {p.votes > 0 && <span>{p.votes} holds</span>}
                  <span>{Math.ceil(p.remaining)}s</span>
                </span>
                <span
                  className="voice-meter"
                  style={{
                    transform: `scaleX(${Math.max(0.05, w)})`,
                  }}
                />
                <span className="voice-life" />
              </button>
            );
          })}
          </div>

          {activeCount > featured.length && (
            <div className="ensemble" aria-label="Full ensemble">
              <div className="ensemble-head">
                <span>ensemble</span>
                <span>{activeCount} voices active</span>
              </div>
              <div className="ensemble-grid">
                {ensemble.map((p) => {
                  const w = Math.min(1, p.weight);
                  return (
                    <button
                      key={p.id}
                      className="ensemble-cell"
                      onClick={() => api.vote(p.id, "board")}
                      title={`${p.text} · ${Math.ceil(p.remaining)}s`}
                      style={{
                        "--voice-color": voiceColor(p.id),
                        "--presence": w,
                        "--life": `${p.life_frac * 100}%`,
                      } as CSSProperties & Record<string, string | number>}
                    >
                      <span>{p.text}</span>
                      <span className="ensemble-life" />
                    </button>
                  );
                })}
                {hiddenCount > 0 && <div className="ensemble-more">+{hiddenCount}</div>}
              </div>
            </div>
          )}

          {top.length === 0 && (
            <div className="empty-score">
              <div className="empty-mark">anchor only</div>
              <div>{s.tunnel_open ? "waiting for the room" : "open the room to begin"}</div>
            </div>
          )}
        </section>

        <aside className="join-panel">
          <div className="panel-top">
            <span>join</span>
            <span>{s.running ? "audio on" : "audio off"}</span>
          </div>

          {!s.tunnel_open ? (
            <>
              <div className="qr-frame closed">
                <div className="qr-locked">room closed</div>
              </div>
              <button className="primary-btn" onClick={() => api.control("open_tunnel")}>
                Open room
              </button>
              <div className="muted-copy">QR will appear here.</div>
            </>
          ) : (
            <>
              <div className="qr-frame">
                <img alt="join QR" src={`/api/qr.png?data=${encodeURIComponent(s.join_url)}`} />
              </div>
              <div className="join-url">{s.join_url.replace(/^https?:\/\//, "")}</div>
              <div className="players">
                <div className="players-num">{s.participants}</div>
                <div className="players-label">players</div>
              </div>
            </>
          )}

          <div className="level-block">
            <div className="panel-top">
              <span>output</span>
              <span>{Math.round(level)}%</span>
            </div>
            <div className="meter">
              <div className="meter-fill" style={{ width: `${level}%` }} />
            </div>
          </div>
        </aside>
      </main>

      <button className="gear" onClick={() => setPanel((p) => !p)} title="Operator panel (O)">O</button>
      {panel && <OperatorPanel state={s} onClose={() => setPanel(false)} />}
    </div>
  );
}
