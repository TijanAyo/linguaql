"use client";

import { useEffect, useState } from "react";
import SQLDisplay from "./SQLDisplay";
import ChartRenderer from "./ChartRenderer";
import StatusLine from "./StatusLine";
import type { Phase } from "../lib/verbs";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const SAMPLE_DB_URL =
  process.env.NEXT_PUBLIC_SAMPLE_DB_URL ||
  "postgresql://demo:demo@sample-db:5432/shop";
const DEV = process.env.NEXT_PUBLIC_DEV_MODE === "true";

function maskDbUrl(url: string): string {
  const m = url.match(/^(\w+:\/\/)([^:@/]+):([^@]+)@([^/]+)(\/.*)?$/);
  if (!m) return url;
  const [, scheme, user, , , path = ""] = m;
  return `${scheme}${user}:****@****${path}`;
}

export default function ChatInterface() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [dbUrl, setDbUrl] = useState(SAMPLE_DB_URL);
  const [dbFocused, setDbFocused] = useState(false);
  const [status, setStatus] = useState("");
  const [question, setQuestion] = useState("total revenue by month");
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState<Phase>("query");
  const [remaining, setRemaining] = useState<number | null>(null);
  const [limit, setLimit] = useState<number | null>(null);

  function refreshLimits() {
    fetch(`${API}/limits`)
      .then((r) => r.json())
      .then((d) => {
        setRemaining(d.queries_remaining);
        setLimit(d.queries_limit);
      })
      .catch(() => {});
  }
  // Load the shared daily budget on mount.
  useEffect(refreshLimits, []);

  const outOfBudget = remaining != null && remaining <= 0;

  async function connect() {
    setBusy(true);
    setPhase("ingest");
    setStatus("");
    try {
      const p = await fetch(`${API}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "demo", db_url: dbUrl }),
      }).then((r) => r.json());
      const reloaded = await fetch(`${API}/projects/${p.id}/reload`, {
        method: "POST",
      }).then((r) => r.json());
      setProjectId(p.id);
      setStatus(
        `Connected. ${reloaded.table_count} tables, ${reloaded.column_count} columns ingested.`,
      );
    } catch (e: any) {
      setStatus("Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function ask(forceBad = false, confirmed = false) {
    if (!projectId || outOfBudget) return;
    setBusy(true);
    setPhase("query");
    setResult(null);
    setStatus("");
    try {
      const r = await fetch(`${API}/projects/${projectId}/query`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          confirmed,
          force_bad_column: forceBad ? "definitely_not_a_column" : null,
        }),
      }).then((r) => r.json());
      setResult(r);
      if (r.queries_remaining != null) setRemaining(r.queries_remaining);
      if (r.queries_limit != null) setLimit(r.queries_limit);
      setStatus(
        r.needs_clarification
          ? "Needs confirmation."
          : r.ok
            ? `Done (retries: ${r.retry_count}).`
            : r.error
              ? "" // the error banner below carries the message
              : "Query returned an error.",
      );
    } catch (e: any) {
      setStatus("Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  const cols: string[] = result?.columns || [];
  const rows: any[] = result?.rows || [];

  return (
    <div style={{ maxWidth: 900, margin: "0 auto", padding: 24 }}>
      <h1 style={{ fontSize: 28 }}>LinguaQL</h1>
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginTop: -8,
        }}
      >
        <p style={{ opacity: 0.6, margin: 0 }}>
          Ask your database in plain English.
        </p>
        {remaining != null && limit != null && (
          <span style={counterStyle} title="Shared daily demo budget">
            {outOfBudget ? "🎬" : "🔋"} {remaining} / {limit} free queries left
            today
          </span>
        )}
      </div>

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <input
          value={dbFocused ? dbUrl : maskDbUrl(dbUrl)}
          onChange={(e) => setDbUrl(e.target.value)}
          onFocus={() => setDbFocused(true)}
          onBlur={() => setDbFocused(false)}
          style={inputStyle}
          placeholder="insert DB connection URL"
        />
        <button onClick={connect} disabled={busy} style={btnStyle}>
          Connect & Ingest
        </button>
      </div>

      {projectId && (
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <input
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            style={inputStyle}
            onKeyDown={(e) => e.key === "Enter" && ask(false)}
          />
          <button
            onClick={() => ask(false)}
            disabled={busy || outOfBudget}
            style={btnStyle}
          >
            Ask
          </button>
          {DEV && (
            <button
              onClick={() => ask(true)}
              disabled={busy || outOfBudget}
              style={{
                ...btnStyle,
                background: "#3a2a2a",
                borderColor: "#5a3a3a",
              }}
              title="Injects a bad column to demonstrate the validator + self-correction loop"
            >
              Ask (force guardrail)
            </button>
          )}
        </div>
      )}

      {outOfBudget && (
        <div style={{ marginTop: 12, fontSize: 13, opacity: 0.75 }}>
          That's a wrap for today 🎬... the daily budget is spent. Come back
          tomorrow!
        </div>
      )}

      <StatusLine busy={busy} phase={phase} status={status} />

      {result && (
        <div style={{ marginTop: 8 }}>
          {result.confidence_score != null && (
            <div style={{ fontSize: 12, opacity: 0.6 }}>
              confidence {Number(result.confidence_score).toFixed(2)} · chart:{" "}
              {result.chart_type} · retries {result.retry_count}
              {result.complexity_score != null &&
                ` · complexity ${result.complexity_score}`}
              {result.explain_cost != null &&
                ` · est.cost ${Number(result.explain_cost).toFixed(0)}`}
            </div>
          )}
          {result.needs_clarification && (
            <div
              style={{
                marginTop: 12,
                padding: 12,
                borderRadius: 8,
                background: "#2a2410",
                border: "1px solid #5a4a1a",
              }}
            >
              <div style={{ marginBottom: 8 }}>{result.clarification}</div>
              <button
                onClick={() => ask(false, true)}
                disabled={busy}
                style={btnStyle}
              >
                Confirm & run
              </button>
            </div>
          )}
          <SQLDisplay sql={result.generated_sql} />
          {result.error && !outOfBudget && (
            <div style={{ color: "#ff8a8a", marginTop: 12 }}>
              {result.error}
              {result.needs_reload &&
                "... click Connect & Ingest to reload the schema."}
            </div>
          )}
          <ChartRenderer
            chartType={result.chart_type}
            chartData={result.chart_data}
          />
          {cols.length > 0 && (
            <div style={{ overflowX: "auto", marginTop: 16 }}>
              <table
                style={{
                  borderCollapse: "collapse",
                  width: "100%",
                  fontSize: 13,
                }}
              >
                <thead>
                  <tr>
                    {cols.map((c) => (
                      <th key={c} style={thStyle}>
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, i) => (
                    <tr key={i}>
                      {cols.map((c) => (
                        <td key={c} style={tdStyle}>
                          {String(row[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div style={howtoStyle}>
        <div style={{ fontWeight: 600, marginBottom: 6, opacity: 0.85 }}>
          Lingua 101
        </div>
        <ol style={{ margin: 0, paddingLeft: 18, lineHeight: 1.7 }}>
          <li>
            A sample database is already provided — just click{" "}
            <b>Connect &amp; Ingest</b> to load it.
          </li>
          <li>
            Prefer your own data? Paste any PostgreSQL / MySQL connection URL in
            the box above, then Connect &amp; Ingest.
          </li>
          <li>
            Ask a question in plain English and hit <b>Ask</b>.
          </li>
        </ol>
        <div style={{ marginTop: 8, opacity: 0.7 }}>
          Try: &ldquo;total revenue by month&rdquo; &middot; &ldquo;top 5
          products by revenue&rdquo; &middot; &ldquo;average order value by
          country&rdquo; &middot; &ldquo;best-rated products&rdquo;
        </div>
      </div>
    </div>
  );
}

const howtoStyle: React.CSSProperties = {
  marginTop: 28,
  paddingTop: 16,
  borderTop: "1px solid #21252d",
  fontSize: 13,
  color: "#c7ccd4",
};
const inputStyle: React.CSSProperties = {
  flex: 1,
  padding: "10px 12px",
  borderRadius: 8,
  border: "1px solid #2a2f3a",
  background: "#1a1d24",
  color: "#e6e8eb",
  fontSize: 14,
};
const btnStyle: React.CSSProperties = {
  padding: "10px 16px",
  borderRadius: 8,
  border: "1px solid #2f5fa0",
  background: "#274b7a",
  color: "#e6e8eb",
  cursor: "pointer",
  fontSize: 14,
};
const counterStyle: React.CSSProperties = {
  fontSize: 12,
  opacity: 0.75,
  padding: "4px 10px",
  borderRadius: 999,
  border: "1px solid #2a2f3a",
  background: "#1a1d24",
  whiteSpace: "nowrap",
  fontFamily: "var(--font-datatype), ui-monospace, monospace",
};
const thStyle: React.CSSProperties = {
  textAlign: "left",
  borderBottom: "1px solid #2a2f3a",
  padding: "8px 10px",
  opacity: 0.7,
  fontFamily: "var(--font-datatype), ui-monospace, monospace",
};
const tdStyle: React.CSSProperties = {
  borderBottom: "1px solid #21252d",
  padding: "8px 10px",
  fontFamily: "var(--font-datatype), ui-monospace, monospace",
};
