import { useState } from "react"
import { Check, ChevronDown, CircleDashed, Loader2, TriangleAlert } from "lucide-react"
import { Progress } from "@/components/ui/progress"
import { cn } from "@/lib/utils"
import type { StageEvent } from "@/lib/api"

export const STAGE_LABELS: Record<string, string> = {
  probe: "Video tekshirilmoqda",
  audio: "Audio ajratilmoqda",
  transcribe: "Transkripsiya (Scribe)",
  plan: "Tahrir rejasi",
  enrich: "Hook va kalit so'zlar",
  ready: "Tahlil tayyor",
  subtitles: "Subtitr qurilmoqda",
  render: "Render",
  done: "Tayyor",
}

// The slow ones. Everything else is over in well under a second, so a spinner
// on them would only flicker.
const SLOW = new Set(["transcribe", "enrich", "render"])

type Props = { stages: string[]; events: StageEvent[]; className?: string }

export function PipelineView({ stages, events, className }: Props) {
  const seen = new Set(events.map((e) => e.stage))
  const failed = events.find((e) => e.stage === "error")
  const current = events[events.length - 1]?.stage ?? null
  const progress = [...events].reverse().find((e) => e.progress !== null)?.progress ?? null

  return (
    <ol className={cn("space-y-1", className)}>
      {stages.map((stage) => {
        const isDone = seen.has(stage) && stage !== current
        const isCurrent = stage === current && !failed
        const showBar = isCurrent && stage === "render" && progress !== null

        return (
          <li key={stage} className="flex items-center gap-3 py-1.5 text-sm">
            <span className="flex size-5 shrink-0 items-center justify-center">
              {failed && isCurrent ? (
                <TriangleAlert className="size-4 text-destructive" />
              ) : isDone ? (
                <Check className="size-4 text-emerald-600 dark:text-emerald-400" />
              ) : isCurrent ? (
                <Loader2 className="size-4 animate-spin text-primary" />
              ) : (
                <CircleDashed className="size-4 text-muted-foreground/40" />
              )}
            </span>

            <span
              className={cn(
                "flex-1 tabular-nums",
                isCurrent && "font-medium",
                !isDone && !isCurrent && "text-muted-foreground/60",
              )}
            >
              {STAGE_LABELS[stage] ?? stage}
              {SLOW.has(stage) && !isDone && !isCurrent && (
                <span className="ml-2 text-xs text-muted-foreground/50">sekin</span>
              )}
            </span>

            {showBar && (
              <span className="flex w-40 items-center gap-2">
                <Progress value={progress * 100} className="h-1.5" />
                <span className="w-10 text-right text-xs tabular-nums text-muted-foreground">
                  {Math.round(progress * 100)}%
                </span>
              </span>
            )}
          </li>
        )
      })}

      {failed?.message && (
        <li className="mt-3 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {failed.message}
        </li>
      )}
    </ol>
  )
}

/**
 * A one-line status above the video: current stage + a thin bar, click to
 * expand the full checklist. Nothing to show once the pipeline has settled
 * (ready with no active render, or no events at all) -- the video itself is
 * the status at that point.
 */
// Stages that mean "nothing is happening right now": ingest settles on
// "ready", a render settles on "done". Anything else on the wire is
// in-progress and worth a strip. ("error" is deliberately not resting -- it
// stays visible so a failure doesn't just look like a quiet finish.)
const RESTING = new Set(["ready", "done"])

export function ProgressStrip({ stages, events, className }: Props) {
  const [open, setOpen] = useState(false)
  const last = events[events.length - 1]
  const active = last && !RESTING.has(last.stage)

  if (!active) return null

  const failed = last.stage === "error"
  const progress = [...events].reverse().find((e) => e.progress !== null)?.progress ?? null
  const stageIndex = Math.max(0, stages.indexOf(last.stage))
  const fraction = failed
    ? 1
    : progress !== null
      ? (stageIndex + progress) / stages.length
      : stageIndex / stages.length

  return (
    <div className={cn("rounded-md border bg-card", className)}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left"
      >
        {failed ? (
          <TriangleAlert className="size-3.5 shrink-0 text-destructive" />
        ) : (
          <Loader2 className="size-3.5 shrink-0 animate-spin text-primary" />
        )}
        <span className={cn("flex-1 text-xs font-medium", failed && "text-destructive")}>
          {failed ? "Xato" : STAGE_LABELS[last.stage] ?? last.stage}
        </span>
        <Progress value={fraction * 100} className="h-1 w-16" />
        <ChevronDown className={cn("size-3.5 text-muted-foreground transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="border-t px-3 pb-2">
          <PipelineView stages={stages} events={events} />
        </div>
      )}
    </div>
  )
}
