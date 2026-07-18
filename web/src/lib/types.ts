export type Tone = "ok" | "warn" | "err" | "muted" | "dim";

export interface TextTone {
  text: string;
  tone: Tone;
}

export const ACTION_TYPES = [
  "visual", "sound", "copy", "speak", "url", "app",
  "file", "hotkey", "shell", "screenshot",
] as const;
export type ActionType = (typeof ACTION_TYPES)[number];

export const NEEDS_TARGET = new Set<ActionType>([
  "copy", "speak", "url", "app", "file", "hotkey", "shell",
]);
export const BROWSABLE = new Set<ActionType>(["app", "file"]);

export const ACTION_HINTS: Record<ActionType, string> = {
  visual: "highlight only",
  sound: "system sound",
  copy: "text to copy",
  speak: "text to speak",
  url: "https://…",
  app: "application name",
  file: "path to file or folder",
  hotkey: "playpause / key code / keystroke expr",
  shell: "shell command",
  screenshot: "full screen to clipboard",
};

export interface ZoneLayout {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface ZoneState {
  id: string;
  name: string;
  enabled: boolean;
  type: ActionType;
  target: string;
  sensitivity: number;
  layout: ZoneLayout;
  desk: TextTone;
  calib: TextTone;
  eval: TextTone;
}

export interface Flash {
  zone: string;
  tone: "ok" | "err";
}

export interface EvalZoneResult {
  correct: number;
  taps: number;
  accuracy: number;
}

export interface EvalReport {
  timestamp: string;
  profile: string;
  accuracy: number;
  median_latency_ms: number;
  passed: boolean;
  per_zone: Record<string, EvalZoneResult>;
  confusion: Record<string, Record<string, number>>;
}

export interface AppState {
  zones: ZoneState[];
  listening: boolean;
  calibrating: boolean;
  evaluating: boolean;
  locked: boolean;
  calibrated: boolean;
  negativeCount: number;
  negLive: string | null;
  trainMsg: TextTone | null;
  status: TextTone;
  meter: number;
  logs: string[];
  flashes: Flash[];
  report: EvalReport | null;
  device: string;
  profile: string;
}

export interface TestActionResult {
  ok: boolean;
  message: string;
}
