import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PerimeterMap } from "@/components/PerimeterMap";
import { cn } from "@/lib/utils";
import type { AppState, Tone } from "@/lib/types";
import type { Act, ActiveFlashes } from "@/lib/usePerimeter";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-success",
  warn: "text-warning",
  err: "text-destructive",
  muted: "text-muted-foreground",
  dim: "text-muted-foreground/50",
};

interface Props {
  state: AppState;
  act: Act;
  flashes: ActiveFlashes;
}

export function CalibrateView({ state, act, flashes }: Props) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[19px] font-semibold tracking-tight">Calibrate</h1>
        <Button
          variant={state.calibrating ? "outline" : "default"}
          className={state.calibrating ? "text-destructive" : ""}
          disabled={state.listening || state.evaluating}
          onClick={() => act((api) => api.calib_toggle())}
        >
          {state.calibrating ? "Cancel" : "Begin calibration"}
        </Button>
      </div>
      <p className="mt-0.5 mb-5 max-w-[640px] text-[13px] text-muted-foreground">
        Each zone arms in turn — make 10 natural taps spread around the highlighted area.
        Keep the laptop where it will stay; moving it invalidates calibration.
      </p>
      <div className="mb-2 text-center text-[11px] text-muted-foreground/50">display side</div>
      <PerimeterMap zones={state.zones} sub="calib" flashes={flashes} className="min-h-[300px]" />
      <div className="mt-2 text-center text-[11px] text-muted-foreground/50">trackpad side</div>

      <div className="mt-4 flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          disabled={state.locked || state.listening}
          onClick={() => act((api) => api.calib_negative())}
        >
          <Plus />
          {state.negLive
            ? state.negLive
            : `Noise rejection${state.negativeCount ? ` · ${state.negativeCount} samples` : ""}`}
        </Button>
        {state.trainMsg && (
          <span className={cn("text-[13px]", TONE_TEXT[state.trainMsg.tone])}>
            {state.trainMsg.text}
          </span>
        )}
      </div>

      {state.trainReport && (
        <div className="mt-4 max-w-[640px] rounded-lg border bg-card px-4 py-3">
          <div className="mb-2 text-xs text-muted-foreground">
            zone separation — how reliably each zone's taps are told apart
            (from {state.trainReport.timestamp})
          </div>
          <div className="flex flex-wrap gap-2">
            {state.zones.map((z) => {
              const score = state.trainReport!.per_zone[z.id];
              if (score === undefined) return null;
              const pct = Math.round(score * 100);
              const tone =
                pct >= 90 ? "text-success" : pct >= 75 ? "text-warning" : "text-destructive";
              return (
                <span
                  key={z.id}
                  className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs"
                >
                  {z.name}
                  <span className={cn("font-semibold tabular-nums", tone)}>{pct}%</span>
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
