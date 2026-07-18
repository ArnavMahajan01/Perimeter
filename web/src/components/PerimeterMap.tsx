import { useMemo, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { Flash, Tone, ZoneLayout, ZoneState } from "@/lib/types";

const TONE_TEXT: Record<Tone, string> = {
  ok: "text-success",
  warn: "text-warning",
  err: "text-destructive",
  muted: "text-muted-foreground",
  dim: "text-muted-foreground/50",
};

const MIN_SIZE = 0.14;

interface PerimeterMapProps {
  zones: ZoneState[];
  sub: "desk" | "calib" | "eval";
  flashes: (Flash & { key: number })[];
  /** When true, zones can be dragged to move and resized from the corner grip. */
  editable?: boolean;
  onLayoutChange?: (zoneId: string, layout: ZoneLayout) => void;
  className?: string;
}

type DragMode = "move" | "resize";

export function PerimeterMap({
  zones,
  sub,
  flashes,
  editable = false,
  onLayoutChange,
  className,
}: PerimeterMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // While a drag is in flight the dragged zone renders from this override,
  // not from polled state — otherwise every poll tick would yank the tile
  // back to its last-saved position mid-drag.
  const [override, setOverride] = useState<{ id: string; layout: ZoneLayout } | null>(null);
  const drag = useRef<{
    zoneId: string;
    mode: DragMode;
    startX: number;
    startY: number;
    origin: ZoneLayout;
    latest: ZoneLayout;
  } | null>(null);

  const flashByZone = useMemo(() => {
    const m = new Map<string, "ok" | "err">();
    for (const f of flashes) m.set(f.zone, f.tone);
    return m;
  }, [flashes]);

  const startDrag = (zone: ZoneState, mode: DragMode) => (e: React.PointerEvent) => {
    if (!editable) return;
    e.preventDefault();
    e.stopPropagation();
    const origin = override?.id === zone.id ? override.layout : zone.layout;
    drag.current = {
      zoneId: zone.id,
      mode,
      startX: e.clientX,
      startY: e.clientY,
      origin,
      latest: origin,
    };

    const onMove = (ev: PointerEvent) => {
      const d = drag.current;
      const rect = containerRef.current?.getBoundingClientRect();
      if (!d || !rect) return;
      const dx = (ev.clientX - d.startX) / rect.width;
      const dy = (ev.clientY - d.startY) / rect.height;
      const o = d.origin;
      const next: ZoneLayout =
        d.mode === "move"
          ? {
              ...o,
              x: clamp(o.x + dx, 0, 1 - o.w),
              y: clamp(o.y + dy, 0, 1 - o.h),
            }
          : {
              ...o,
              w: clamp(o.w + dx, MIN_SIZE, 1 - o.x),
              h: clamp(o.h + dy, MIN_SIZE, 1 - o.y),
            };
      // Zones must not overlap each other: if this position would collide
      // with another zone, keep the last valid position instead.
      const others = zones.filter((z) => z.id !== d.zoneId);
      if (others.some((z) => intersects(next, z.layout))) return;
      d.latest = next;
      setOverride({ id: d.zoneId, layout: next });
    };

    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      const d = drag.current;
      drag.current = null;
      if (d) onLayoutChange?.(d.zoneId, d.latest);
      // Keep the override until the next poll returns the saved layout;
      // clearing it after a short grace period avoids a visible snap-back.
      setTimeout(() => setOverride(null), 400);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative min-h-[280px] rounded-xl border-2 border-dashed border-border bg-card/30",
        className,
      )}
    >
      {/* laptop anchor, fixed, non-interactive */}
      <div className="pointer-events-none absolute top-1/2 left-1/2 z-0 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-1 text-muted-foreground/60">
        <div className="grid h-14 w-20 place-items-center rounded-lg border border-border/80 bg-gradient-to-b from-card to-background text-xl">
          ⌨
        </div>
        <span className="text-[11px]">laptop</span>
      </div>

      {zones.map((zone) => {
        const layout = override?.id === zone.id ? override.layout : zone.layout;
        const flash = flashByZone.get(zone.id);
        const status = zone[sub];
        return (
          <div
            key={zone.id}
            onPointerDown={startDrag(zone, "move")}
            className={cn(
              "absolute z-10 flex flex-col gap-1 overflow-hidden rounded-lg border-2 border-dashed bg-card/90 p-3 shadow-sm transition-[box-shadow,border-color] duration-150",
              editable ? "cursor-grab touch-none select-none active:cursor-grabbing" : "",
              flash === "ok" &&
                "border-solid border-success shadow-[0_0_0_1px_var(--success),0_0_24px_-4px_var(--success)]",
              flash === "err" &&
                "border-solid border-destructive shadow-[0_0_0_1px_var(--destructive),0_0_24px_-4px_var(--destructive)]",
              !flash && "border-border",
            )}
            style={{
              left: `${layout.x * 100}%`,
              top: `${layout.y * 100}%`,
              width: `${layout.w * 100}%`,
              height: `${layout.h * 100}%`,
            }}
          >
            <div className="truncate text-[13.5px] font-semibold tracking-tight">
              {zone.name}
            </div>
            <div className={cn("min-h-[18px] truncate text-[12.5px]", TONE_TEXT[status.tone])}>
              {status.text}
            </div>
            {editable && (
              <div
                onPointerDown={startDrag(zone, "resize")}
                className="absolute right-0 bottom-0 h-5 w-5 cursor-nwse-resize touch-none"
                aria-label={`Resize ${zone.name}`}
              >
                <svg viewBox="0 0 20 20" className="h-full w-full text-muted-foreground/50">
                  <path d="M17 11v6h-6" fill="none" stroke="currentColor" strokeWidth="1.5" />
                </svg>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function clamp(v: number, min: number, max: number) {
  return Math.min(Math.max(v, min), Math.max(min, max));
}

const GAP = 0.01; // minimum spacing between zones (canvas fraction)

function intersects(a: ZoneLayout, b: ZoneLayout) {
  return (
    a.x < b.x + b.w + GAP &&
    a.x + a.w + GAP > b.x &&
    a.y < b.y + b.h + GAP &&
    a.y + a.h + GAP > b.y
  );
}
