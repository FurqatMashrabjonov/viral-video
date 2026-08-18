import { useEffect, useRef, useState } from "react"
import type { StageEvent } from "./api"

/**
 * Follow a project's pipeline over SSE.
 *
 * EventSource reconnects on its own and replays Last-Event-ID, so nothing is
 * lost across a dropped connection -- that is why the server journals events
 * rather than broadcasting them. The stream is closed by the server on a
 * terminal stage; the browser would otherwise reconnect forever.
 */
export function useStream(projectId: string | null, terminalStages: string[]) {
  const [events, setEvents] = useState<StageEvent[]>([])
  const source = useRef<EventSource | null>(null)

  useEffect(() => {
    setEvents([])
    if (!projectId) return

    const es = new EventSource(`/api/projects/${projectId}/stream`)
    source.current = es

    es.addEventListener("stage", (e) => {
      const event = JSON.parse((e as MessageEvent).data) as StageEvent
      setEvents((prev) => (prev.some((p) => p.id === event.id) ? prev : [...prev, event]))
      if (terminalStages.includes(event.stage)) es.close()
    })

    // The server closes the stream at a terminal stage, which the browser reads
    // as a failure and would retry forever. Close it here instead.
    es.onerror = () => es.close()

    return () => es.close()
  }, [projectId, terminalStages.join(",")])

  const last = events[events.length - 1]
  return {
    events,
    stage: last?.stage ?? null,
    progress: [...events].reverse().find((e) => e.progress !== null)?.progress ?? null,
    done: last ? terminalStages.includes(last.stage) : false,
    close: () => source.current?.close(),
  }
}
