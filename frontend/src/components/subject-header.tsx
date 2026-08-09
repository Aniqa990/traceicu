import { Link } from "react-router-dom"
import { ChevronLeft, User } from "lucide-react"
import { Skeleton } from "@/components/ui/skeleton"
import type { SubjectOverview } from "@/lib/types"

export function SubjectHeader({
  subjectId,
  overview,
  loading,
}: {
  subjectId: number
  overview: SubjectOverview | null
  loading: boolean
}) {
  const primary = overview?.encounters?.[0]
  return (
    <div className="border-b border-border bg-card">
      <div className="mx-auto max-w-5xl px-4 py-5 sm:px-6">
        <Link
          to="/"
          className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ChevronLeft className="size-4" /> Search
        </Link>

        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-7 w-48" />
            <Skeleton className="h-4 w-72" />
          </div>
        ) : (
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="flex size-9 items-center justify-center rounded-md bg-primary/12 text-primary">
                  <User className="size-4" />
                </span>
                <div>
                  <h1 className="font-mono text-xl font-semibold leading-none tracking-tight">
                    Patient {subjectId}
                  </h1>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {overview?.gender ?? "?"} · {overview?.anchor_age ?? "?"} yrs ·{" "}
                    {overview?.anchor_year_group ?? "year group n/a"}
                  </p>
                </div>
              </div>
            </div>

          </div>
        )}
      </div>
    </div>
  )
}
