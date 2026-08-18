import { useRef, useState } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { cn } from "@/lib/utils"
import { api } from "@/lib/api"

export function UploadCard({ onUploaded }: { onUploaded: (projectId: string) => void }) {
  const input = useRef<HTMLInputElement>(null)
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function send(file: File) {
    setBusy(true)
    setError(null)
    try {
      const { project_id } = await api.upload(file)
      onUploaded(project_id)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Yuklab bo'lmadi")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardContent
        className={cn(
          "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed py-10 text-center transition-colors",
          dragging ? "border-primary bg-primary/5" : "border-transparent",
        )}
        onDragOver={(e) => {
          e.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          const file = e.dataTransfer.files[0]
          if (file) void send(file)
        }}
      >
        <Upload className="size-7 text-muted-foreground" />
        <div>
          <p className="font-medium">Vertikal videoni bu yerga tashlang</p>
          <p className="text-sm text-muted-foreground">9:16, 15–90 soniya</p>
        </div>

        <input
          ref={input}
          type="file"
          accept="video/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) void send(file)
            e.target.value = ""
          }}
        />
        <Button onClick={() => input.current?.click()} disabled={busy}>
          {busy ? "Yuklanmoqda…" : "Fayl tanlash"}
        </Button>

        <p className="max-w-sm text-xs text-muted-foreground">
          Yuklash transkripsiyani ishga tushiradi — bu videoning eng qimmat qismi.
          Sozlamalarni keyin bepul o'zgartirasiz.
        </p>

        {error && <p className="text-sm text-destructive">{error}</p>}
      </CardContent>
    </Card>
  )
}
