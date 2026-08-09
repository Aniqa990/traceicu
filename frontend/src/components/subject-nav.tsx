import { Link } from "react-router-dom"
import { ListTree, MessagesSquare } from "lucide-react"
import { cn } from "@/lib/utils"

export function SubjectNav({
  subjectId,
  current,
}: {
  subjectId: number
  current: "timeline" | "ask"
}) {
  const items = [
    { key: "timeline", label: "Timeline", to: `/subjects/${subjectId}`, icon: ListTree },
    { key: "ask", label: "Ask the record", to: `/subjects/${subjectId}/ask`, icon: MessagesSquare },
  ] as const

  return (
    <div className="border-b border-border bg-card">
      <div className="mx-auto flex max-w-5xl gap-1 px-4 sm:px-6">
        {items.map((item) => {
          const activeTab = current === item.key
          const Icon = item.icon
          return (
            <Link
              key={item.key}
              to={item.to}
              className={cn(
                "-mb-px flex items-center gap-2 border-b-2 px-3 py-3 text-sm font-medium transition-colors",
                activeTab
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              <Icon className="size-4" />
              {item.label}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
