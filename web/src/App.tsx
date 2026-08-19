import { useCallback, useEffect, useState } from "react"
import { Clapperboard, Plus, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Toaster } from "@/components/ui/sonner"
import { EditorTab } from "@/components/EditorTab"
import { ProjectList } from "@/components/ProjectList"
import { SettingsPanel } from "@/components/SettingsPanel"
import { TaskRail, type RailTab } from "@/components/TaskRail"
import { UploadCard } from "@/components/UploadCard"
import { VideoPanel } from "@/components/VideoPanel"
import { useStream } from "@/lib/useStream"
import { api, type Project, type ProjectDetail, type Render, type Schema } from "@/lib/api"

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ProjectDetail | null>(null)
  const [settings, setSettings] = useState<Record<string, boolean | number | string>>({})
  const [rail, setRail] = useState<RailTab>("style")
  const [preview, setPreview] = useState<Render | null>(null)
  const [previewBusy, setPreviewBusy] = useState(false)
  // What kind of preview is on screen. A captions preview has no grade and no
  // zoom on purpose, so the badge has to say which one you are looking at --
  // otherwise a flat, ungraded picture reads as a broken render.
  const [previewLabel, setPreviewLabel] = useState("")

  const terminal = schema?.terminal_stages ?? []
  const { events, done, restart } = useStream(selectedId, terminal)

  const refreshProjects = useCallback(async () => {
    setProjects(await api.projects())
  }, [])

  const refreshDetail = useCallback(async () => {
    if (!selectedId) return setDetail(null)
    setDetail(await api.project(selectedId))
    void refreshProjects()
  }, [selectedId, refreshProjects])

  useEffect(() => {
    void api.schema().then((s) => {
      setSchema(s)
      setSettings(s.defaults)
    })
    void refreshProjects()
  }, [refreshProjects])

  // Reload the project whenever the stream settles, so the transcript and the
  // render list reflect what just finished (ingest or a render, either one).
  useEffect(() => {
    void refreshDetail()
  }, [selectedId, done, refreshDetail])

  useEffect(() => {
    setRail("style")
    setPreview(null)
    setPreviewLabel("")
    setPreviewBusy(false)
  }, [selectedId])

  function startPreview(label: string) {
    restart()
    setPreview(null)
    setPreviewLabel(label)
    setPreviewBusy(true)
  }

  function finishPreview(r: Render | null) {
    setPreview(r)
    setPreviewBusy(false)
  }

  function selectProject(id: string) {
    setSelectedId(id)
  }

  const styleFields = schema?.fields.filter((f) => f.group === "Subtitr") ?? []
  const aiFields = schema?.fields.filter((f) => f.group !== "Subtitr") ?? []

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-6 py-4">
          <Clapperboard className="size-5 shrink-0" />
          <span className="shrink-0 font-semibold tracking-tight">uzcaption</span>

          {selectedId && projects.length > 0 && (
            <Select value={selectedId} onValueChange={selectProject}>
              <SelectTrigger className="ml-2 w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}

          <div className="ml-auto flex items-center gap-2">
            {selectedId && (
              <Button variant="outline" size="sm" onClick={() => setSelectedId(null)}>
                <Plus className="size-4" />
                Yangi video
              </Button>
            )}
            <Button variant="ghost" size="sm" onClick={() => void refreshProjects()}>
              <RefreshCw className="size-4" />
              Yangilash
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-6">
        {!selectedId ? (
          <div className="mx-auto max-w-lg space-y-8">
            <UploadCard onUploaded={selectProject} />
            {projects.length > 0 && (
              <div>
                <h2 className="mb-2 px-1 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  So'nggi loyihalar
                </h2>
                <ProjectList projects={projects} selectedId={null} onSelect={selectProject} />
              </div>
            )}
          </div>
        ) : !schema || !detail ? (
          <p className="text-sm text-muted-foreground">Yuklanmoqda…</p>
        ) : (
          <div className="grid gap-6 lg:grid-cols-[160px_1fr_320px]">
            <TaskRail active={rail} onChange={setRail} />

            <div className="min-w-0">
              {rail === "style" && (
                <SettingsPanel fields={styleFields} values={settings} onChange={setSettings} />
              )}
              {rail === "ai" && (
                <SettingsPanel fields={aiFields} values={settings} onChange={setSettings} />
              )}
              {rail === "captions" &&
                (detail.plan ? (
                  <EditorTab
                    key={selectedId}
                    projectId={selectedId}
                    plan={detail.plan}
                    settings={settings}
                    onSaved={(plan) => setDetail((d) => (d ? { ...d, plan } : d))}
                    previewBusy={previewBusy}
                    onPreviewStart={startPreview}
                    onPreviewResult={finishPreview}
                  />
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Tahlil hali tugamadi — reja tayyor bo'lgach so'zlarni bu yerda tahrirlaysiz.
                  </p>
                ))}
            </div>

            <VideoPanel
              stages={schema.stages}
              events={events}
              projectId={selectedId}
              settings={settings}
              renders={detail.renders}
              preview={preview}
              previewBusy={previewBusy}
              previewLabel={previewLabel}
              onPreviewStart={startPreview}
              onPreviewResult={finishPreview}
              onBeforeAction={restart}
            />
          </div>
        )}
      </main>
      <Toaster richColors />
    </div>
  )
}
