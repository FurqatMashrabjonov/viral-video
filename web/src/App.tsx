import { useCallback, useEffect, useState } from "react"
import { Clapperboard, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Separator } from "@/components/ui/separator"
import { PipelineView } from "@/components/PipelineView"
import { ProjectList } from "@/components/ProjectList"
import { UploadCard } from "@/components/UploadCard"
import { useStream } from "@/lib/useStream"
import { api, type Project, type ProjectDetail, type Schema } from "@/lib/api"

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ProjectDetail | null>(null)

  const terminal = schema?.terminal_stages ?? []
  const { events, done } = useStream(selectedId, terminal)

  const refreshProjects = useCallback(async () => {
    setProjects(await api.projects())
  }, [])

  useEffect(() => {
    void api.schema().then(setSchema)
    void refreshProjects()
  }, [refreshProjects])

  // Reload the project whenever the stream settles, so the transcript and the
  // render list reflect what just finished.
  useEffect(() => {
    if (!selectedId) return setDetail(null)
    void api.project(selectedId).then(setDetail)
    void refreshProjects()
  }, [selectedId, done, refreshProjects])

  return (
    <div className="min-h-svh bg-background text-foreground">
      <header className="border-b">
        <div className="mx-auto flex max-w-6xl items-center gap-2 px-6 py-4">
          <Clapperboard className="size-5" />
          <span className="font-semibold tracking-tight">uzcaption</span>
          <span className="text-sm text-muted-foreground">
            o'zbek tilidagi vertikal videolar uchun
          </span>
          <Button
            variant="ghost"
            size="sm"
            className="ml-auto"
            onClick={() => void refreshProjects()}
          >
            <RefreshCw className="size-4" />
            Yangilash
          </Button>
        </div>
      </header>

      <main className="mx-auto grid max-w-6xl gap-6 px-6 py-6 lg:grid-cols-[280px_1fr]">
        <aside className="space-y-3">
          <h2 className="px-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Loyihalar
          </h2>
          <ScrollArea className="h-[60svh] pr-2">
            <ProjectList
              projects={projects}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          </ScrollArea>
        </aside>

        <section className="space-y-6">
          <UploadCard
            onUploaded={(id) => {
              setSelectedId(id)
              void refreshProjects()
            }}
          />

          {selectedId && schema && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {detail?.name ?? "Loyiha"}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <PipelineView stages={schema.stages} events={events} />

                {detail?.plan && (
                  <>
                    <Separator />
                    <div className="space-y-2">
                      {detail.plan.hook && (
                        <p className="text-sm">
                          <span className="text-muted-foreground">Hook: </span>
                          <span className="font-medium">{detail.plan.hook.text}</span>
                        </p>
                      )}
                      <p className="text-sm leading-relaxed">
                        {detail.plan.words.map((w, i) => (
                          <span
                            key={i}
                            className={
                              w.keyword
                                ? "rounded bg-emerald-500/15 px-1 font-medium text-emerald-700 dark:text-emerald-300"
                                : undefined
                            }
                          >
                            {w.word}{" "}
                          </span>
                        ))}
                      </p>
                      <p className="text-xs text-muted-foreground tabular-nums">
                        {detail.plan.words.length} so'z ·{" "}
                        {detail.plan.words.filter((w) => w.keyword).length} kalit so'z ·{" "}
                        {detail.renders.length} render
                      </p>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          )}
        </section>
      </main>
    </div>
  )
}
