import { useState } from "react"
import { Eye, Save } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Separator } from "@/components/ui/separator"
import { api, type Plan, type Render, type Word } from "@/lib/api"
import { cn } from "@/lib/utils"

const PREVIEW_BEFORE = 1.0
const PREVIEW_AFTER = 4.0

type Props = {
  projectId: string
  plan: Plan
  settings: Record<string, unknown>
  onSaved: (plan: Plan) => void
}

export function EditorTab({ projectId, plan, settings, onSaved }: Props) {
  const [words, setWords] = useState<Word[]>(plan.words)
  const [hook, setHook] = useState(plan.hook?.text ?? "")
  const [selected, setSelected] = useState<number | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [dirty, setDirty] = useState(false)
  const [preview, setPreview] = useState<Render | null>(null)
  const [previewBusy, setPreviewBusy] = useState(false)

  async function save() {
    const next = { ...plan, hook: hook.trim() ? { text: hook.trim(), start: 0, end: 3 } : null, words }
    await api.savePlan(projectId, next)
    setDirty(false)
    onSaved(next)
    toast.success("Reja saqlandi")
  }

  async function previewAround() {
    if (selected === null) return
    const word = words[selected]
    setPreviewBusy(true)
    setPreview(null)
    try {
      const t0 = Math.max(0, word.start - PREVIEW_BEFORE)
      const t1 = word.start + PREVIEW_AFTER
      const { render_id } = await api.render(projectId, { settings, segment: [t0, t1] })

      let row: Render | null = null
      for (let i = 0; i < 90 && row?.status !== "done" && row?.status !== "error"; i++) {
        await new Promise((r) => setTimeout(r, 500))
        row = await api.renderStatus(render_id)
      }
      setPreview(row)
      if (row?.status !== "done") toast.error("Oldindan ko'rish chiqmadi")
    } finally {
      setPreviewBusy(false)
    }
  }

  function toggleKeyword(i: number) {
    setWords((ws) => ws.map((w, j) => (j === i ? { ...w, keyword: !w.keyword } : w)))
    setDirty(true)
  }

  function editWord(i: number, text: string) {
    setWords((ws) => ws.map((w, j) => (j === i ? { ...w, word: text } : w)))
    setDirty(true)
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Hook
        </label>
        <Input
          value={hook}
          onChange={(e) => {
            setHook(e.target.value)
            setDirty(true)
          }}
          placeholder="Hook matni (bo'sh qoldirilsa ko'rsatilmaydi)"
        />
      </div>

      <Separator />

      <div>
        <p className="mb-2 text-xs font-medium uppercase tracking-wider text-muted-foreground">
          So'zlar — bosish: kalit so'z · ikki marta bosish: matn
        </p>
        <p className="flex flex-wrap gap-1.5">
          {words.map((w, i) => (
            <span key={i}>
              {editing === i ? (
                <input
                  autoFocus
                  value={w.word}
                  className={cn(
                    "w-24 rounded border border-input bg-background px-1.5 py-0.5 text-sm",
                    w.keyword && "ring-2 ring-emerald-500",
                  )}
                  onChange={(e) => editWord(i, e.target.value)}
                  onBlur={() => setEditing(null)}
                  onKeyDown={(e) => e.key === "Enter" && setEditing(null)}
                />
              ) : (
                <button
                  type="button"
                  onClick={() => (selected === i ? toggleKeyword(i) : setSelected(i))}
                  onDoubleClick={() => {
                    setSelected(i)
                    setEditing(i)
                  }}
                  className={cn(
                    "rounded px-1.5 py-0.5 text-sm transition-colors",
                    w.keyword
                      ? "bg-emerald-500/15 font-medium text-emerald-700 dark:text-emerald-300"
                      : "hover:bg-accent",
                    w.low_confidence &&
                      "underline decoration-wavy decoration-amber-500 underline-offset-4",
                    selected === i && "ring-2 ring-primary",
                  )}
                  title={
                    w.low_confidence
                      ? "Scribe bu so'zga unchalik ishonmadi — tekshirib ko'ring"
                      : w.keyword
                        ? "Kalit so'zni o'chirish"
                        : "Kalit so'z qilish"
                  }
                >
                  {w.word}
                </button>
              )}
            </span>
          ))}
        </p>
        <p className="mt-2 text-xs text-muted-foreground tabular-nums">
          {words.length} so'z · {words.filter((w) => w.keyword).length} kalit
          {words.some((w) => w.low_confidence) &&
            ` · ${words.filter((w) => w.low_confidence).length} shubhali (tagi to'lqinli chizilgan)`}
        </p>
      </div>

      <Separator />

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => void save()} disabled={!dirty} variant="default">
          <Save className="size-4" />
          {dirty ? "Saqlash" : "Saqlandi"}
        </Button>
        <Button
          onClick={() => void previewAround()}
          disabled={selected === null || previewBusy}
          variant="outline"
        >
          <Eye className="size-4" />
          {previewBusy
            ? "Render qilinmoqda…"
            : selected !== null
              ? `Oldindan ko'rish: «${words[selected].word}»`
              : "So'z tanlang"}
        </Button>
      </div>

      {preview?.status === "done" && (
        <video
          key={preview.id}
          src={api.videoUrl(preview.id)}
          controls
          autoPlay
          playsInline
          className="aspect-9/16 w-full max-w-xs rounded-lg border bg-black"
        />
      )}

      {preview?.status === "error" && (
        <p className="text-sm text-destructive">{preview.error}</p>
      )}

      <p className="text-xs text-muted-foreground">
        Oldindan ko'rish tanlangan so'z atrofidagi 5 soniyani xuddi yakuniy
        video qanday chiqsa shunday render qiladi — taxminiy ko'rinish emas.
      </p>
    </div>
  )
}
