import {
  Activity,
  ArrowRightLeft,
  FlaskConical,
  HeartPulse,
  Hospital,
  LogOut,
  Pill,
  Stethoscope,
  type LucideIcon,
} from "lucide-react"
import type { EventType } from "./types"

interface EventMeta {
  icon: LucideIcon
  /** Short human label for the event category. */
  category: string
  /** Tailwind class for the rail dot / icon accent. */
  tone: string
  clusterType?: boolean
}

const META: Record<EventType, EventMeta> = {
  ADMISSION: { icon: Hospital, category: "Admission", tone: "text-primary" },
  DISCHARGE: { icon: LogOut, category: "Discharge", tone: "text-muted-foreground" },
  TRANSFER: { icon: ArrowRightLeft, category: "Transfer", tone: "text-primary" },
  LAB: { icon: FlaskConical, category: "Lab", tone: "text-primary" },
  LAB_CLUSTER: { icon: FlaskConical, category: "Labs", tone: "text-primary", clusterType: true },
  MEDICATION_ADMIN: { icon: Pill, category: "Medication", tone: "text-warning-foreground" },
  PROCEDURE: { icon: Stethoscope, category: "Procedure", tone: "text-primary" },
  ICU_STAY: { icon: HeartPulse, category: "ICU stay", tone: "text-destructive" },
  ICU_OBSERVATION: { icon: Activity, category: "Observation", tone: "text-primary" },
  ICU_OBSERVATION_CLUSTER: {
    icon: Activity,
    category: "ICU observations",
    tone: "text-primary",
    clusterType: true,
  },
}

const FALLBACK: EventMeta = { icon: Activity, category: "Event", tone: "text-muted-foreground" }

export function eventMeta(type: EventType): EventMeta {
  return META[type] ?? FALLBACK
}

export function isCluster(event: { event_type: EventType; is_derived?: boolean }): boolean {
  return (
    event.is_derived === true ||
    event.event_type === "LAB_CLUSTER" ||
    event.event_type === "ICU_OBSERVATION_CLUSTER"
  )
}
