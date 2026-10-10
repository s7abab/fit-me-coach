"use client";

import { useEffect, useState } from "react";
import { getDashboard, type Dashboard } from "@/lib/api";
import { headerDate } from "@/lib/format";
import Brief from "./Brief";
import Chat from "./Chat";
import Trends from "./Trends";

type Tab = "coach" | "trends";

export default function App() {
  const [tab, setTab] = useState<Tab>("coach"); // phones show one pane at a time
  const [days, setDays] = useState(14);
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [today, setToday] = useState("");

  useEffect(() => setToday(headerDate(new Date())), []);

  useEffect(() => {
    const controller = new AbortController();
    setError(null);
    getDashboard(days, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== "AbortError") setError("Could not load your data. Is the API running?");
      });
    return () => controller.abort();
  }, [days]);

  return (
    <div className="app" data-tab={tab}>
      <header className="top">
        <span className="wordmark">fit me<i /></span>
        <nav className="tabs" aria-label="View">
          <button type="button" aria-pressed={tab === "coach"} onClick={() => setTab("coach")}>Coach</button>
          <button type="button" aria-pressed={tab === "trends"} onClick={() => setTab("trends")}>Trends</button>
        </nav>
        <span className="top-date">{today}</span>
      </header>

      <Chat>
        <Brief data={data} error={error} days={days} />
      </Chat>

      <Trends data={data} days={days} onDays={setDays} />
    </div>
  );
}
