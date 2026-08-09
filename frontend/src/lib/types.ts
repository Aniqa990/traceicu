// Mirrors the Pydantic models exposed by the TraceICU FastAPI backend
// (app/models.py, app/subjects.py, app/ai/schema.py).

export interface Evidence {
  source_table: string
  source_fields: Record<string, unknown>
}

export type EventType =
  | "ADMISSION"
  | "DISCHARGE"
  | "TRANSFER"
  | "LAB"
  | "LAB_CLUSTER"
  | "MEDICATION_ADMIN"
  | "PROCEDURE"
  | "ICU_STAY"
  | "ICU_OBSERVATION"
  | "ICU_OBSERVATION_CLUSTER"

export interface TimelineEvent {
  event_id: string
  subject_id: number
  hadm_id?: number | null
  stay_id?: number | null
  event_time?: string | null
  event_end_time?: string | null
  event_type: EventType
  event_subtype?: string | null
  label: string
  value?: string | null
  unit?: string | null
  is_derived?: boolean
  derivation_rule?: string | null
  /** Present only on cluster events in the Level-1 summary payload. */
  child_count?: number
  /** Present when fetching a single event (Level 2). */
  children?: TimelineEvent[]
  children_total?: number
  evidence?: Evidence[]
}

export interface TimelineResponse {
  subject_id: number
  hadm_id?: number | null
  limit: number
  offset: number
  total_events: number
  events: TimelineEvent[]
}

export interface SubjectSearchResult {
  subject_id: number
  gender?: string | null
  anchor_age?: number | null
  admission_count: number
  icu_stay_count: number
}

export interface EncounterSummary {
  hadm_id: number
  admittime?: string | null
  dischtime?: string | null
  admission_type?: string | null
  admission_location?: string | null
  discharge_location?: string | null
  icu_stay_count: number
}

export interface SubjectOverview {
  subject_id: number
  gender?: string | null
  anchor_age?: number | null
  anchor_year_group?: string | null
  encounters: EncounterSummary[]
}

export interface QueryPlan {
  intent: string
  domain?: string | null
  concept?: string | null
  time_scope?: string | null
  start_time?: string | null
  end_time?: string | null
  hadm_id?: number | null
  stay_id?: number | null
}

export interface AskResponse {
  status: "supported" | "abstain" | "out_of_scope"
  answer: string
  evidence: Evidence[]
  evidence_coverage: number
  query_plan?: QueryPlan | null
  reason?: string | null
  searched_tables: string[]
  latency_ms: number
}
