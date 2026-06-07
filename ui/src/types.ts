// Copyright 2026 Google LLC. Apache-2.0.

export interface ActivePrompt {
  id: number;
  text: string;
  weight: number;
  remaining: number;
  timeout: number;
  life_frac: number;
  votes: number;
  client_id: string;
}

export interface Params {
  base_prompt: string;
  anchor_weight: number;
  ramp_in_s: number;
  timeout_s: number;
  ramp_out_s: number;
  mix_mode: string;
  max_prompts: number;
  per_prompt_cap: number;
  crowd_gain: number;
  normalize_mode: string;
  chunk_frames: number;
  temperature: number;
  top_k: number;
  cfg_musiccoca: number;
  cfg_drums: number;
  drums_on: boolean;
  master_gain: number;
  max_buffer_s: number;
  profanity_filter: boolean;
}

export interface BoardState {
  running: boolean;
  tunnel_open: boolean;
  join_url: string;
  lan_url: string;
  participants: number;
  level: number;
  steps_per_s: number;
  anchor: string | null;
  active: ActivePrompt[];
  params: Params;
}
