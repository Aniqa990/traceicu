import { useEffect, useState } from "react"
import { Link, useParams } from "react-router-dom"
import { ChevronLeft, FileText } from "lucide-react"
import { AppHeader } from "@/components/app-header"
import { ProvenanceDrawer } from "@/components/provenance-drawer"
import { DemoBanner } from "@/components/demo-banner"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { eventMeta } from "@/lib/event-meta"
import { formatTime } from "@/lib/utils"
import { getEvent } from "@/lib/api"
import type { TimelineEvent } from "@/lib/types"

export function ClusterPage() {
  const { subjectId: raw, eventId } = useParams()
  const subjectId = Number(raw)

  const [event, setEvent] = useState<TimelineEvent | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<TimelineEvent | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    getEvent(subjectId, eventId ?? "")
      .then((e) => {
        if (!cancelled) setEvent(e)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [subjectId, eventId])

  const children = event?.children ?? []
  const meta = event ? eventMeta(event.event_type) : null
  const Icon = meta?.icon

  function openRow(child: TimelineEvent) {
    setSelected(child)
    setDrawerOpen(true)
  }

  return (
    <div className="min-h-screen">
      <AppHeader />

      <main className="mx-auto max-w-4xl px-4 py-8 sm:px-6">
        <Link
          to={`/subjects/${subjectId}`}
          className="mb-5 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="size-4" /> Timeline
        </Link>

        <DemoBanner />

        {loading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-64 w-full" />
          </div>
        ) : !event ? (
          <p className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
            Event not found.
          </p>
        ) : (
          <>
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2.5">
                {Icon ? (
                  <span className="flex size-9 items-center justify-center rounded-md bg-primary/12">
                    <Icon className={`size-4 ${meta?.tone}`} />
                  </span>
                ) : null}
                <div>
                  <h1 className="text-lg font-semibold tracking-tight">{event.label}</h1>
                  <p className="text-sm text-muted-foreground">
                    {children.length} observation(s)
                    {children.length > 0
                      ? ` · ${formatTime(children[0].event_time)} – ${formatTime(
                          children[children.length - 1].event_time,
                        )}`
                      : ""}
                  </p>
                </div>
              </div>
              {event.derivation_rule ? (
                <Badge variant="outline" className="max-w-xs text-pretty">
                  {event.derivation_rule}
                </Badge>
              ) : null}
            </div>

            <div className="overflow-hidden rounded-lg border border-border bg-card">
              <Table>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead>Concept</TableHead>
                    <TableHead className="text-right">Value</TableHead>
                    <TableHead>Unit</TableHead>
                    <TableHead className="text-right">Time</TableHead>
                    <TableHead className="w-10" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {children.map((child) => (
                    <TableRow
                      key={child.event_id}
                      onClick={() => openRow(child)}
                      className="cursor-pointer"
                    >
                      <TableCell className="font-medium">{child.label}</TableCell>
                      <TableCell className="text-right font-mono">{child.value ?? "—"}</TableCell>
                      <TableCell className="font-mono text-muted-foreground">
                        {child.unit ?? ""}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {formatTime(child.event_time)}
                      </TableCell>
                      <TableCell>
                        <FileText className="size-3.5 text-muted-foreground" />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
              Select any row to open its source row in the provenance drawer.
            </p>
          </>
        )}
      </main>

      <ProvenanceDrawer event={selected} open={drawerOpen} onOpenChange={setDrawerOpen} />
    </div>
  )
}
