export type Project = {
  id: string
  name: string
  source_path: string
  duration: number | null
  width: number | null
  height: number | null
  fps: number | null
  status: "ingesting" | "ready" | "error"
  error: string | null
  created_at: number
}

export type Word = {
  word: string
  start: number
  end: number
  keyword: boolean
  logprob?: number | null
  low_confidence?: boolean
}
export type Hook = { text: string; start: number; end: number } | null
export type Plan = { words: Word[]; hook: Hook; zooms: unknown[]; sfx: unknown[] }

export type Render = {
  id: string
  project_id: string
  settings: Record<string, unknown>
  output_path: string | null
  ass_path: string | null
  status: "queued" | "rendering" | "done" | "error"
  progress: number
  error: string | null
  created_at: number
}

export type ProjectDetail = Project & { plan: Plan | null; renders: Render[] }

export type StageEvent = {
  id: number
  project_id: string
  render_id: string | null
  stage: string
  progress: number | null
  message: string | null
  ts: number
}

export type Field = {
  key: string
  group: string
  label: string
  type: "bool" | "number" | "select"
  default: boolean | number | string
  min?: number
  max?: number
  step?: number
  options?: string[]
  depends_on?: string
}

export type Schema = {
  fields: Field[]
  defaults: Record<string, boolean | number | string>
  stages: string[]
  terminal_stages: string[]
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  schema: () => fetch("/api/schema").then(json<Schema>),
  projects: () => fetch("/api/projects").then(json<Project[]>),
  project: (id: string) => fetch(`/api/projects/${id}`).then(json<ProjectDetail>),
  events: (id: string, after = 0) =>
    fetch(`/api/projects/${id}/events?after=${after}`).then(json<StageEvent[]>),

  upload: (file: File) => {
    const body = new FormData()
    body.append("file", file)
    return fetch("/api/projects", { method: "POST", body }).then(
      json<{ project_id: string; status: string }>,
    )
  },

  savePlan: (id: string, plan: Plan) =>
    fetch(`/api/projects/${id}/plan`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(plan),
    }).then(json<{ ok: boolean }>),

  render: (id: string, settings: Record<string, unknown>) =>
    fetch(`/api/projects/${id}/render`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }).then(json<{ render_id: string }>),

  renderStatus: (renderId: string) =>
    fetch(`/api/renders/${renderId}`).then(json<Render>),

  videoUrl: (renderId: string) => `/api/renders/${renderId}/video`,
}
