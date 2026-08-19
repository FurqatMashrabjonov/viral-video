import { useState } from "react"
import { Clapperboard, Play } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ProgressStrip } from "@/components/PipelineView"
import { RenderResult } from "@/components/RenderResult"
import { api, type Render, type StageEvent } from "@/lib/api"

type Props = {
  stages: string[]
  events: StageEvent[]
  projectId: string
  settings: Record<string, unknown>
  renders: Render[]
  preview: Render | null
  previewBusy: boolean
  onBeforeAction: () => void // reopens the SSE stream so the strip covers this render too
}

/**
 * The one place a video ever shows, on purpose -- the plan explicitly called
 * out that a word preview used to open its own separate <video> inside the
 * editor tab, which meant two different players could be showing two
 * different things at once. A word preview now takes over this panel instead
 * of spawning a second one.
 */
export function VideoPanel({
  stages, events, projectId, settings, renders, preview, previewBusy, onBeforeAction,
}: Props) {
  const [busy, setBusy] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  const latest = renders[0] ?? null
  const shown = preview ?? latest

  async function renderNow() {
    setBusy(true)
    onBeforeAction()
    try {
      await api.render(projectId, settings)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="sticky top-4 space-y-3">
      <ProgressStrip stages={stages} events={events} />

      <div className="relative">
        {preview && (
          <Badge variant="secondary" className="absolute left-2 top-2 z-10">
            so'z oldindan ko'rish
          </Badge>
        )}

        {previewBusy ? (
          <div className="flex aspect-9/16 w-full items-center justify-center rounded-lg border bg-muted text-center text-sm text-muted-foreground">
            Oldindan ko'rish render qilinmoqda…
          </div>
        ) : shown?.status === "done" ? (
          <video
            key={shown.id}
            src={api.videoUrl(shown.id)}
            controls
            autoPlay={Boolean(preview)}
            playsInline
            className="aspect-9/16 w-full rounded-lg border bg-black"
          />
        ) : shown?.status === "error" ? (
          <div className="flex aspect-9/16 w-full flex-col items-center justify-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-center text-sm text-destructive">
            {shown.error ?? "Render xato bilan tugadi"}
          </div>
        ) : shown ? (
          <div className="flex aspect-9/16 w-full items-center justify-center rounded-lg border bg-muted text-sm text-muted-foreground">
            Render davom etmoqda…
          </div>
        ) : (
          <div className="flex aspect-9/16 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed text-sm text-muted-foreground">
            <Clapperboard className="size-6" />
            Hali render yo'q
          </div>
        )}
      </div>

      <Button onClick={() => void renderNow()} disabled={busy} className="w-full">
        <Play className="size-4" />
        {busy ? "Render boshlanmoqda…" : "Render qilish"}
      </Button>
      <p className="text-xs text-muted-foreground">
        Render faqat CPU sarflaydi — transkripsiya qayta ishlamaydi.
      </p>

      {renders.length > 0 && (
        <div className="space-y-2 border-t pt-3">
          <button
            type="button"
            onClick={() => setHistoryOpen((v) => !v)}
            className="text-xs text-muted-foreground underline-offset-2 hover:underline"
          >
            {historyOpen ? "Tarixni yashirish" : `Oldingi renderlar (${renders.length})`}
          </button>
          {historyOpen && <RenderResult renders={renders} showLatest={false} />}
        </div>
      )}
    </div>
  )
}
