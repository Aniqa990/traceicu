import { useEffect, useRef, useState } from "react"
import { useParams } from "react-router-dom"
import { ArrowUp, Database, ShieldCheck, Sparkles, TriangleAlert } from "lucide-react"
import { AppHeader } from "@/components/app-header"
import { SubjectHeader } from "@/components/subject-header"
import { SubjectNav } from "@/components/subject-nav"
import { ProvenanceDrawer } from "@/components/provenance-drawer"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Badge } from "@/components/ui/badge"
import { ask, getSubjectOverview } from "@/lib/api"
import { cn } from "@/lib/utils"
import type { AskResponse, Evidence, SubjectOverview, TimelineEvent } from "@/lib/types"

interface UserMsg {
  role: "user"
  id: string
  text: string
}
interface BotMsg {
  role: "assistant"
  id: string
  response: AskResponse
}
type Msg = UserMsg | BotMsg

const SUGGESTIONS = [
  "What was the first sodium?",
  "List all medications given",
  "Show the ICU transfers",
]

export function AskPage() {
  const { subjectId: raw } = useParams()
  const subjectId = Number(raw)

  const [overview, setOverview] = useState<SubjectOverview | null>(null)
  const [ovLoading, setOvLoading] = useState(true)
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState("")
  const [pending, setPending] = useState(false)

  const [selected, setSelected] = useState<TimelineEvent | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    getSubjectOverview(subjectId)
      .then((ov) => !cancelled && setOverview(ov))
      .finally(() => !cancelled && setOvLoading(false))
    return () => {
      cancelled = true
    }
  }, [subjectId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" })
  }, [messages, pending])

  async function submit(question: string) {
    const q = question.trim()
    if (!q || pending) return
    const userMsg: UserMsg = { role: "user", id: crypto.randomUUID(), text: q }
    setMessages((m) => [...m, userMsg])
    setInput("")
    setPending(true)
    const response = await ask(subjectId, q)
    setMessages((m) => [...m, { role: "assistant", id: crypto.randomUUID(), response }])
    setPending(false)
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.nativeEvent.isComposing || e.keyCode === 229) return
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault()
      submit(input)
    }
  }

  function openEvidence(label: string, ev: Evidence) {
    setSelected({
      event_id: `cite-${ev.source_table}`,
      subject_id: subjectId,
      event_type: "LAB",
      label,
      evidence: [ev],
    })
    setDrawerOpen(true)
  }

  return (
    <div className="flex min-h-screen flex-col">
      <AppHeader />
      <SubjectHeader subjectId={subjectId} overview={overview} loading={ovLoading} />
      <SubjectNav subjectId={subjectId} current="ask" />

      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4 sm:px-6">
        <div ref={scrollRef} className="scroll-thin flex-1 overflow-y-auto py-8">
          {messages.length === 0 ? (
            <EmptyState onPick={submit} />
          ) : (
            <div className="space-y-6">
              {messages.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="flex justify-end">
                    <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2.5 text-sm text-primary-foreground">
                      {m.text}
                    </div>
                  </div>
                ) : (
                  <AssistantMessage key={m.id} response={m.response} onCite={openEvidence} />
                ),
              )}
              {pending ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Sparkles className="size-4 animate-pulse text-primary" />
                  Retrieving evidence…
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Composer */}
        <div className="sticky bottom-0 border-t border-border bg-background/90 py-4 backdrop-blur">
          <div className="flex items-end gap-2 rounded-xl border border-border bg-card p-2 shadow-sm focus-within:ring-2 focus-within:ring-ring">
            <Textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKeyDown}
              rows={1}
              placeholder={`Ask about patient ${subjectId}'s labs, vitals, meds, procedures…`}
              className="max-h-40 flex-1 border-0 bg-transparent shadow-none focus-visible:ring-0"
            />
            <Button
              size="icon"
              onClick={() => submit(input)}
              disabled={!input.trim() || pending}
              aria-label="Send"
            >
              <ArrowUp className="size-4" />
            </Button>
          </div>
          <p className="mt-2 flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
            <ShieldCheck className="size-3.5" />
            Answers are built only from retrieved source rows. The assistant abstains when nothing
            is found.
          </p>
        </div>
      </main>

      <ProvenanceDrawer event={selected} open={drawerOpen} onOpenChange={setDrawerOpen} />
    </div>
  )
}

function EmptyState({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="flex flex-col items-center py-12 text-center">
      <span className="mb-4 flex size-12 items-center justify-center rounded-xl bg-primary/12 text-primary">
        <Sparkles className="size-6" />
      </span>
      <h2 className="text-lg font-semibold">Ask the record</h2>
      <p className="mt-1 max-w-md text-pretty text-sm text-muted-foreground">
        Query this patient&apos;s structured record in natural language. Every answer cites the
        exact rows it was built from — and abstains when the record has no supporting data.
      </p>
      <div className="mt-6 flex flex-wrap justify-center gap-2">
        {SUGGESTIONS.map((s) => (
          <button
            key={s}
            onClick={() => onPick(s)}
            className="rounded-full border border-border bg-card px-3.5 py-1.5 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  )
}

// frontend/src/pages/AskPage.tsx — add this component, near AssistantMessage

function CitedAnswer({
  text,
  evidence,
  onCite,
}: {
  text: string
  evidence: Evidence[]
  onCite: (label: string, ev: Evidence) => void
}) {
  const parts = text.split(/(\[E\d+\])/g)
  return (
    <p>
      {parts.map((part, i) => {
        const m = part.match(/^\[E(\d+)\]$/)
        if (!m) return <span key={i}>{part}</span>
        const idx = Number(m[1]) - 1
        const ev = evidence[idx]
        if (!ev) return <span key={i}>{part}</span>
        return (
          <button
            key={i}
            onClick={() => onCite(`Evidence ${idx + 1}`, ev)}
            className="mx-0.5 inline-flex translate-y-[-1px] items-center rounded bg-primary/15 px-1.5 py-0.5 align-middle font-mono text-[11px] font-semibold text-primary transition-colors hover:bg-primary/25"
          >
            {part}
          </button>
        )
      })}
    </p>
  )
}

function AssistantMessage({
  response,
  onCite,
}: {
  response: AskResponse
  onCite: (label: string, ev: Evidence) => void
}) {
  const abstained = response.status !== "supported"
  return (
    <div className="space-y-3">
      <div
        className={cn(
          "rounded-2xl rounded-bl-sm border px-4 py-3 text-sm leading-relaxed",
          abstained
            ? "border-warning/40 bg-warning/10 text-foreground"
            : "border-border bg-card text-foreground",
        )}
      >
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <StatusBadge status={response.status} />
          {response.query_plan?.intent ? (
            <Badge variant="outline" className="font-mono">
              {response.query_plan.intent}
            </Badge>
          ) : null}
          <span className="ml-auto font-mono text-xs text-muted-foreground">
            {response.latency_ms} ms
          </span>
        </div>
        <CitedAnswer text={response.answer} evidence={response.evidence} onCite={onCite} />
      </div>
      
      {response.evidence.length > 0 ? (
        <div className="space-y-1.5 pl-1">
          <div className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            <Database className="size-3.5" />
            Evidence · {response.evidence.length} row(s)
          </div>
          <div className="flex flex-wrap gap-2">
            {response.evidence.map((ev, i) => (
              <button
                key={i}
                onClick={() => onCite(`Evidence ${i + 1}`, ev)}
                className="group flex items-center gap-2 rounded-md border border-border bg-card px-2.5 py-1.5 text-left text-xs transition-colors hover:border-primary/40 hover:bg-accent/40"
              >
                <Badge variant="secondary" className="font-mono">
                  {ev.source_table}
                </Badge>
                <span className="font-mono text-muted-foreground">
                  {previewFields(ev.source_fields)}
                </span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {response.searched_tables.length > 0 ? (
        <p className="pl-1 text-xs text-muted-foreground">
          Searched: {response.searched_tables.join(", ")}
        </p>
      ) : null}
    </div>
  )
}

function StatusBadge({ status }: { status: AskResponse["status"] }) {
  if (status === "supported")
    return (
      <Badge variant="default">
        <ShieldCheck className="size-3" /> Supported
      </Badge>
    )
  if (status === "out_of_scope")
    return (
      <Badge variant="outline">
        <TriangleAlert className="size-3" /> Out of scope
      </Badge>
    )
  return (
    <Badge variant="warning">
      <TriangleAlert className="size-3" /> Abstained
    </Badge>
  )
}

function previewFields(fields: Record<string, unknown>): string {
  const keys = ["value", "valuenum", "charttime", "medication", "careunit", "icd_code"]
  for (const k of keys) {
    if (k in fields && fields[k] != null) return `${k}=${String(fields[k])}`
  }
  const first = Object.entries(fields)[0]
  return first ? `${first[0]}=${String(first[1])}` : ""
}
