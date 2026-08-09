import { useEffect, useMemo, useRef, useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  ArrowRight,
  FlaskConical,
  Lock,
  Route as RouteIcon,
  Search,
  ShieldCheck,
} from "lucide-react"
import { AppHeader } from "@/components/app-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Badge } from "@/components/ui/badge"
import { searchSubjects } from "@/lib/api"
import type { SubjectSearchResult } from "@/lib/types"

export function SearchPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState("")
  const [results, setResults] = useState<SubjectSearchResult[]>([])
  const [loading, setLoading] = useState(false)
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const numeric = useMemo(() => /^\d+$/.test(query.trim()), [query])

  useEffect(() => {
    const q = query.trim()
    if (!q) {
      setResults([])
      return
    }
    let cancelled = false
    setLoading(true)
    const t = setTimeout(async () => {
      const r = await searchSubjects(q)
      if (!cancelled) {
        setResults(r)
        setActive(0)
        setLoading(false)
      }
    }, 180)
    return () => {
      cancelled = true
      clearTimeout(t)
    }
  }, [query])

  function go(subjectId: number) {
    navigate(`/subjects/${subjectId}`)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setActive((a) => Math.min(a + 1, results.length - 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setActive((a) => Math.max(a - 1, 0))
    } else if (e.key === "Enter") {
      e.preventDefault()
      if (results[active]) go(results[active].subject_id)
      else if (numeric) go(Number(query.trim()))
    }
  }

  return (
    <div className="min-h-screen">
      <AppHeader />

      <main className="mx-auto max-w-3xl px-4 pb-24 pt-16 sm:px-6 sm:pt-24">
        <div className="animate-fade-rise">
          <p className="mb-3 flex items-center gap-2 text-xs font-medium uppercase tracking-widest text-primary">
            <RouteIcon className="size-3.5" />
            Evidence-first ICU record explorer
          </p>
          <h1 className="text-balance text-4xl font-semibold leading-tight tracking-tight sm:text-5xl">
            Trace every clinical fact back to its{" "}
            <span className="text-primary">exact source row.</span>
          </h1>
          <p className="mt-4 max-w-xl text-pretty leading-relaxed text-muted-foreground">
            TraceICU reconstructs a single patient&apos;s hospital journey from MIMIC-IV — labs,
            vitals, medications, procedures and transfers — as one auditable timeline. Nothing is
            summarized without a citation to the record it came from.
          </p>
        </div>

        {/* Search */}
        <div className="relative mt-10">
          <label htmlFor="subject-search" className="sr-only">
            Search by subject_id
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-muted-foreground" />
            <Input
              id="subject-search"
              ref={inputRef}
              inputMode="numeric"
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="Enter subject_id (e.g. 10006)"
              className="h-14 pl-12 pr-32 font-mono text-base"
            />
            <Button
              onClick={() => (results[active] ? go(results[active].subject_id) : numeric && go(Number(query.trim())))}
              disabled={!numeric && results.length === 0}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              Open <ArrowRight className="size-4" />
            </Button>
          </div>

          {/* Autocomplete */}
          {query.trim() && (
            <div className="absolute inset-x-0 top-[calc(100%+0.5rem)] z-20 overflow-hidden rounded-lg border border-border bg-popover shadow-lg">
              {loading ? (
                <div className="px-4 py-3 text-sm text-muted-foreground">Searching…</div>
              ) : results.length === 0 ? (
                <div className="px-4 py-3 text-sm text-muted-foreground">
                  {numeric
                    ? "No matching subject_id found."
                    : "subject_id is numeric — type digits only."}
                </div>
              ) : (
                <ul className="max-h-72 overflow-y-auto scroll-thin py-1">
                  {results.map((r, i) => (
                    <li key={r.subject_id}>
                      <button
                        type="button"
                        onMouseEnter={() => setActive(i)}
                        onClick={() => go(r.subject_id)}
                        className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left text-sm transition-colors ${
                          i === active ? "bg-accent text-accent-foreground" : "hover:bg-muted"
                        }`}
                      >
                        <span className="flex items-center gap-3">
                          <span className="font-mono font-medium">{r.subject_id}</span>
                          <span className="text-muted-foreground">
                            {r.gender ?? "?"} · {r.anchor_age ?? "?"} yrs
                          </span>
                        </span>
                        <span className="flex items-center gap-2 text-xs text-muted-foreground">
                          <Badge variant="outline">{r.admission_count} adm</Badge>
                          <Badge variant="outline">{r.icu_stay_count} ICU</Badge>
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Feature strip */}
        <div className="mt-14 grid gap-4 sm:grid-cols-3">
          <Feature
            icon={<RouteIcon className="size-4" />}
            title="Full journey"
            body="Admissions, transfers, ICU stays, labs, vitals and meds on one vertical timeline."
          />
          <Feature
            icon={<FlaskConical className="size-4" />}
            title="Clustered detail"
            body="Dense lab and observation bursts collapse into clusters you can drill into."
          />
          <Feature
            icon={<ShieldCheck className="size-4" />}
            title="Provenance drawer"
            body="Any event opens the raw source row it was built from — table, field and value."
          />
        </div>

        {/* Security + terms */}
        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <div className="rounded-lg border border-border bg-card p-5">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <Lock className="size-4 text-primary" /> Security &amp; access
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Data is served read-only from a local DuckDB build of the de-identified MIMIC-IV
              demo. No protected health information is transmitted; subject identifiers are
              synthetic and dates are shifted.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-5">
            <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
              <ShieldCheck className="size-4 text-primary" /> Terms &amp; conditions
            </div>
            <p className="text-sm leading-relaxed text-muted-foreground">
              Research and educational prototype only. Not for clinical use. Do not use for diagnosis, treatment, 
              triage, or emergency decisions. 
            </p>
          </div>
        </div>

        {/* Footer stats */}
        <div className="mt-8 flex flex-col items-start justify-between gap-2 border-t border-border pt-6 text-sm text-muted-foreground sm:flex-row sm:items-center">
          <div className="flex items-center gap-4 font-mono">
            <span>100 subjects</span>
            <span className="text-border">•</span>
            <span>275 admissions</span>
            <span className="text-border">•</span>
            <span>140 ICU stays</span>
          </div>
          <span>Source: MIMIC-IV Clinical Database Demo v2.2</span>
        </div>
      </main>
    </div>
  )
}

function Feature({
  icon,
  title,
  body,
}: {
  icon: React.ReactNode
  title: string
  body: string
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <div className="mb-3 flex size-8 items-center justify-center rounded-md bg-primary/12 text-primary">
        {icon}
      </div>
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="mt-1 text-sm leading-relaxed text-muted-foreground">{body}</p>
    </div>
  )
}
