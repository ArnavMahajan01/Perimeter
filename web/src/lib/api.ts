import type { ActionType, AppState, TestActionResult } from "./types";

interface PywebviewApi {
  poll(): Promise<AppState>;
  toggle_listen(): Promise<void>;
  calib_toggle(): Promise<void>;
  calib_negative(): Promise<void>;
  eval_toggle(): Promise<void>;
  set_action(zid: string, kind: ActionType, target: string): Promise<void>;
  set_enabled(zid: string, enabled: boolean): Promise<void>;
  set_sensitivity(zid: string, value: number): Promise<void>;
  set_layout(zid: string, x: number, y: number, w: number, h: number): Promise<void>;
  test_action(zid: string): Promise<TestActionResult>;
  browse(zid: string, kind: ActionType): Promise<string | null>;
  set_onboarded(): Promise<void>;
  set_background_mode(enabled: boolean): Promise<void>;
  set_launch_at_login(enabled: boolean): Promise<TestActionResult>;
  switch_profile(name: string): Promise<TestActionResult>;
  create_profile(name: string): Promise<TestActionResult>;
  delete_profile(name: string): Promise<TestActionResult>;
  add_override(): Promise<TestActionResult>;
  update_override(
    index: number, app: string, zid: string, kind: ActionType, target: string,
  ): Promise<void>;
  remove_override(index: number): Promise<void>;
  calib_zone(zid: string): Promise<void>;
  activate_license(key: string): Promise<TestActionResult>;
  deactivate_license(): Promise<TestActionResult>;
}

declare global {
  interface Window {
    pywebview?: { api: PywebviewApi };
  }
}

/** Resolves once window.pywebview.api exists (fires after native window init). */
export function whenReady(): Promise<PywebviewApi> {
  return new Promise((resolve) => {
    if (window.pywebview?.api) {
      resolve(window.pywebview.api);
      return;
    }
    window.addEventListener(
      "pywebviewready",
      () => resolve(window.pywebview!.api),
      { once: true },
    );
  });
}
