import { useState } from "react"
import { Play } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Separator } from "@/components/ui/separator"
import { Slider } from "@/components/ui/slider"
import { Switch } from "@/components/ui/switch"
import { api, type Field, type Render, type Schema } from "@/lib/api"

type Values = Record<string, boolean | number | string>

type Props = {
  schema: Schema
  projectId: string
  onRender: (render: Render) => void
}

export function SettingsPanel({ schema, projectId, onRender }: Props) {
  const [values, setValues] = useState<Values>(schema.defaults)
  const [busy, setBusy] = useState(false)

  const groups: [string, Field[]][] = []
  for (const field of schema.fields) {
    const group = groups.find(([name]) => name === field.group)
    if (group) group[1].push(field)
    else groups.push([field.group, [field]])
  }

  function set(key: string, value: boolean | number | string) {
    setValues((v) => ({ ...v, [key]: value }))
  }

  async function renderNow() {
    setBusy(true)
    try {
      const { render_id } = await api.render(projectId, values)
      onRender({ id: render_id, settings: values } as Render)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-6">
      {groups.map(([group, fields]) => (
        <fieldset key={group}>
          <legend className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {group}
          </legend>
          <div className="mt-2 space-y-4">
            {fields.map((f) => {
              const parent = f.depends_on
              const disabled = parent ? !values[parent] : false

              return (
                <div key={f.key} className="flex items-center justify-between gap-4">
                  <Label
                    htmlFor={f.key}
                    className={disabled ? "text-muted-foreground/50" : undefined}
                  >
                    {f.label}
                  </Label>

                  {f.type === "bool" && (
                    <Switch
                      id={f.key}
                      checked={Boolean(values[f.key])}
                      onCheckedChange={(v) => set(f.key, v)}
                    />
                  )}

                  {f.type === "number" && (
                    <div className="flex w-48 items-center gap-3">
                      <Slider
                        id={f.key}
                        disabled={disabled}
                        min={f.min}
                        max={f.max}
                        step={f.step}
                        value={[Number(values[f.key])]}
                        onValueChange={([v]) => set(f.key, v)}
                      />
                      <span
                        className={
                          "w-12 text-right text-xs tabular-nums " +
                          (disabled ? "text-muted-foreground/50" : "text-muted-foreground")
                        }
                      >
                        {Number(values[f.key]).toFixed(
                          (f.step ?? 1) < 1 ? 2 : 0,
                        )}
                      </span>
                    </div>
                  )}

                  {f.type === "select" && (
                    <Select
                      disabled={disabled}
                      value={String(values[f.key])}
                      onValueChange={(v) => set(f.key, v)}
                    >
                      <SelectTrigger className="w-48">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {(f.options ?? []).map((option) => (
                          <SelectItem key={option} value={option}>
                            {option}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>
              )
            })}
          </div>
        </fieldset>
      ))}

      <Separator />

      <Button onClick={() => void renderNow()} disabled={busy} className="w-full">
        <Play className="size-4" />
        {busy ? "Render boshlanmoqda…" : "Render qilish"}
      </Button>
      <p className="text-xs text-muted-foreground">
        Render faqat CPU sarflaydi — transkripsiya qayta ishlamaydi.
      </p>
    </div>
  )
}
