import { useEffect, useState } from "react"
import { useParams } from "react-router-dom"
import { AppHeader } from "@/components/app-header"
import { SubjectHeader } from "@/components/subject-header"
import { SubjectNav } from "@/components/subject-nav"
import { TimelineView } from "@/components/timeline/timeline-view"
import { ProvenanceDrawer } from "@/components/provenance-drawer"
import { DemoBanner } from "@/components/demo-banner"
import { Skeleton } from "@/components/ui/skeleton"
import { getSubjectOverview, getTimeline } from "@/lib/api"
import type { SubjectOverview, TimelineEvent } from "@/lib/types"

export function SubjectPage() {
  const { subjectId: raw } = useParams()
  const subjectId = Number(raw)

  const [overview, setOverview] = useState<SubjectOverview | null>(null)
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<TimelineEvent | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all([getSubjectOverview(subjectId), getTimeline(subjectId)]).then(([ov, tl]) => {
      if (cancelled) return
      setOverview(ov)
      setEvents(tl.events)
      setLoading(false)
    })
    return () => {
      cancelled = true
    }
  }, [subjectId])

  function openEvent(event: TimelineEvent) {
    setSelected(event)
    setDrawerOpen(true)
  }

  return (
    <div className="min-h-screen">
      <AppHeader />
      <SubjectHeader subjectId={subjectId} overview={overview} loading={loading} />
      <SubjectNav subjectId={subjectId} current="timeline" />

      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <DemoBanner />
        <div className="mb-6 flex items-baseline justify-between">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">
            Patient journey
          </h2>
          {!loading ? (
            <span className="font-mono text-xs text-muted-foreground">{events.length} events</span>
          ) : null}
        </div>

        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : events.length === 0 ? (
          <p className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
            No timeline events were reconstructed for this patient.
          </p>
        ) : (
          <TimelineView subjectId={subjectId} events={events} onSelectEvent={openEvent} />
        )}
      </main>

      <ProvenanceDrawer event={selected} open={drawerOpen} onOpenChange={setDrawerOpen} />
    </div>
  )
}
