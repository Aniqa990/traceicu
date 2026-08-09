import React from "react"
import ReactDOM from "react-dom/client"
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom"
import { SearchPage } from "@/pages/SearchPage"
import { SubjectPage } from "@/pages/SubjectPage"
import { ClusterPage } from "@/pages/ClusterPage"
import { AskPage } from "@/pages/AskPage"
import "./index.css"

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/subjects/:subjectId" element={<SubjectPage />} />
        <Route path="/subjects/:subjectId/events/:eventId" element={<ClusterPage />} />
        <Route path="/subjects/:subjectId/ask" element={<AskPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </React.StrictMode>,
)
