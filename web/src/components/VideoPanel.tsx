import { useState } from "react"
import { Clapperboard, Play, Subtitles } from "lucide-react"
import { toast } from "sonner"

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
  previewLabel: string
  onPreviewStart: (label: string) => void
  onPreviewResult: (render: Render | null) => void
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
  stages, events, projectId, settings, renders, preview, previewBusy, previewLabel,
  onPreviewStart, onPreviewResult, onBeforeAction,
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

  // Whole video, subtitles only: no grade, no zoom, no B-roll, half height,
  // ultrafast encode. Measured end to end on a 30s clip: 17.5s full render vs
  // 1.8s preview, which is what makes it usable as a "did I fix that typo /
  // does this style read" loop.
  async function previewCaptions() {
    onPreviewStart("faqat subtitr — rang va zoom yo'q")
    try {
      const row = await api.renderAndWait(projectId, settings, { captions_only: true })
      onPreviewResult(row)
      if (row?.status !== "done") toast.error("Subtitr ko'rish chiqmadi")
    } catch (e) {
      onPreviewResult(null)
      toast.error(e instanceof Error ? e.message : "Subtitr ko'rish chiqmadi")
    }
  }

  return (
    <div className="sticky top-4 space-y-3">
      <ProgressStrip stages={stages} events={events} />

      <div className="relative">
        {preview && previewLabel && (
          <Badge variant="secondary" className="absolute left-2 top-2 z-10">
            {previewLabel}
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

      <Button
        onClick={() => void previewCaptions()}
        disabled={busy || previewBusy}
        variant="outline"
        className="w-full"
      >
        <Subtitles className="size-4" />
        {previewBusy ? "Tayyorlanmoqda…" : "Subtitrni tez ko'rish"}
      </Button>
      <Button onClick={() => void renderNow()} disabled={busy || previewBusy} className="w-full">
        <Play className="size-4" />
        {busy ? "Render boshlanmoqda…" : "Render qilish"}
      </Button>
      <p className="text-xs text-muted-foreground">
        <strong>Subtitrni tez ko'rish</strong> — butun videoni faqat subtitr bilan, rang/zoom/B-roll'siz
        va past sifatda chiqaradi (30 soniyalik videoda 17.5s o'rniga 1.8s). Subtitrning o'zi
        yakuniy videodagi bilan bir xil — matn, vaqt va uslubni shu yerda tekshiring.
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
