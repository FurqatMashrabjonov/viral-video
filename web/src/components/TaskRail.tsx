import type { LucideIcon } from "lucide-react"
import { Captions, Sparkles, SwatchBook } from "lucide-react"
import { cn } from "@/lib/utils"

export type RailTab = "style" | "captions" | "ai"

const TABS: { id: RailTab; label: string; icon: LucideIcon }[] = [
  { id: "style", label: "Uslub", icon: SwatchBook },
  { id: "captions", label: "Captions", icon: Captions },
  { id: "ai", label: "AI vositalar", icon: Sparkles },
]

type Props = { active: RailTab; onChange: (tab: RailTab) => void }

/** Task-oriented left rail -- what you're editing, not which pipeline stage
 * you're on. The video panel next to it never depends on which tab is active. */
export function TaskRail({ active, onChange }: Props) {
  return (
    <nav className="flex gap-1 overflow-x-auto lg:flex-col lg:gap-0.5 lg:overflow-visible">
      {TABS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          type="button"
          onClick={() => onChange(id)}
          className={cn(
            "flex shrink-0 items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors lg:w-full",
            active === id
              ? "bg-accent font-medium text-accent-foreground"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          <Icon className="size-4 shrink-0" />
          <span className="whitespace-nowrap">{label}</span>
        </button>
      ))}
    </nav>
  )
}
