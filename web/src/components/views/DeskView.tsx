import { useState } from "react";
import { Pencil, PencilOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { PerimeterMap } from "@/components/PerimeterMap";
import type { AppState } from "@/lib/types";
import type { Act, ActiveFlashes } from "@/lib/usePerimeter";

interface Props {
  state: AppState;
  act: Act;
  flashes: ActiveFlashes;
}

export function DeskView({ state, act, flashes }: Props) {
  const [editLayout, setEditLayout] = useState(false);
  const listenDisabled = (state.locked || !state.calibrated) && !state.listening;

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[19px] font-semibold tracking-tight">Desk</h1>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditLayout((v) => !v)}
            className="text-muted-foreground"
          >
            {editLayout ? <PencilOff /> : <Pencil />}
            {editLayout ? "Done" : "Edit layout"}
          </Button>
          <Button
            variant={state.listening ? "outline" : "default"}
            className={state.listening ? "text-destructive" : ""}
            disabled={listenDisabled}
            onClick={() => act((api) => api.toggle_listen())}
          >
            {state.listening ? "Stop listening" : "Start listening"}
          </Button>
        </div>
      </div>
      <p className="mt-0.5 mb-5 max-w-[640px] text-[13px] text-muted-foreground">
        {editLayout
          ? "Drag zones to move them, pull the corner grip to resize. A bigger zone accepts taps more permissively (catches taps farther from where you calibrated); a smaller zone is stricter. To truly extend a zone's physical reach, recalibrate with taps spread over the larger area."
          : "Tap a calibrated zone on the desk to run its action. Zones light up when they fire."}
      </p>
      <div className="mb-2 text-center text-[11px] text-muted-foreground/50">display side</div>
      <PerimeterMap
        zones={state.zones}
        sub="desk"
        flashes={flashes}
        editable={editLayout}
        onLayoutChange={(zid, l) => act((api) => api.set_layout(zid, l.x, l.y, l.w, l.h))}
        className="min-h-[320px]"
      />
      <div className="mt-2 text-center text-[11px] text-muted-foreground/50">trackpad side</div>
    </div>
  );
}
