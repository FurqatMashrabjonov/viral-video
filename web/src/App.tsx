import { useCallback, useEffect, useState } from "react"
import { Clapperboard, RefreshCw } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Toaster } from "@/components/ui/sonner"
import { EditorTab } from "@/components/EditorTab"
import { PipelineView } from "@/components/PipelineView"
import { ProjectList } from "@/components/ProjectList"
import { RenderResult } from "@/components/RenderResult"
import { SettingsPanel } from "@/components/SettingsPanel"
import { UploadCard } from "@/components/UploadCard"
import { useStream } from "@/lib/useStream"
import { api, type Project, type ProjectDetail, type Schema } from "@/lib/api"

export default function App() {
  const [schema, setSchema] = useState<Schema | null>(null)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detail, setDetail] = useState<ProjectDetail | null>(null)
  const [settings, setSettings] = useState<Record<string, boolean | number | string>>({})

  const terminal = schema?.terminal_stages ?? []
  const { events, done } = useStream(selectedId, terminal)

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
  // render list reflect what just finished.
  useEffect(() => {
    void refreshDetail()
  }, [selectedId, done, refreshDetail])

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
                <Tabs defaultValue="progress">
                  <TabsList className="grid w-full grid-cols-4">
                    <TabsTrigger value="progress">Jarayon</TabsTrigger>
                    <TabsTrigger value="sozlamalar">Sozlamalar</TabsTrigger>
                    <TabsTrigger value="natija">Natija</TabsTrigger>
                    <TabsTrigger value="transkript">Transkript</TabsTrigger>
                  </TabsList>

                  <TabsContent value="progress" className="pt-4">
                    <PipelineView stages={schema.stages} events={events} />
                  </TabsContent>

                  <TabsContent value="sozlamalar" className="pt-4">
                    <SettingsPanel
                      schema={schema}
                      projectId={selectedId}
                      values={settings}
                      onChange={setSettings}
                      onRender={() => void refreshDetail()}
                    />
                  </TabsContent>

                  <TabsContent value="natija" className="pt-4">
                    {detail ? (
                      <RenderResult renders={detail.renders} />
                    ) : (
                      <p className="text-sm text-muted-foreground">Yuklanmoqda…</p>
                    )}
                  </TabsContent>

                  <TabsContent value="transkript" className="pt-4">
                    {detail?.plan && (
                      <EditorTab
                        key={selectedId}
                        projectId={selectedId}
                        plan={detail.plan}
                        settings={settings}
                        onSaved={(plan) =>
                          setDetail((d) => (d ? { ...d, plan } : d))
                        }
                      />
                    )}
                  </TabsContent>
                </Tabs>
              </CardContent>
            </Card>
          )}
        </section>
      </main>
      <Toaster richColors />
    </div>
  )
}
