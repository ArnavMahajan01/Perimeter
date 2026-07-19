# Perimeter

Four assignable tap zones on the desk around your laptop, sensed through the
built-in microphone. Tap Left Rear — Gmail opens. Tap Right Front — a
screenshot lands on your clipboard. Software only, cross-platform
(macOS / Linux / Windows).

**[⬇ Download for macOS](https://github.com/ArnavMahajan01/Perimeter/releases/latest)** —
unzip, drag to Applications, then **right-click → Open** on first launch
(the app isn't code-signed yet). Everything runs locally; audio is analyzed
and discarded on the spot.

Inspired by [Holo](https://github.com/JustinGamer191/Holo) (a macOS-only
Swift prototype), reimplemented in Python so it runs on any OS.

## Zone topology

```text
                  Display side
Left Rear      ┌─────────────┐      Right Rear
               │   laptop    │
Left Front     └─────────────┘      Right Front
                  Trackpad side
```

## How it works

A tap sends a faint mechanical transient through the desk into the laptop
chassis and mic. Each zone sounds measurably different (distance, damping,
resonance paths differ), so zone identification is a small per-desk
classification problem. The app detects tap-like transients (90 ms analysis
windows, sustained-sound rejection), classifies the zone with a regularized
linear model, applies ambiguity and out-of-distribution rejection, and runs
the assigned action. Everything is local; raw audio is discarded after
feature extraction.

A calibration is specific to one laptop, desk, and position — moving the
laptop means recalibrating (it takes about a minute).

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Activate the venv (`source .venv/bin/activate`) in every new terminal.

Permissions: the OS will prompt for microphone access on first run. Keyboard
suppression (optional) needs Input Monitoring on macOS. Linux hotkey/copy
actions use `xdotool` / `xclip` if installed.

## Run

```bash
python3 cli.py app
```

The app opens a native window (pywebview). The interface is a React +
shadcn/ui app in `web/`; a pre-built bundle is loaded from `web/dist`. To
rebuild the UI after changing anything in `web/src`:

```bash
cd web && npm install && npm run build
```

If `web/dist` doesn't exist, the app falls back to the legacy single-file
interface in `ui/index.html` (and to a basic Tk window if pywebview is
missing). Six sections in the sidebar:

- **Desk** — the live view. START listening; tapped zones light up and run
  their actions. Zone tiles show the assigned action.
- **Calibrate** — guided setup. Each zone is armed in turn; make 10 natural
  taps spread around the highlighted area. Weak, clipped, or noise-masked
  taps are rejected with guidance ("tap more firmly", "wait for quiet").
  Afterwards a leave-one-out agreement check identifies the weakest zone if
  the calibration isn't reliable. Optionally add noise-rejection samples
  (talk and type while armed) so speech and typing never fire actions.
- **Actions** — one row per zone: `visual`, `sound`, `copy`, `speak`, `url`,
  `app`, `file`, `hotkey`, `shell`, or `screenshot`, each with an inline
  Test button. Changes save as they're made. Below the zone rows live the
  per-app overrides (see next section).
- **Evaluate** — held-out accuracy test: 15 fresh taps per zone, armed one
  zone at a time. Reports per-zone accuracy, a confusion matrix, and median
  latency; targets are ≥80% accuracy and <200 ms. Saved as JSON + CSV and
  restored on relaunch. Rejected taps count as incorrect.
- **Diagnostics** — live input level and a rolling classification log.
- **Settings** — desk profiles, launch at login, background listening,
  pause hotkey.

## Per-app overrides

The same tap can do different things depending on which app you're using.
Each zone has a default action, and an override rule says: *if this app is
frontmost, this zone runs a different action instead.*

Example — Left Rear's default opens Gmail, plus one override rule
(`app: zoom → Left Rear → hotkey: mute`):

| You're using       | Tap Left Rear does |
|--------------------|--------------------|
| Browser, Finder, … | opens Gmail        |
| Zoom               | mutes the call     |

The moment you leave Zoom, the same spot goes back to Gmail. Nothing to
reconfigure — the desk adapts to what's on screen.

Rules are managed at the bottom of the **Actions** tab. App matching is a
case-insensitive "contains": `zoom` matches *zoom.us*, `chrome` matches
*Google Chrome*. The tab shows the current frontmost app so you know
exactly what to type. If several rules match, the first one wins; zones
without a matching rule use their default action.

## Build the standalone app

Package everything into a double-clickable desktop app (no Python or
terminal needed to run it):

```bash
cd web && npm run build && cd ..     # 1. build the UI bundle
.venv/bin/pyinstaller Perimeter.spec # 2. build the app
```

Output lands in `dist/` — `Perimeter.app` on macOS (drag it to
/Applications), a `Perimeter/` folder with `Perimeter.exe` on Windows,
and a `Perimeter/` folder with a `Perimeter` binary on Linux. Build on
each OS you want to ship for; PyInstaller does not cross-compile.

When packaged, user state moves out of the app into the per-user data
directory (`~/Library/Application Support/Perimeter` on macOS,
`%APPDATA%\Perimeter` on Windows, `~/.local/share/perimeter` on Linux),
so calibrations survive app updates.

Note: the macOS app is unsigned — on another Mac, first launch needs
right-click → Open (Gatekeeper). Distributing outside your own machines
properly requires an Apple Developer ID signature + notarization.

## Cross-platform notes

| action     | macOS            | Linux                    | Windows            |
|------------|------------------|--------------------------|--------------------|
| sound      | `afplay`         | `paplay` / `aplay`       | SystemSounds       |
| copy       | `pbcopy`         | `xclip` / `wl-copy`      | `clip`             |
| speak      | `say`            | `espeak` / `spd-say`     | System.Speech      |
| url / file | `open`           | `xdg-open`               | `start`            |
| app        | `open -a`        | `gtk-launch` / exec      | `start`            |
| hotkey     | `osascript`      | `xdotool`                | SendKeys           |
| screenshot | `screencapture`  | `gnome-screenshot`       | PrintScreen        |

## Honest limitations (same physics as Holo)

- Rigid desks (solid wood, laminate) work best. Glass, hollow-core, or
  heavily damped surfaces may not produce separable zones at all.
- The 4 zones must be spread out; adjacent spots on a uniform surface won't
  separate.
- Typing, mug placement, and speech can resemble taps — the sustained-sound
  gate, noise-rejection samples, and OOD rejection reduce false fires but
  can't guarantee zero.
- Run **Evaluate** before trusting it: no desk is "supported" until it
  passes an accuracy test on that exact setup.

## Power-user CLI

```bash
python3 cli.py devices     # list microphones
python3 cli.py listen      # raw tap-detection meter
python3 cli.py run         # headless daemon (uses the app's calibration)
python3 cli.py test        # predictions only, nothing fires
```

Tap decisions are logged to `data/events.log` (JSONL). Evaluation reports
live in `data/evaluations/`, profiles in `data/profiles/`.

## Credits

The idea comes from [Holo](https://github.com/JustinGamer191/Holo) by
[@JustinGamer191](https://github.com/JustinGamer191) — a macOS Swift
prototype that first showed desk-tap zones sensed through the built-in
microphone were possible. Perimeter reimplements the concept from scratch
in Python, cross-platform, with its own calibration, evaluation, and UI.
