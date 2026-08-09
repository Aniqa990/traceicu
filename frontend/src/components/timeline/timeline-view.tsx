import { useNavigate } from "react-router-dom"
import { ChevronRight, FileText } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { eventMeta, isCluster } from "@/lib/event-meta"
import { formatDate, formatTime } from "@/lib/utils"
import type { TimelineEvent } from "@/lib/types"

export function TimelineView({
  subjectId,
  events,
  onSelectEvent,
}: {
  subjectId: number
  events: TimelineEvent[]
  onSelectEvent: (event: TimelineEvent) => void
}) {
  const navigate = useNavigate()

  // Insert date separators when the calendar day changes.
  let lastDay = ""

  return (
    <ol className="relative ml-1">
      {/* continuous rail */}
      <span
        aria-hidden
        className="absolute bottom-4 left-[7px] top-4 w-px bg-border"
      />
      {events.map((event) => {
        const meta = eventMeta(event.event_type)
        const Icon = meta.icon
        const cluster = isCluster(event)
        const count = event.child_count ?? event.children_total ?? event.children?.length
        const day = formatDate(event.event_time)
        const showDay = day !== lastDay
        lastDay = day

        return (
          <li key={event.event_id} className="relative">
            {showDay ? (
              <div className="flex items-center gap-2 py-3 pl-7">
                <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {day}
                </span>
              </div>
            ) : null}

            <div className="relative pl-7">
              {/* rail dot */}
              <span
                aria-hidden
                className={`absolute left-0 top-3.5 z-10 flex size-3.5 items-center justify-center rounded-full border-2 border-background bg-card ${meta.tone}`}
              >
                <span className="size-1.5 rounded-full bg-current" />
              </span>

              <button
                type="button"
                onClick={() =>
                  cluster
                    ? navigate(`/subjects/${subjectId}/events/${encodeURIComponent(event.event_id)}`)
                    : onSelectEvent(event)
                }
                className="group mb-2 flex w-full items-center gap-3 rounded-lg border border-border bg-card px-3.5 py-3 text-left transition-colors hover:border-primary/40 hover:bg-accent/40"
              >
                <span className="w-11 shrink-0 font-mono text-xs text-muted-foreground">
                  {formatTime(event.event_time) || "—"}
                </span>

                <Icon className={`size-4 shrink-0 ${meta.tone}`} />

                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span className="truncate text-sm font-medium text-foreground">
                      {event.label}
                    </span>
                    {event.value ? (
                      <span className="font-mono text-sm text-muted-foreground">
                        {event.value}
                        {event.unit ? ` ${event.unit}` : ""}
                      </span>
                    ) : null}
                  </span>
                  {event.event_subtype ? (
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                      {event.event_subtype}
                    </span>
                  ) : null}
                </span>

                {cluster ? (
                  <span className="flex shrink-0 items-center gap-1.5">
                    {typeof count === "number" ? (
                      <Badge variant="default">{count} items</Badge>
                    ) : null}
                    <ChevronRight className="size-4 text-muted-foreground transition-transform group-hover:translate-x-0.5" />
                  </span>
                ) : (
                  <span className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100">
                    <FileText className="size-3.5" />
                    source
                  </span>
                )}
              </button>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
