import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import type { Project } from "@/lib/api"

const STATUS: Record<Project["status"], { label: string; variant: "default" | "secondary" | "destructive" }> = {
  ingesting: { label: "tahlil qilinmoqda", variant: "secondary" },
  ready: { label: "tayyor", variant: "default" },
  error: { label: "xato", variant: "destructive" },
}

function ago(ts: number) {
  const s = Math.max(0, Date.now() / 1000 - ts)
  if (s < 60) return "hozir"
  if (s < 3600) return `${Math.floor(s / 60)} daq oldin`
  if (s < 86400) return `${Math.floor(s / 3600)} soat oldin`
  return `${Math.floor(s / 86400)} kun oldin`
}

type Props = {
  projects: Project[]
  selectedId: string | null
  onSelect: (id: string) => void
}

export function ProjectList({ projects, selectedId, onSelect }: Props) {
  if (projects.length === 0) {
    return (
      <p className="px-3 py-8 text-center text-sm text-muted-foreground">
        Hali loyiha yo'q
      </p>
    )
  }

  return (
    <ul className="space-y-1">
      {projects.map((p) => {
        const status = STATUS[p.status] ?? STATUS.ingesting
        return (
          <li key={p.id}>
            <Button
              variant="ghost"
              onClick={() => onSelect(p.id)}
              className={cn(
                "h-auto w-full justify-start gap-3 px-3 py-2.5 text-left",
                selectedId === p.id && "bg-accent",
              )}
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-medium">{p.name}</span>
                <span className="block text-xs text-muted-foreground tabular-nums">
                  {ago(p.created_at)}
                  {p.duration ? ` · ${p.duration.toFixed(1)}s` : ""}
                </span>
              </span>
              <Badge variant={status.variant} className="shrink-0 text-[11px]">
                {status.label}
              </Badge>
            </Button>
          </li>
        )
      })}
    </ul>
  )
}
