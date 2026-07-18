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
    </div>
  );
}
