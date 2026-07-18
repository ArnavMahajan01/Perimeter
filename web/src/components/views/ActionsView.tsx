import { useState } from "react";
import { FolderOpen, Play } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  ACTION_HINTS,
  ACTION_TYPES,
  BROWSABLE,
  NEEDS_TARGET,
  type ActionType,
  type AppState,
  type ZoneState,
} from "@/lib/types";
import type { Act } from "@/lib/usePerimeter";

interface Props {
  state: AppState;
  act: Act;
}

const GROUPS: [string, string[]][] = [
  ["Left side", ["lr", "lf"]],
  ["Right side", ["rr", "rf"]],
];

export function ActionsView({ state, act }: Props) {
  const byId = new Map(state.zones.map((z) => [z.id, z]));
  return (
    <div>
      <h1 className="text-[19px] font-semibold tracking-tight">Actions</h1>
      <p className="mt-0.5 mb-5 max-w-[640px] text-[13px] text-muted-foreground">
        What each zone does when tapped. Changes save automatically.
      </p>
      {GROUPS.map(([label, ids]) => (
        <div key={label}>
          <div className="mt-4 mb-2 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground/60 uppercase">
            {label}
          </div>
          {ids.map((zid) => {
            const zone = byId.get(zid);
            return zone ? <ActionRow key={zid} zone={zone} act={act} /> : null;
          })}
        </div>
      ))}
    </div>
  );
}

function ActionRow({ zone, act }: { zone: ZoneState; act: Act }) {
  // While the user is typing, render the draft — not the polled value —
  // so the 120 ms poll can't overwrite in-progress input.
  const [draft, setDraft] = useState<string | null>(null);
  const target = draft ?? zone.target;
  const needsTarget = NEEDS_TARGET.has(zone.type);
  const browsable = BROWSABLE.has(zone.type);

  const setAction = (kind: ActionType, value: string) =>
    act((api) => api.set_action(zone.id, kind, value));

  return (
    <div className="mb-2 flex items-center gap-3 rounded-lg border bg-card px-4 py-3">
      <div className="w-[92px] flex-none text-[13px] font-semibold">{zone.name}</div>

      <Switch
        checked={zone.enabled}
        onCheckedChange={(on) => act((api) => api.set_enabled(zone.id, on))}
      />

      <Select
        value={zone.type}
        onValueChange={(v) => setAction(v as ActionType, target)}
      >
        <SelectTrigger className="w-[130px] flex-none">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {ACTION_TYPES.map((t) => (
            <SelectItem key={t} value={t}>
              {t}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>

      <Input
        value={needsTarget ? target : ""}
        disabled={!needsTarget}
        placeholder={ACTION_HINTS[zone.type]}
        onFocus={() => setDraft(zone.target)}
        onBlur={() => setDraft(null)}
        onChange={(e) => {
          setDraft(e.target.value);
          setAction(zone.type, e.target.value);
        }}
        className="flex-1"
      />

      {browsable && (
        <Button
          variant="outline"
          size="sm"
          className="flex-none"
          onClick={async () => {
            const path = await act((api) => api.browse(zone.id, zone.type));
            if (path) setDraft(null);
          }}
        >
          <FolderOpen />
          Browse
        </Button>
      )}

      <Tooltip>
        <TooltipTrigger asChild>
          <div className="w-[90px] flex-none">
            {/* uncontrolled: the thumb must track the pointer during a drag
                without the poll snapping it back; commit saves on release */}
            <Slider
              defaultValue={[zone.sensitivity]}
              min={0}
              max={100}
              step={1}
              onValueCommit={([v]) => act((api) => api.set_sensitivity(zone.id, v))}
            />
          </div>
        </TooltipTrigger>
        <TooltipContent>sensitivity</TooltipContent>
      </Tooltip>

      <Button
        variant="ghost"
        size="sm"
        className="flex-none text-muted-foreground"
        onClick={async () => {
          const r = await act((api) => api.test_action(zone.id));
          if (r) (r.ok ? toast.success : toast.error)(r.message);
        }}
      >
        <Play />
        Test
      </Button>
    </div>
  );
}
