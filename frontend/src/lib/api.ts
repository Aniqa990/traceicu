//api.ts

import type {
  AskResponse,
  SubjectOverview,
  SubjectSearchResult,
  TimelineEvent,
  TimelineResponse,
} from "./types"

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ""

async function request<T>(path: string, init?: RequestInit, timeoutMs = 6000): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)
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

export async function searchSubjects(q: string): Promise<SubjectSearchResult[]> {
  if (!q.trim()) return []
  const data = await request<{ results: SubjectSearchResult[] }>(
    `/api/v1/subjects/search?q=${encodeURIComponent(q)}&limit=10`,
  )
  return data.results
}

export async function getSubjectOverview(subjectId: number): Promise<SubjectOverview> {
  return await request<SubjectOverview>(`/api/v1/subjects/${subjectId}`)
}

export async function getTimeline(subjectId: number): Promise<TimelineResponse> {
  return await request<TimelineResponse>(`/api/v1/timeline?subject_id=${subjectId}&limit=200`)
}

export async function getEvent(subjectId: number, eventId: string): Promise<TimelineEvent> {
  return await request<TimelineEvent>(
    `/api/v1/events/${encodeURIComponent(eventId)}?subject_id=${subjectId}&limit=2000`,
  )
}

export async function ask(subjectId: number, question: string): Promise<AskResponse> {
  return await request<AskResponse>(`/api/v1/ask`, {
    method: "POST",
    body: JSON.stringify({ subject_id: subjectId, question }),
  }, 25000)
}
