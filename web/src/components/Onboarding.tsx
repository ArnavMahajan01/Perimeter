import { useState } from "react";
import { Crosshair, Hand, Mic, Waves } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { AppState } from "@/lib/types";
import type { Act } from "@/lib/usePerimeter";

interface Props {
  state: AppState;
  act: Act;
  onFinish: (goToCalibrate: boolean) => void;
}

const STEPS = ["Welcome", "Microphone", "Technique"] as const;

export function Onboarding({ state, act, onFinish }: Props) {
  const [step, setStep] = useState(0);

  const finish = async (goToCalibrate: boolean) => {
    await act((api) => api.set_onboarded());
    onFinish(goToCalibrate);
  };

  return (
    <div className="absolute inset-0 z-50 grid place-items-center bg-background/90 backdrop-blur-sm">
      <div className="w-[520px] rounded-xl border bg-card p-8 shadow-lg">
        {/* step dots */}
        <div className="mb-6 flex items-center gap-1.5">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={cn(
                "h-1.5 rounded-full transition-all",
                i === step ? "w-6 bg-primary" : "w-1.5 bg-muted-foreground/30",
              )}
            />
          ))}
        </div>

        {step === 0 && (
          <>
            <Waves className="mb-4 size-8 text-muted-foreground" />
            <h2 className="mb-2 text-lg font-semibold tracking-tight">
              Turn your desk into buttons
            </h2>
            <p className="mb-3 text-[13.5px] leading-relaxed text-muted-foreground">
              Perimeter listens for taps on the desk around your laptop through the
              built-in microphone. Four zones — two on each side — each run an action
              you choose: open an app, take a screenshot, play/pause, anything.
            </p>
            <p className="mb-6 text-[13.5px] leading-relaxed text-muted-foreground">
              It works best on <span className="text-foreground">rigid desks</span> (solid
              wood, laminate). Glass or hollow-core surfaces may not separate zones well.
              Everything runs locally — audio never leaves your machine.
            </p>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => finish(false)}>
                Skip
              </Button>
              <Button onClick={() => setStep(1)}>Next</Button>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <Mic className="mb-4 size-8 text-muted-foreground" />
            <h2 className="mb-2 text-lg font-semibold tracking-tight">Check your microphone</h2>
            <p className="mb-4 text-[13.5px] leading-relaxed text-muted-foreground">
              Tap the desk a few times — the meter below should jump. If it doesn't move,
              grant microphone access in System Settings → Privacy &amp; Security →
              Microphone, then relaunch.
            </p>
            <div className="mb-1 text-xs text-muted-foreground">
              input · {state.device}
            </div>
            <div className="mb-6 h-2 overflow-hidden rounded-full bg-input">
              <div
                className="h-full rounded-full bg-success transition-[width] duration-100 ease-linear"
                style={{ width: `${Math.min(100, state.meter * 100).toFixed(1)}%` }}
              />
            </div>
            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(0)}>
                Back
              </Button>
              <Button onClick={() => setStep(2)}>Next</Button>
            </div>
          </>
        )}

        {step === 2 && (
          <>
            <Hand className="mb-4 size-8 text-muted-foreground" />
            <h2 className="mb-2 text-lg font-semibold tracking-tight">How to tap</h2>
            <ul className="mb-6 space-y-2 text-[13.5px] leading-relaxed text-muted-foreground">
              <li>
                • Tap with a <span className="text-foreground">fingertip, firmly</span> — like
                knocking softly on a door. Too-light taps are rejected.
              </li>
              <li>
                • During calibration, <span className="text-foreground">spread your taps
                around each zone</span>, don't hit the same exact spot 10 times.
              </li>
              <li>
                • Keep the laptop where it will stay —{" "}
                <span className="text-foreground">moving it invalidates calibration</span>{" "}
                (recalibrating takes about a minute).
              </li>
            </ul>
            <div className="flex justify-between">
              <Button variant="ghost" onClick={() => setStep(1)}>
                Back
              </Button>
              <Button onClick={() => finish(true)}>
                <Crosshair />
                Start calibration
              </Button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
