import { Download } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api, type Render } from "@/lib/api"

const STATUS: Record<Render["status"], { label: string; variant: "default" | "secondary" | "destructive" }> = {
  queued: { label: "navbatda", variant: "secondary" },
  rendering: { label: "rendermoda", variant: "secondary" },
  done: { label: "tayyor", variant: "default" },
  error: { label: "xato", variant: "destructive" },
}

type Props = {
  renders: Render[]
  // The always-visible video panel already shows the latest render; a caller
  // embedding this as a history list underneath sets this to skip repeating it.
  showLatest?: boolean
}

export function RenderResult({ renders, showLatest = true }: Props) {
  if (renders.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Hali render yo'q — sozlamalarni tanlab render qiling.
      </p>
    )
  }

  const done = renders.filter((r) => r.status === "done")
  const latest = renders[0]

  return (
    <div className="space-y-4">
      {showLatest && latest.status === "done" && (
        <video
          key={latest.id}
          src={api.videoUrl(latest.id)}
          controls
          playsInline
          className="aspect-9/16 w-full max-w-xs rounded-lg border bg-black"
        />
      )}

      {showLatest && latest.status !== "done" && latest.status !== "error" && (
        <p className="text-sm text-muted-foreground">Render davom etmoqda…</p>
      )}
      {showLatest && latest.status === "error" && (
        <p className="text-sm text-destructive">{latest.error ?? "Render xato bilan tugadi"}</p>
      )}

      <ul className="space-y-1.5">
        {renders.map((r) => {
          const status = STATUS[r.status]
          return (
            <li
              key={r.id}
              className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
            >
              <span className="flex items-center gap-2">
                <Badge variant={status.variant} className="text-[11px]">
                  {status.label}
                </Badge>
                <span className="text-xs text-muted-foreground tabular-nums">
                  {new Date(r.created_at * 1000).toLocaleTimeString("uz-UZ")}
                </span>
              </span>
              {r.status === "done" && (
                <Button variant="ghost" size="icon" className="size-7" asChild>
                  <a href={api.videoUrl(r.id)} download>
                    <Download className="size-3.5" />
                  </a>
                </Button>
              )}
            </li>
          )
        })}
      </ul>

      <p className="text-xs text-muted-foreground">
        {done.length} ta tayyor render. Har birida o'sha paytdagi sozlamalar saqlangan.
      </p>
    </div>
  )
}
