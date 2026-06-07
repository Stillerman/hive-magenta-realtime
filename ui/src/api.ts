// Copyright 2026 Google LLC. Apache-2.0.
import type { BoardState, Params } from "./types";

async function post(path: string, body: unknown) {
  const r = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

export const api = {
  submitPrompt: (text: string, client_id: string) =>
    post("/api/prompt", { text, client_id }),
  vote: (id: number, client_id: string) => post("/api/vote", { id, client_id }),
  heartbeat: (client_id: string) => post("/api/heartbeat", { client_id }),
  setParams: (patch: Partial<Params>) => post("/api/params", patch),
  control: (action: string, extra: Record<string, unknown> = {}) =>
    post("/api/control", { action, ...extra }),
  getState: async (): Promise<BoardState> =>
    (await fetch("/api/state")).json(),
};

/** Subscribe to the board state websocket, with auto-reconnect + polling fallback. */
export function subscribeBoard(onState: (s: BoardState) => void): () => void {
  let ws: WebSocket | null = null;
  let poll: ReturnType<typeof setInterval> | null = null;
  let closed = false;

  const startPolling = () => {
    if (poll) return;
    poll = setInterval(async () => {
      try { onState(await api.getState()); } catch { /* ignore */ }
    }, 250);
  };
  const stopPolling = () => { if (poll) { clearInterval(poll); poll = null; } };

  const connect = () => {
    if (closed) return;
    const proto = location.protocol === "https:" ? "wss://" : "ws://";
    ws = new WebSocket(proto + location.host + "/ws/board");
    ws.onmessage = (e) => { stopPolling(); onState(JSON.parse(e.data)); };
    ws.onclose = () => { startPolling(); if (!closed) setTimeout(connect, 1500); };
    ws.onerror = () => { ws?.close(); };
  };
  connect();

  return () => { closed = true; stopPolling(); ws?.close(); };
}
