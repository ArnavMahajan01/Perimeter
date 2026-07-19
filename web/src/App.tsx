import { useState } from "react";
import {
  Activity,
  ChartLine,
  Crosshair,
  LayoutGrid,
  Settings,
  Zap,
} from "lucide-react";
import { Toaster } from "@/components/ui/sonner";
import { cn } from "@/lib/utils";
import { usePerimeter } from "@/lib/usePerimeter";
import type { Tone } from "@/lib/types";
import { DeskView } from "@/components/views/DeskView";
import { CalibrateView } from "@/components/views/CalibrateView";
import { ActionsView } from "@/components/views/ActionsView";
import { EvaluateView } from "@/components/views/EvaluateView";
import { DiagnosticsView } from "@/components/views/DiagnosticsView";
import { SettingsView } from "@/components/views/SettingsView";
import { Onboarding } from "@/components/Onboarding";

const VIEWS = [
  { id: "desk", label: "Desk", icon: LayoutGrid },
  { id: "calibrate", label: "Calibrate", icon: Crosshair },
  { id: "actions", label: "Actions", icon: Zap },
  { id: "evaluate", label: "Evaluate", icon: ChartLine },
  { id: "diagnostics", label: "Diagnostics", icon: Activity },
  { id: "settings", label: "Settings", icon: Settings },
] as const;

type ViewId = (typeof VIEWS)[number]["id"];

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-success",
  warn: "text-warning",
  err: "text-destructive",
  muted: "text-muted-foreground",
  dim: "text-muted-foreground/50",
};

export default function App() {
  const [view, setView] = useState<ViewId>("desk");
  const [forceOnboarding, setForceOnboarding] = useState(false);
  const { state, act, activeFlashes } = usePerimeter();

  if (!state) {
    return (
      <div className="grid h-full place-items-center text-sm text-muted-foreground">
        starting…
      </div>
    );
  }

  const showOnboarding = forceOnboarding || !state.onboarded;

  return (
    <div className="relative flex h-full">
      {showOnboarding && (
        <Onboarding
          state={state}
          act={act}
          onFinish={(goToCalibrate) => {
            setForceOnboarding(false);
            if (goToCalibrate) setView("calibrate");
          }}
        />
      )}
      {/* sidebar */}
      <aside className="flex w-[212px] flex-none flex-col border-r bg-sidebar px-2.5 pt-4 pb-3.5">
        <div className="flex items-center gap-2.5 px-2.5 pb-4">
          <div className="grid h-7 w-7 place-items-center rounded-md bg-primary text-[13px] font-bold text-primary-foreground">
            P
          </div>
          <span className="text-[14.5px] font-semibold tracking-tight">Perimeter</span>
        </div>
        <nav className="flex flex-col gap-0.5">
          {VIEWS.map(({ id, label, icon: Icon }) => {
            const lockedOut = state.locked && id !== view;
            return (
              <button
                key={id}
                onClick={() => setView(id)}
                disabled={lockedOut}
                className={cn(
                  "flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13.5px] font-medium transition-colors",
                  view === id
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
                  lockedOut && "pointer-events-none opacity-40",
                )}
              >
                <Icon className="size-[15px]" />
                {label}
              </button>
            );
          })}
        </nav>
        <div className="mt-auto flex items-center gap-2 px-2.5 text-xs text-muted-foreground/60">
          <span
            className={cn(
              "h-1.5 w-1.5 rounded-full",
              state.meter > 0.001 ? "bg-success" : "bg-muted-foreground/40",
            )}
          />
          microphone
        </div>
      </aside>

      {/* main */}
      <main className="flex min-w-0 flex-1 flex-col">
        <div className="flex-1 overflow-y-auto px-7 pt-6 pb-4">
          {view === "desk" && <DeskView state={state} act={act} flashes={activeFlashes} />}
          {view === "calibrate" && (
            <CalibrateView state={state} act={act} flashes={activeFlashes} />
          )}
          {view === "actions" && <ActionsView state={state} act={act} />}
          {view === "evaluate" && (
            <EvaluateView state={state} act={act} flashes={activeFlashes} />
          )}
          {view === "diagnostics" && <DiagnosticsView state={state} />}
          {view === "settings" && (
            <SettingsView
              state={state}
              act={act}
              onRerunOnboarding={() => setForceOnboarding(true)}
            />
          )}
        </div>
        <footer className="flex flex-none items-center justify-between border-t bg-background px-7 py-2 text-[12.5px]">
          <span className={TONE_TEXT[state.status.tone]}>{state.status.text}</span>
          <span className="text-muted-foreground/50">
            {state.device} · profile {state.profile}
          </span>
        </footer>
      </main>
      <Toaster position="bottom-right" />
    </div>
  );
}
