"use client";

import { useState } from "react";
import SQLDisplay from "./SQLDisplay";
import ChartRenderer from "./ChartRenderer";

const API = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
// Reachable from the backend container (docker network hostname).
const SAMPLE_DB_URL = "postgresql://demo:demo@sample-db:5432/shop";

export default function ChatInterface() {
  const [projectId, setProjectId] = useState<string | null>(null);
  const [dbUrl, setDbUrl] = useState(SAMPLE_DB_URL);
  const [status, setStatus] = useState("");
  const [question, setQuestion] = useState("total revenue by month");
  const [result, setResult] = useState<any>(null);
  const [busy, setBusy] = useState(false);

  async function connect() {
    setBusy(true);
    setStatus("Registering project…");
    try {
      const p = await fetch(`${API}/projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "demo", db_url: dbUrl }),
      }).then((r) => r.json());
      setStatus("Ingesting schema…");
      const reloaded = await fetch(`${API}/projects/${p.id}/reload`, {
        method: "POST",
      }).then((r) => r.json());
      setProjectId(p.id);
      setStatus(
        `Connected. ${reloaded.table_count} tables, ${reloaded.column_count} columns ingested.`
      );
    } catch (e: any) {
      setStatus("Error: " + e.message);
    } finally {
      setBusy(false);
    }
  }

  async function ask(forceBad = false, confirmed = false) {
    if (!projectId) return;
    setBusy(true);
    setResult(null);
    setStatus("Thinking…");
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
      setStatus(
        r.needs_clarification
          ? "Needs confirmation."
          : r.ok
          ? `Done (retries: ${r.retry_count}).`
          : "Query returned an error."
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
      <p style={{ opacity: 0.6, marginTop: -8 }}>Ask your database in plain English.</p>

      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <input
          value={dbUrl}
          onChange={(e) => setDbUrl(e.target.value)}
          style={inputStyle}
          placeholder="postgres connection URL"
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
          <button onClick={() => ask(false)} disabled={busy} style={btnStyle}>
            Ask
          </button>
          <button
            onClick={() => ask(true)}
            disabled={busy}
            style={{ ...btnStyle, background: "#3a2a2a", borderColor: "#5a3a3a" }}
            title="Injects a bad column to demonstrate the validator + self-correction loop"
          >
            Ask (force guardrail)
          </button>
        </div>
      )}

      {status && (
        <div style={{ marginTop: 12, fontSize: 13, opacity: 0.75 }}>{status}</div>
      )}

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
              <button onClick={() => ask(false, true)} disabled={busy} style={btnStyle}>
                Confirm & run
              </button>
            </div>
          )}
          <SQLDisplay sql={result.generated_sql} />
          {result.error && (
            <div style={{ color: "#ff8a8a", marginTop: 12 }}>
              {result.error}
              {result.needs_reload && " — click Connect & Ingest to reload the schema."}
            </div>
          )}
          <ChartRenderer chartType={result.chart_type} chartData={result.chart_data} />
          {cols.length > 0 && (
            <div style={{ overflowX: "auto", marginTop: 16 }}>
              <table style={{ borderCollapse: "collapse", width: "100%", fontSize: 13 }}>
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
    </div>
  );
}

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
const thStyle: React.CSSProperties = {
  textAlign: "left",
  borderBottom: "1px solid #2a2f3a",
  padding: "8px 10px",
  opacity: 0.7,
};
const tdStyle: React.CSSProperties = {
  borderBottom: "1px solid #21252d",
  padding: "8px 10px",
};
