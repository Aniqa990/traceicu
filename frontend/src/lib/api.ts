// Thin API client for the TraceICU FastAPI backend.
//
// In local dev, Vite proxies /api/* to the backend on 127.0.0.1:8000
// (see vite.config.ts), so VITE_API_BASE_URL is optional.
//
// Set VITE_API_BASE_URL only when the frontend should call a different
// backend origin (for example a deployed API). When the backend is
// unreachable — as in the hosted preview — every call transparently
// falls back to the demo fixtures in ./mock so the UI stays fully
// explorable.

import {
  MOCK_OVERVIEW,
  MOCK_SEARCH,
  MOCK_TIMELINE,
  mockAsk,
  mockEventDetail,
} from "./mock"
import type {
  AskResponse,
  SubjectOverview,
  SubjectSearchResult,
  TimelineEvent,
  TimelineResponse,
} from "./types"

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ""

/** True after any request fails to reach the backend — used to surface a demo banner. */
export let usingDemoData = false

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), 6000)
  try {
    const res = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    })
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`)
    }
    return (await res.json()) as T
  } finally {
    clearTimeout(timeout)
  }
}

function markDemo() {
  usingDemoData = true
}

export async function searchSubjects(q: string): Promise<SubjectSearchResult[]> {
  if (!q.trim()) return []
  try {
    const data = await request<{ results: SubjectSearchResult[] }>(
      `/api/v1/subjects/search?q=${encodeURIComponent(q)}&limit=10`,
    )
    return data.results
  } catch {
    markDemo()
    return MOCK_SEARCH.filter((s) => String(s.subject_id).startsWith(q.trim()))
  }
}

export async function getSubjectOverview(subjectId: number): Promise<SubjectOverview> {
  try {
    return await request<SubjectOverview>(`/api/v1/subjects/${subjectId}`)
  } catch {
    markDemo()
    return { ...MOCK_OVERVIEW, subject_id: subjectId }
  }
}

export async function getTimeline(subjectId: number): Promise<TimelineResponse> {
  try {
    return await request<TimelineResponse>(`/api/v1/timeline?subject_id=${subjectId}&limit=200`)
  } catch {
    markDemo()
    return { ...MOCK_TIMELINE, subject_id: subjectId }
  }
}

export async function getEvent(subjectId: number, eventId: string): Promise<TimelineEvent> {
  try {
    return await request<TimelineEvent>(
      `/api/v1/events/${encodeURIComponent(eventId)}?subject_id=${subjectId}&limit=2000`,
    )
  } catch {
    markDemo()
    const ev = mockEventDetail(eventId)
    if (!ev) throw new Error("Event not found")
    return ev
  }
}

export async function ask(subjectId: number, question: string): Promise<AskResponse> {
  try {
    return await request<AskResponse>(`/api/v1/ask`, {
      method: "POST",
      body: JSON.stringify({ subject_id: subjectId, question }),
    })
  } catch {
    markDemo()
    return mockAsk(question)
  }
}
