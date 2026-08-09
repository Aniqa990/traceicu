import { Info } from "lucide-react"
import { usingDemoData } from "@/lib/api"

/**
 * Shown when the FastAPI backend was unreachable and the UI fell back to
 * bundled demo fixtures. `usingDemoData` is a live module binding, so it
 * reflects the latest fetch outcome on each render.
 */
export function DemoBanner() {
  if (!usingDemoData) return null
  return (
    <div className="mb-6 flex items-start gap-2.5 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-warning-foreground">
      <Info className="mt-0.5 size-4 shrink-0" />
      <p className="leading-relaxed">
        <span className="font-medium">Demo data.</span> The TraceICU API is unreachable, so bundled
        sample records for patient 10006 are shown. Set{" "}
        <code className="rounded bg-warning/20 px-1 font-mono text-xs">VITE_API_BASE_URL</code> to a
        running backend for live data.
      </p>
    </div>
  )
}
