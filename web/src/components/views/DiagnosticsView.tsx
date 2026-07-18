import { ScrollArea } from "@/components/ui/scroll-area";
import type { AppState } from "@/lib/types";

interface Props {
  state: AppState;
}

export function DiagnosticsView({ state }: Props) {
  return (
    <div className="flex h-full flex-col">
      <h1 className="text-[19px] font-semibold tracking-tight">Diagnostics</h1>
      <p className="mt-0.5 mb-5 max-w-[640px] text-[13px] text-muted-foreground">
        Live input level and the rolling classification log.
      </p>

      <div className="mb-4 grid max-w-[420px] grid-cols-[130px_1fr] gap-x-3 gap-y-1 text-[13px]">
        <span className="text-muted-foreground">input</span>
        <span>{state.device}</span>
        <span className="text-muted-foreground">profile</span>
        <span>{state.profile}</span>
        <span className="text-muted-foreground">window</span>
        <span>90 ms @ 44100 Hz</span>
        <span className="text-muted-foreground">calibrated</span>
        <span>{state.calibrated ? "yes" : "no"}</span>
      </div>

      <div className="text-xs text-muted-foreground">input level</div>
      <div className="mt-1.5 mb-4 h-1.5 overflow-hidden rounded-full bg-input">
        <div
          className="h-full rounded-full bg-foreground transition-[width] duration-100 ease-linear"
          style={{ width: `${Math.min(100, state.meter * 100).toFixed(1)}%` }}
        />
      </div>

      <ScrollArea className="min-h-0 flex-1 rounded-lg border bg-card">
        <pre className="p-3.5 font-mono text-xs leading-[1.7] whitespace-pre-wrap text-muted-foreground">
          {state.logs.join("\n") || "no events yet"}
        </pre>
      </ScrollArea>
    </div>
  );
}
