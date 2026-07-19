import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Separator } from "@/components/ui/separator";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { AppState } from "@/lib/types";
import type { Act } from "@/lib/usePerimeter";

interface Props {
  state: AppState;
  act: Act;
  onRerunOnboarding: () => void;
}

export function SettingsView({ state, act, onRerunOnboarding }: Props) {
  const [newProfile, setNewProfile] = useState("");

  const createProfile = async () => {
    const name = newProfile.trim();
    if (!name) return;
    const r = await act((api) => api.create_profile(name));
    if (r) {
      (r.ok ? toast.success : toast.error)(r.message);
      if (r.ok) setNewProfile("");
    }
  };

  return (
    <div>
      <h1 className="text-[19px] font-semibold tracking-tight">Settings</h1>
      <p className="mt-0.5 mb-5 max-w-[640px] text-[13px] text-muted-foreground">
        App behavior. Zone actions and sensitivity live in the Actions tab.
      </p>

      <div className="mb-4 max-w-[560px] rounded-lg border bg-card px-4 py-3.5">
        <div className="text-[13.5px] font-medium">Desk profiles</div>
        <div className="mt-0.5 mb-3 max-w-[420px] text-[12.5px] text-muted-foreground">
          One profile per physical setup (home desk, office, kitchen table).
          Each keeps its own calibration — switch instead of recalibrating.
        </div>
        <div className="flex items-center gap-2">
          <Select
            value={state.profile}
            onValueChange={async (name) => {
              const r = await act((api) => api.switch_profile(name));
              if (r && !r.ok) toast.error(r.message);
            }}
            disabled={state.locked}
          >
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {state.profiles.map((p) => (
                <SelectItem key={p} value={p}>
                  {p}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="ghost"
            size="sm"
            className="text-muted-foreground"
            disabled={state.locked || state.profile === "default"}
            onClick={async () => {
              const r = await act((api) => api.delete_profile(state.profile));
              if (r) (r.ok ? toast.success : toast.error)(r.message);
            }}
            title="Delete this profile and its calibration"
          >
            <Trash2 />
            Delete
          </Button>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <Input
            value={newProfile}
            onChange={(e) => setNewProfile(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && createProfile()}
            placeholder="new profile name"
            className="w-[180px]"
            disabled={state.locked}
          />
          <Button
            variant="outline"
            size="sm"
            disabled={state.locked || !newProfile.trim()}
            onClick={createProfile}
          >
            <Plus />
            Create
          </Button>
        </div>
      </div>

      <div className="max-w-[560px] space-y-1 rounded-lg border bg-card px-4">
        <SettingRow
          title="Launch at login"
          description="Start Perimeter automatically when you log in. (Takes effect for the installed app, not when running from the source folder.)"
        >
          <Switch
            checked={state.launchAtLogin}
            onCheckedChange={async (on) => {
              const r = await act((api) => api.set_launch_at_login(on));
              if (r && !r.ok) toast.error(r.message);
            }}
          />
        </SettingRow>
        <Separator />
        <SettingRow
          title="Keep listening in background"
          description="Closing the window keeps Perimeter listening; click the Dock icon to bring it back. Off = closing the window quits."
        >
          <Switch
            checked={state.backgroundMode}
            onCheckedChange={(on) => act((api) => api.set_background_mode(on))}
          />
        </SettingRow>
        <Separator />
        <SettingRow
          title="Pause hotkey"
          description="Toggle listening from anywhere. Needs Input Monitoring permission on macOS."
        >
          <kbd className="rounded-md border bg-muted px-2 py-1 font-mono text-xs">
            {state.pauseHotkey}
          </kbd>
        </SettingRow>
        <Separator />
        <SettingRow
          title="Setup guide"
          description="Re-run the first-launch introduction and mic check."
        >
          <button
            className="text-[13px] font-medium text-foreground underline-offset-4 hover:underline"
            onClick={onRerunOnboarding}
          >
            Show again
          </button>
        </SettingRow>
      </div>

      <div className="mt-4 max-w-[560px] text-xs text-muted-foreground/60">
        input: {state.device} · profile: {state.profile}
      </div>
    </div>
  );
}

function SettingRow({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-6 py-3.5">
      <div>
        <div className="text-[13.5px] font-medium">{title}</div>
        <div className="mt-0.5 max-w-[380px] text-[12.5px] text-muted-foreground">
          {description}
        </div>
      </div>
      <div className="flex-none">{children}</div>
    </div>
  );
}
