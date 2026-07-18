import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { PerimeterMap } from "@/components/PerimeterMap";
import type { AppState, EvalReport } from "@/lib/types";
import type { Act, ActiveFlashes } from "@/lib/usePerimeter";

interface Props {
  state: AppState;
  act: Act;
  flashes: ActiveFlashes;
}

export function EvaluateView({ state, act, flashes }: Props) {
  const evalDisabled =
    (state.listening || state.calibrating || !state.calibrated) && !state.evaluating;

  return (
    <div>
      <div className="flex items-center justify-between">
        <h1 className="text-[19px] font-semibold tracking-tight">Evaluate</h1>
        <Button
          variant={state.evaluating ? "outline" : "default"}
          className={state.evaluating ? "text-destructive" : ""}
          disabled={evalDisabled}
          onClick={() => act((api) => api.eval_toggle())}
        >
          {state.evaluating ? "Cancel" : "Run accuracy test"}
        </Button>
      </div>
      <p className="mt-0.5 mb-5 max-w-[640px] text-[13px] text-muted-foreground">
        Held-out test: 15 fresh taps per zone, armed one at a time. Targets: ≥80% accuracy,
        median latency &lt;200 ms. Rejected taps count as incorrect.
      </p>
      <div className="mb-2 text-center text-[11px] text-muted-foreground/50">display side</div>
      <PerimeterMap zones={state.zones} sub="eval" flashes={flashes} className="min-h-[220px]" />
      <div className="mt-2 mb-5 text-center text-[11px] text-muted-foreground/50">
        trackpad side
      </div>
      {state.report && <Report report={state.report} zones={state.zones} />}
    </div>
  );
}

function Report({ report, zones }: { report: EvalReport; zones: AppState["zones"] }) {
  const zoneName = (id: string) => zones.find((z) => z.id === id)?.name ?? id;
  const confusionLabels = [...Object.keys(report.confusion), "(rejected)"];

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <Card>
          <CardContent className="px-4">
            <div className="text-[11.5px] text-muted-foreground">accuracy</div>
            <div className="text-[22px] font-semibold tracking-tight">
              {Math.round(report.accuracy * 100)}%
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="px-4">
            <div className="text-[11.5px] text-muted-foreground">median latency</div>
            <div className="text-[22px] font-semibold tracking-tight">
              {Math.round(report.median_latency_ms)} ms
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="px-4">
            <div className="text-[11.5px] text-muted-foreground">
              verdict · {report.timestamp}
            </div>
            <div className="pt-1.5">
              {report.passed ? (
                <Badge className="border-success/40 bg-success/10 text-success" variant="outline">
                  passed
                </Badge>
              ) : (
                <Badge className="border-warning/40 bg-warning/10 text-warning" variant="outline">
                  missed targets
                </Badge>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="px-4">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>zone</TableHead>
                <TableHead className="text-right">correct</TableHead>
                <TableHead className="text-right">accuracy</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(report.per_zone).map(([zid, z]) => (
                <TableRow key={zid}>
                  <TableCell>{zoneName(zid)}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {z.correct}/{z.taps}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {Math.round(z.accuracy * 100)}%
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="px-4">
          <div className="mb-1.5 text-xs text-muted-foreground">
            confusion (rows = expected)
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead />
                {confusionLabels.map((l) => (
                  <TableHead key={l} className="text-right">
                    {l === "(rejected)" ? "rej." : zoneName(l)}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {Object.entries(report.confusion).map(([expected, row]) => (
                <TableRow key={expected}>
                  <TableCell>{zoneName(expected)}</TableCell>
                  {confusionLabels.map((p) => (
                    <TableCell key={p} className="text-right tabular-nums">
                      {row[p] ?? 0}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
