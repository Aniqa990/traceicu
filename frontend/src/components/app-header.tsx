import { Link } from "react-router-dom"
import { Activity } from "lucide-react"
import { Badge } from "@/components/ui/badge"

export function AppHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
            <Activity className="size-4" />
          </span>
          <span className="text-sm font-semibold tracking-tight text-foreground">
            Trace<span className="text-primary">ICU</span>
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="font-mono">
            Research-only
          </Badge>
          <Badge variant="secondary" className="font-mono">
            MIMIC-IV
          </Badge>
        </div>
      </div>
    </header>
  )
}
