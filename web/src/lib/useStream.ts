import { useCallback, useEffect, useRef, useState } from "react"
import type { StageEvent } from "./api"

/**
 * Follow a project's pipeline over SSE.
 *
 * EventSource reconnects on its own and replays Last-Event-ID, so nothing is
 * lost across a dropped connection -- that is why the server journals events
 * rather than broadcasting them. The stream is closed by the server on a
 * terminal stage; the browser would otherwise reconnect forever.
 *
 * A render is its own terminal event on the same project stream, so once one
 * render finishes the stream is closed for good -- triggering a second render
 * (or a segment preview) would otherwise show no live progress at all. Call
 * `restart()` right before starting a new render/preview to reopen it.
 * Restart reconnects with `after=<last seen id>`, not from scratch: a plain
 * reconnect replays the whole history and would immediately hit that first
 * old "done" and close again before the new render has written anything.
 */
export function useStream(projectId: string | null, terminalStages: string[]) {
  const [events, setEvents] = useState<StageEvent[]>([])
  const source = useRef<EventSource | null>(null)
  const lastId = useRef(0)

  const connect = useCallback((after = 0) => {
    source.current?.close()
    if (!projectId) return

    const es = new EventSource(`/api/projects/${projectId}/stream?after=${after}`)
    source.current = es

    es.addEventListener("stage", (e) => {
      const event = JSON.parse((e as MessageEvent).data) as StageEvent
      lastId.current = Math.max(lastId.current, event.id)
      setEvents((prev) => (prev.some((p) => p.id === event.id) ? prev : [...prev, event]))
      if (terminalStages.includes(event.stage)) es.close()
    })

    // The server closes the stream at a terminal stage, which the browser reads
    // as a failure and would retry forever. Close it here instead.
    es.onerror = () => es.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, terminalStages.join(",")])

  useEffect(() => {
    setEvents([])
    lastId.current = 0
    connect(0)
    return () => source.current?.close()
  }, [connect])

  const last = events[events.length - 1]
  return {
    events,
    stage: last?.stage ?? null,
    progress: [...events].reverse().find((e) => e.progress !== null)?.progress ?? null,
    done: last ? terminalStages.includes(last.stage) : false,
    close: () => source.current?.close(),
    restart: () => connect(lastId.current),
  }
}
