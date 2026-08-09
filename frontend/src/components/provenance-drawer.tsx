import { Database, FileText } from "lucide-react"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"
import { Badge } from "@/components/ui/badge"
import { eventMeta } from "@/lib/event-meta"
import { formatDateTime } from "@/lib/utils"
import type { TimelineEvent } from "@/lib/types"

interface ProvenanceDrawerProps {
  event: TimelineEvent | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Human-friendly hint for which source field carries the timestamp. */
function timeField(fields: Record<string, unknown>): string | null {
  for (const key of ["charttime", "starttime", "intime", "admittime", "chartdate", "storetime"]) {
    if (key in fields) return key
  }
  return null
}

export function ProvenanceDrawer({ event, open, onOpenChange }: ProvenanceDrawerProps) {
  const meta = event ? eventMeta(event.event_type) : null
  const Icon = meta?.icon

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="overflow-y-auto scroll-thin">
        <SheetHeader>
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-primary">
            <FileText className="size-3.5" />
            Source evidence
          </div>
          <SheetTitle className="flex items-center gap-2 pt-1">
            {Icon ? <Icon className={`size-4 ${meta?.tone}`} /> : null}
            {event?.label ?? "—"}
          </SheetTitle>
          {event?.value ? (
            <SheetDescription className="font-mono text-base text-foreground">
              {event.value}
              {event.unit ? <span className="text-muted-foreground"> {event.unit}</span> : null}
            </SheetDescription>
          ) : (
            <SheetDescription>{formatDateTime(event?.event_time)}</SheetDescription>
          )}
        </SheetHeader>

        <div className="flex-1 space-y-6 p-5">
          {event?.is_derived ? (
            <div className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
              <span className="font-medium text-foreground">Derived event.</span>{" "}
              {event.derivation_rule ??
                "Computed grouping of source rows; each member below traces to its own row."}
            </div>
          ) : null}

          {(event?.evidence ?? []).length === 0 && !event?.is_derived ? (
            <p className="text-sm text-muted-foreground">
              No source rows are attached to this event.
            </p>
          ) : null}

          {(event?.evidence ?? []).map((ev, idx) => {
            const tf = timeField(ev.source_fields)
            const entries = Object.entries(ev.source_fields)
            return (
              <div key={idx} className="space-y-3">
                <div className="space-y-2">
                  <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <Database className="size-3.5" />
                    Source
                  </div>
                  <dl className="grid grid-cols-[7rem_1fr] gap-y-1.5 text-sm">
                    <dt className="text-muted-foreground">Table</dt>
                    <dd>
                      <Badge variant="secondary" className="font-mono">
                        {ev.source_table}
                      </Badge>
                    </dd>
                    {tf ? (
                      <>
                        <dt className="text-muted-foreground">Time field</dt>
                        <dd className="font-mono text-foreground">{tf}</dd>
                      </>
                    ) : null}
                  </dl>
                </div>

                <div className="space-y-2">
                  <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Raw source row
                  </div>
                  <div className="overflow-hidden rounded-md border border-border">
                    <table className="w-full text-sm">
                      <tbody>
                        {entries.map(([key, val]) => (
                          <tr
                            key={key}
                            className="border-b border-border last:border-0 even:bg-muted/30"
                          >
                            <td className="whitespace-nowrap px-3 py-1.5 font-mono text-xs text-muted-foreground">
                              {key}
                            </td>
                            <td className="px-3 py-1.5 font-mono text-xs text-foreground">
                              {val === null || val === undefined ? "—" : String(val)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </SheetContent>
    </Sheet>
  )
}
