// Demo fixtures used when the FastAPI backend is unreachable (e.g. the
// hosted preview). Shapes mirror src/lib/types.ts exactly so swapping in
// the live API requires no component changes.

import type {
  AskResponse,
  SubjectOverview,
  SubjectSearchResult,
  TimelineEvent,
  TimelineResponse,
} from "./types"

const BASE_DATE = "2155-11-01"

export const MOCK_SEARCH: SubjectSearchResult[] = [
  { subject_id: 10006, gender: "F", anchor_age: 68, admission_count: 1, icu_stay_count: 1 },
  { subject_id: 10011, gender: "F", anchor_age: 50, admission_count: 1, icu_stay_count: 1 },
  { subject_id: 10013, gender: "F", anchor_age: 87, admission_count: 1, icu_stay_count: 1 },
  { subject_id: 10019, gender: "M", anchor_age: 49, admission_count: 1, icu_stay_count: 1 },
  { subject_id: 10020, gender: "F", anchor_age: 55, admission_count: 2, icu_stay_count: 1 },
]

export const MOCK_OVERVIEW: SubjectOverview = {
  subject_id: 10006,
  gender: "F",
  anchor_age: 68,
  anchor_year_group: "2008 - 2010",
  encounters: [
    {
      hadm_id: 142345,
      admittime: `${BASE_DATE} 10:30:00`,
      dischtime: "2155-11-05 15:10:00",
      admission_type: "EW EMER.",
      admission_location: "EMERGENCY ROOM",
      discharge_location: "HOME",
      icu_stay_count: 1,
    },
  ],
}

function labChild(
  id: string,
  label: string,
  value: string,
  unit: string,
  time: string,
  rowId: number,
  itemid: number,
): TimelineEvent {
  return {
    event_id: id,
    subject_id: 10006,
    hadm_id: 142345,
    event_time: time,
    event_type: "LAB",
    label,
    value,
    unit,
    evidence: [
      {
        source_table: "labevents",
        source_fields: {
          labevent_id: rowId,
          subject_id: 10006,
          hadm_id: 142345,
          itemid,
          charttime: time,
          storetime: time.replace(":30:", ":45:"),
          value,
          valuenum: value,
          valueuom: unit,
        },
      },
    ],
  }
}

const LAB_CHILDREN: TimelineEvent[] = [
  labChild("lab-1", "Sodium", "138", "mEq/L", `${BASE_DATE} 12:30:00`, 1001, 50983),
  labChild("lab-2", "Potassium", "4.1", "mEq/L", `${BASE_DATE} 12:30:00`, 1002, 50971),
  labChild("lab-3", "Creatinine", "0.9", "mg/dL", `${BASE_DATE} 12:30:00`, 1003, 50912),
  labChild("lab-4", "WBC", "8.4", "K/uL", `${BASE_DATE} 12:31:00`, 1004, 51301),
  labChild("lab-5", "Hemoglobin", "13.1", "g/dL", `${BASE_DATE} 12:31:00`, 1005, 51222),
  labChild("lab-6", "Hematocrit", "39.2", "%", `${BASE_DATE} 12:31:00`, 1006, 51221),
  labChild("lab-7", "Platelet Count", "241", "K/uL", `${BASE_DATE} 12:31:00`, 1007, 51265),
  labChild("lab-8", "Chloride", "104", "mEq/L", `${BASE_DATE} 12:32:00`, 1008, 50902),
  labChild("lab-9", "Bicarbonate", "24", "mEq/L", `${BASE_DATE} 12:32:00`, 1009, 50882),
  labChild("lab-10", "Glucose", "126", "mg/dL", `${BASE_DATE} 12:32:00`, 1010, 50931),
  labChild("lab-11", "BUN", "18", "mg/dL", `${BASE_DATE} 12:33:00`, 1011, 51006),
  labChild("lab-12", "Anion Gap", "10", "mEq/L", `${BASE_DATE} 12:33:00`, 1012, 50868),
  labChild("lab-13", "Calcium, Total", "9.1", "mg/dL", `${BASE_DATE} 12:33:00`, 1013, 50893),
  labChild("lab-14", "Magnesium", "2.0", "mg/dL", `${BASE_DATE} 12:45:00`, 1014, 50960),
]

function icuChild(
  id: string,
  label: string,
  value: string,
  unit: string,
  time: string,
  rowId: number,
  itemid: number,
): TimelineEvent {
  return {
    event_id: id,
    subject_id: 10006,
    hadm_id: 142345,
    stay_id: 39060235,
    event_time: time,
    event_type: "ICU_OBSERVATION",
    label,
    value,
    unit,
    evidence: [
      {
        source_table: "chartevents",
        source_fields: {
          subject_id: 10006,
          hadm_id: 142345,
          stay_id: 39060235,
          itemid,
          charttime: time,
          value,
          valuenum: value,
          valueuom: unit,
        },
      },
    ],
  }
}

const ICU_CHILDREN: TimelineEvent[] = [
  icuChild("icu-1", "Heart Rate", "92", "bpm", `${BASE_DATE} 14:05:00`, 2001, 220045),
  icuChild("icu-2", "Arterial BP Systolic", "118", "mmHg", `${BASE_DATE} 14:05:00`, 2002, 220050),
  icuChild("icu-3", "Arterial BP Diastolic", "64", "mmHg", `${BASE_DATE} 14:05:00`, 2003, 220051),
  icuChild("icu-4", "Respiratory Rate", "18", "insp/min", `${BASE_DATE} 14:05:00`, 2004, 220210),
  icuChild("icu-5", "SpO2", "97", "%", `${BASE_DATE} 14:05:00`, 2005, 220277),
  icuChild("icu-6", "Temperature C", "37.1", "°C", `${BASE_DATE} 14:10:00`, 2006, 223762),
  icuChild("icu-7", "GCS - Eye Opening", "4", "", `${BASE_DATE} 14:10:00`, 2007, 220739),
  icuChild("icu-8", "GCS - Verbal Response", "5", "", `${BASE_DATE} 14:10:00`, 2008, 223900),
  icuChild("icu-9", "GCS - Motor Response", "6", "", `${BASE_DATE} 14:10:00`, 2009, 223901),
  icuChild("icu-10", "CVP", "8", "mmHg", `${BASE_DATE} 14:15:00`, 2010, 220074),
]

const MED_CHILDREN: TimelineEvent[] = [
  {
    event_id: "med-1",
    subject_id: 10006,
    hadm_id: 142345,
    event_time: `${BASE_DATE} 16:00:00`,
    event_type: "MEDICATION_ADMIN",
    label: "Furosemide",
    value: "40 mg",
    unit: "mg",
    evidence: [
      {
        source_table: "emar",
        source_fields: {
          subject_id: 10006,
          hadm_id: 142345,
          medication: "Furosemide",
          dose_given: "40",
          dose_unit: "mg",
          route: "IV",
          charttime: `${BASE_DATE} 16:00:00`,
        },
      },
    ],
  },
]

export const MOCK_TIMELINE_EVENTS: TimelineEvent[] = [
  {
    event_id: "evt-admission",
    subject_id: 10006,
    hadm_id: 142345,
    event_time: `${BASE_DATE} 10:30:00`,
    event_type: "ADMISSION",
    label: "Hospital admission",
    event_subtype: "EW EMER.",
    evidence: [
      {
        source_table: "admissions",
        source_fields: {
          subject_id: 10006,
          hadm_id: 142345,
          admittime: `${BASE_DATE} 10:30:00`,
          admission_type: "EW EMER.",
          admission_location: "EMERGENCY ROOM",
        },
      },
    ],
  },
  {
    event_id: "evt-transfer",
    subject_id: 10006,
    hadm_id: 142345,
    event_time: `${BASE_DATE} 11:15:00`,
    event_type: "TRANSFER",
    label: "Transfer → MICU",
    event_subtype: "Medical Intensive Care Unit",
    evidence: [
      {
        source_table: "transfers",
        source_fields: {
          subject_id: 10006,
          hadm_id: 142345,
          eventtype: "transfer",
          careunit: "Medical Intensive Care Unit (MICU)",
          intime: `${BASE_DATE} 11:15:00`,
        },
      },
    ],
  },
  {
    event_id: "evt-lab-cluster",
    subject_id: 10006,
    hadm_id: 142345,
    event_time: `${BASE_DATE} 12:30:00`,
    event_end_time: `${BASE_DATE} 12:45:00`,
    event_type: "LAB_CLUSTER",
    label: "Laboratory measurements",
    is_derived: true,
    derivation_rule: "Grouped labevents within a 15-minute window",
    child_count: LAB_CHILDREN.length,
    children: LAB_CHILDREN,
  },
  {
    event_id: "evt-procedure",
    subject_id: 10006,
    hadm_id: 142345,
    event_time: `${BASE_DATE} 13:10:00`,
    event_type: "PROCEDURE",
    label: "Central venous catheter placement",
    event_subtype: "ICD-10 02HV33Z",
    evidence: [
      {
        source_table: "procedures_icd",
        source_fields: {
          subject_id: 10006,
          hadm_id: 142345,
          icd_code: "02HV33Z",
          icd_version: 10,
          chartdate: BASE_DATE,
        },
      },
    ],
  },
  {
    event_id: "evt-icu-stay",
    subject_id: 10006,
    hadm_id: 142345,
    stay_id: 39060235,
    event_time: `${BASE_DATE} 14:00:00`,
    event_end_time: "2155-11-04 09:20:00",
    event_type: "ICU_STAY",
    label: "ICU admission",
    event_subtype: "MICU",
    evidence: [
      {
        source_table: "icustays",
        source_fields: {
          subject_id: 10006,
          hadm_id: 142345,
          stay_id: 39060235,
          first_careunit: "Medical Intensive Care Unit (MICU)",
          intime: `${BASE_DATE} 14:00:00`,
          outtime: "2155-11-04 09:20:00",
          los: 2.8,
        },
      },
    ],
  },
  {
    event_id: "evt-icu-obs-cluster",
    subject_id: 10006,
    hadm_id: 142345,
    stay_id: 39060235,
    event_time: `${BASE_DATE} 14:05:00`,
    event_end_time: `${BASE_DATE} 14:15:00`,
    event_type: "ICU_OBSERVATION_CLUSTER",
    label: "ICU observations",
    is_derived: true,
    derivation_rule: "Grouped chartevents within a 15-minute window",
    child_count: ICU_CHILDREN.length,
    children: ICU_CHILDREN,
  },
  {
    event_id: "evt-med",
    subject_id: 10006,
    hadm_id: 142345,
    event_time: `${BASE_DATE} 16:00:00`,
    event_type: "MEDICATION_ADMIN",
    label: "Furosemide",
    value: "40 mg",
    unit: "mg",
    event_subtype: "IV",
    evidence: MED_CHILDREN[0].evidence,
  },
  {
    event_id: "evt-discharge",
    subject_id: 10006,
    hadm_id: 142345,
    event_time: "2155-11-05 15:10:00",
    event_type: "DISCHARGE",
    label: "Hospital discharge",
    event_subtype: "HOME",
    evidence: [
      {
        source_table: "admissions",
        source_fields: {
          subject_id: 10006,
          hadm_id: 142345,
          dischtime: "2155-11-05 15:10:00",
          discharge_location: "HOME",
        },
      },
    ],
  },
]

export const MOCK_TIMELINE: TimelineResponse = {
  subject_id: 10006,
  limit: 50,
  offset: 0,
  total_events: MOCK_TIMELINE_EVENTS.length,
  events: MOCK_TIMELINE_EVENTS.map(({ children, ...rest }) => rest),
}

export function mockEventDetail(eventId: string): TimelineEvent | null {
  const found = MOCK_TIMELINE_EVENTS.find((e) => e.event_id === eventId)
  if (!found) return null
  if (found.children) {
    return { ...found, children_total: found.children.length }
  }
  return found
}

export function mockAsk(question: string): AskResponse {
  const q = question.toLowerCase()
  if (q.includes("sodium") || q.includes("lab")) {
    return {
      status: "supported",
      answer:
        "The first recorded sodium during this admission was 138 mEq/L at 2155-11-01 12:30, within the normal reference range.",
      evidence: LAB_CHILDREN[0].evidence ?? [],
      evidence_coverage: 1.0,
      query_plan: {
        intent: "first_measurement",
        domain: "lab",
        concept: "sodium",
        hadm_id: 142345,
      },
      searched_tables: ["labevents", "d_labitems"],
      latency_ms: 412.3,
    }
  }
  if (q.includes("medication") || q.includes("drug") || q.includes("furosemide")) {
    return {
      status: "supported",
      answer:
        "One medication administration is recorded: Furosemide 40 mg IV at 2155-11-01 16:00.",
      evidence: MED_CHILDREN[0].evidence ?? [],
      evidence_coverage: 1.0,
      query_plan: { intent: "medications", domain: "medication", hadm_id: 142345 },
      searched_tables: ["emar", "prescriptions"],
      latency_ms: 298.7,
    }
  }
  return {
    status: "abstain",
    answer:
      "No supporting rows were retrieved for this question, so no answer is provided. Try asking about labs, vitals, medications, procedures, or transfers for this patient.",
    evidence: [],
    evidence_coverage: 0.0,
    query_plan: { intent: "unsupported", hadm_id: 142345 },
    reason: "no_rows_retrieved",
    searched_tables: [],
    latency_ms: 187.4,
  }
}
