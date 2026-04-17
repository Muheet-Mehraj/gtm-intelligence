import React, { useState, useRef, useEffect, useCallback } from "react";

/* GLOBAL STYLES */
const CSS = `
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:        #080a0e;
  --bg1:       #0d1017;
  --bg2:       #121720;
  --bg3:       #181e2a;
  --border:    rgba(255,255,255,0.07);
  --border2:   rgba(255,255,255,0.12);
  --text:      #e8eaf0;
  --text2:     #8890a4;
  --text3:     #555e72;
  --accent:    #00d4aa;
  --accent2:   #0099cc;
  --gold:      #f5a623;
  --danger:    #ff5a5a;
  --radius:    6px;
  --radius2:   10px;
  --mono:      'IBM Plex Mono', monospace;
  --sans:      'IBM Plex Sans', sans-serif;
}

html, body { height: 100%; background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 13px; }

::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

.app {
  display: grid;
  grid-template-rows: auto auto 1fr;
  height: 100vh;
  overflow: hidden;
}

.topbar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg1);
}
.logo {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  white-space: nowrap;
}
.pipeline-steps {
  display: flex;
  align-items: center;
  margin-left: auto;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text3);
  letter-spacing: 0.06em;
}
.ps {
  padding: 3px 10px;
  border: 1px solid var(--border);
  background: var(--bg2);
}
.ps:first-child { border-radius: var(--radius) 0 0 var(--radius); }
.ps:last-child  { border-radius: 0 var(--radius) var(--radius) 0; }
.ps.active { color: var(--accent); border-color: var(--accent); background: rgba(0,212,170,0.08); }
.pipe-arrow { color: var(--text3); font-size: 9px; }

.searchbar {
  padding: 14px 20px 10px;
  background: var(--bg1);
  border-bottom: 1px solid var(--border);
}
.search-row { display: flex; gap: 8px; margin-bottom: 10px; }
.search-input {
  flex: 1;
  background: var(--bg2);
  border: 1px solid var(--border2);
  border-radius: var(--radius);
  padding: 9px 14px;
  color: var(--text);
  font-family: var(--mono);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
}
.search-input::placeholder { color: var(--text3); }
.search-input:focus { border-color: var(--accent); }
.run-btn {
  background: var(--accent);
  color: #000;
  border: none;
  border-radius: var(--radius);
  padding: 9px 20px;
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  letter-spacing: 0.05em;
  transition: opacity 0.15s, transform 0.1s;
  white-space: nowrap;
}
.run-btn:hover { opacity: 0.85; }
.run-btn:active { transform: scale(0.97); }
.run-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.suggestions { display: flex; flex-wrap: wrap; gap: 6px; }
.sug-chip {
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 20px;
  padding: 4px 12px;
  font-size: 11px;
  color: var(--text2);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
  font-family: var(--sans);
}
.sug-chip:hover { border-color: var(--accent); color: var(--accent); }

.main {
  display: grid;
  grid-template-columns: 240px 1fr;
  overflow: hidden;
}

.sidebar {
  border-right: 1px solid var(--border);
  background: var(--bg1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.sidebar-hdr {
  padding: 12px 16px 8px;
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--text3);
  border-bottom: 1px solid var(--border);
}
.timeline { flex: 1; overflow-y: auto; padding: 8px 0; }
.tl-empty {
  padding: 24px 16px;
  font-size: 11px;
  color: var(--text3);
  font-family: var(--mono);
  line-height: 1.6;
}
.step-item {
  display: flex;
  gap: 10px;
  padding: 7px 16px;
  position: relative;
  animation: stepIn 0.2s ease;
}
@keyframes stepIn {
  from { opacity: 0; transform: translateX(-6px); }
  to   { opacity: 1; transform: translateX(0); }
}
.step-item::before {
  content: '';
  position: absolute;
  left: 21px; top: 24px; bottom: -7px;
  width: 1px;
  background: var(--border);
}
.step-item:last-child::before { display: none; }
.step-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-top: 3px;
  position: relative; z-index: 1;
}
.dot-running {
  background: var(--gold);
  box-shadow: 0 0 0 3px rgba(245,166,35,0.2);
  animation: dp 1.2s ease-in-out infinite;
}
@keyframes dp {
  0%,100% { box-shadow: 0 0 0 3px rgba(245,166,35,0.2); }
  50%      { box-shadow: 0 0 0 5px rgba(245,166,35,0.35); }
}
.dot-done  { background: var(--accent); }
.dot-error { background: var(--danger); }
.dot-retry { background: var(--gold); }
.step-lbl {
  font-family: var(--mono);
  font-size: 10px; font-weight: 600;
  letter-spacing: 0.08em;
  color: var(--text);
  display: flex; align-items: center; gap: 6px;
  margin-bottom: 2px;
}
.retry-badge {
  background: rgba(245,166,35,0.15);
  color: var(--gold);
  border: 1px solid rgba(245,166,35,0.3);
  border-radius: 3px;
  font-size: 8px;
  padding: 1px 5px;
  letter-spacing: 0.06em;
}
.step-dtl { font-size: 10px; color: var(--text3); font-family: var(--mono); line-height: 1.5; }
.conf-section {
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg2);
}
.conf-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.conf-lbl { font-size: 10px; color: var(--text3); font-family: var(--mono); letter-spacing: 0.06em; }
.conf-val { font-size: 13px; font-weight: 600; color: var(--accent); font-family: var(--mono); }
.conf-track { height: 3px; background: var(--border2); border-radius: 99px; overflow: hidden; }
.conf-fill { height: 100%; background: var(--accent); border-radius: 99px; transition: width 0.8s cubic-bezier(0.4,0,0.2,1); }

.right-panel { display: flex; flex-direction: column; overflow: hidden; }

.empty-state {
  flex: 1;
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  color: var(--text3); gap: 10px;
  font-family: var(--mono);
}
.empty-icon { font-size: 32px; opacity: 0.3; margin-bottom: 8px; }
.empty-state h2 { font-size: 14px; color: var(--text2); font-weight: 500; }
.empty-state p  { font-size: 11px; line-height: 1.6; text-align: center; max-width: 280px; }

.results { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.results-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg1);
  gap: 12px; flex-shrink: 0;
}
.tabs { display: flex; gap: 2px; }
.tab {
  padding: 5px 14px;
  font-size: 11px; font-family: var(--mono); letter-spacing: 0.05em;
  color: var(--text2);
  border: 1px solid transparent;
  border-radius: var(--radius);
  cursor: pointer; transition: all 0.15s;
  background: transparent;
}
.tab:hover { color: var(--text); background: var(--bg2); }
.tab.active { color: var(--accent); border-color: rgba(0,212,170,0.3); background: rgba(0,212,170,0.07); }
.res-meta { font-family: var(--mono); font-size: 10px; color: var(--text3); white-space: nowrap; }
.res-meta span { color: var(--accent); }

.sort-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--bg);
  flex-shrink: 0;
}
.sort-lbl { font-size: 10px; color: var(--text3); font-family: var(--mono); }
.sort-btn {
  padding: 3px 10px; font-size: 10px; font-family: var(--mono);
  color: var(--text2); border: 1px solid var(--border);
  border-radius: 20px; background: transparent; cursor: pointer;
  transition: all 0.15s;
}
.sort-btn:hover { border-color: var(--border2); color: var(--text); }
.sort-btn.active { border-color: var(--accent); color: var(--accent); background: rgba(0,212,170,0.07); }

.companies-list {
  flex: 1; overflow-y: auto;
  padding: 14px 20px;
  display: flex; flex-direction: column; gap: 10px;
}
.co-card {
  background: var(--bg1);
  border: 1px solid var(--border);
  border-radius: var(--radius2);
  padding: 14px 16px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
  position: relative; overflow: hidden;
}
.co-card::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--accent);
  opacity: 0; transition: opacity 0.15s;
}
.co-card:hover { border-color: var(--border2); background: var(--bg2); }
.co-card:hover::before { opacity: 1; }
.co-card.sel { border-color: rgba(0,212,170,0.4); background: var(--bg2); }
.co-card.sel::before { opacity: 1; }

.card-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 8px; }
.co-name { font-size: 15px; font-weight: 600; color: var(--text); letter-spacing: -0.01em; }
.icp-badge {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  padding: 3px 10px; border-radius: 4px; white-space: nowrap; letter-spacing: 0.04em;
}
.icp-high { background: rgba(0,212,170,0.15); color: var(--accent); border: 1px solid rgba(0,212,170,0.3); }
.icp-mid  { background: rgba(245,166,35,0.12); color: var(--gold);   border: 1px solid rgba(245,166,35,0.25); }
.icp-low  { background: rgba(255,90,90,0.1);   color: var(--danger); border: 1px solid rgba(255,90,90,0.2); }

.card-meta { display: flex; gap: 0; margin-bottom: 9px; flex-wrap: wrap; }
.mpill {
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; color: var(--text2);
  padding-right: 10px; margin-right: 10px;
  border-right: 1px solid var(--border);
}
.mpill:last-child { border-right: none; margin-right: 0; }
.mkey { color: var(--text3); font-family: var(--mono); font-size: 9px; letter-spacing: 0.06em; text-transform: uppercase; }

.signals { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 9px; }
.sig {
  font-size: 10px; padding: 2px 8px; border-radius: 3px;
  font-family: var(--mono);
  background: rgba(0,153,204,0.1); color: var(--accent2);
  border: 1px solid rgba(0,153,204,0.2); letter-spacing: 0.03em;
}

.insight { font-size: 11px; color: var(--text2); line-height: 1.55; display: flex; gap: 6px; align-items: flex-start; }
.ia { color: var(--accent); flex-shrink: 0; }
.why {
  font-size: 10px; color: var(--text3); font-family: var(--mono);
  line-height: 1.5; margin-top: 5px; padding-top: 5px;
  border-top: 1px solid var(--border);
}

.detail-panel { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 16px; }
.dsec { background: var(--bg1); border: 1px solid var(--border); border-radius: var(--radius2); overflow: hidden; }
.dsec-hdr {
  padding: 10px 14px;
  font-family: var(--mono); font-size: 9px; font-weight: 600;
  letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--text3);
  border-bottom: 1px solid var(--border);
  background: var(--bg2);
  display: flex; align-items: center; gap: 8px;
}
.ddot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); flex-shrink: 0; }
.dtabs { display: flex; gap: 6px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.email-body {
  padding: 16px; font-family: var(--mono); font-size: 12px;
  line-height: 1.8; color: var(--text2); white-space: pre-wrap;
}
.trace-list { padding: 10px 14px; display: flex; flex-direction: column; gap: 4px; }
.trace-item {
  display: flex; gap: 8px; align-items: flex-start;
  font-size: 11px; color: var(--text2); font-family: var(--mono);
  padding: 3px 0; border-bottom: 1px solid var(--border); line-height: 1.5;
}
.trace-item:last-child { border-bottom: none; }
.tarr { color: var(--accent); flex-shrink: 0; font-size: 10px; margin-top: 1px; }

.personas-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 14px; }
.persona-card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px; }
.persona-title { font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 4px; }
.persona-desc  { font-size: 11px; color: var(--text2); line-height: 1.5; }

.comp-row {
  display: grid; grid-template-columns: 120px 1fr 36px;
  gap: 12px; align-items: center;
  padding: 9px 14px; border-bottom: 1px solid var(--border); font-size: 11px;
}
.comp-row:last-child { border-bottom: none; }
.comp-name { font-weight: 500; color: var(--text); font-size: 12px; }
.comp-bar-wrap { height: 4px; background: var(--border2); border-radius: 99px; overflow: hidden; }
.comp-bar { height: 100%; background: var(--accent2); border-radius: 99px; }
.comp-score { font-family: var(--mono); font-size: 11px; color: var(--text2); text-align: right; }

.error-list { padding: 14px; }
.err-item { font-family: var(--mono); font-size: 11px; color: var(--danger); padding: 4px 0; border-bottom: 1px solid var(--border); display: flex; gap: 8px; }
`;

/* ─── TYPES ──────────────────────────────────────────────────────────────── */
type AgentStep = {
  step: string;
  status: "running" | "done" | "error" | "retry";
  detail: string;
  data?: Record<string, unknown>;
  ts: number;
};
type Company = {
  company: string; industry: string; region: string; employees: number;
  funding: string; icp_score: number; confidence: number;
  signals: string[]; insight: string; why_this_result?: string;
};
type GTMResult = {
  plan: Record<string, unknown>;
  results: Company[];
  signals: string[];
  confidence: number;
  reasoning_trace: string[];
  errors: string[];
  retry_count: number;
  gtm_strategy?: Record<string, Record<string, unknown>>;
};

/* ─── CONSTANTS ──────────────────────────────────────────────────────────── */
const STEP_LABELS: Record<string, string> = {
  planner: "PLANNER", retrieval: "RETRIEVAL",
  enrichment: "ENRICHMENT", critic: "CRITIC", gtm_strategy: "GTM STRATEGY",
};
const SUGGESTIONS = [
  "Find high-growth AI SaaS companies in the US",
  "Identify fintech startups hiring aggressively",
  "Find companies likely to churn their current GTM tools",
  "Enterprise health tech companies scaling in Europe",
];
const PIPELINE = ["Plan", "Retrieve", "Enrich", "Validate", "Target"];
const STEP_TO_PIPE: Record<string, number> = {
  planner: 0, retrieval: 1, enrichment: 2, critic: 3, gtm_strategy: 4,
};

function icpClass(score: number) {
  if (score >= 0.7) return "icp-high";
  if (score >= 0.4) return "icp-mid";
  return "icp-low";
}
function icpLabel(score: number) {
  const tier = score >= 0.7 ? "High ICP" : score >= 0.4 ? "Mid ICP" : "Low ICP";
  return `${tier} · ${score.toFixed(2)}`;
}

/* ─── COMPANY CARD ───────────────────────────────────────────────────────── */
function CompanyCard({ c, selected, onClick }: { c: Company; selected: boolean; onClick: () => void }) {
  return (
    <div className={`co-card ${selected ? "sel" : ""}`} onClick={onClick}>
      <div className="card-top">
        <div className="co-name">{c.company}</div>
        <div className={`icp-badge ${icpClass(c.icp_score)}`}>{icpLabel(c.icp_score)}</div>
      </div>
      <div className="card-meta">
        {[
          ["Industry", c.industry],
          ["Region", c.region],
          ["Employees", c.employees.toLocaleString()],
          ["Funding", c.funding],
          ["Confidence", `${Math.round(c.confidence * 100)}%`],
        ].map(([k, v]) => (
          <div key={k} className="mpill">
            <span className="mkey">{k}</span>
            <span>{v}</span>
          </div>
        ))}
      </div>
      {c.signals.length > 0 && (
        <div className="signals">
          {c.signals.map(s => <span key={s} className="sig">{s.replace(/_/g, " ")}</span>)}
        </div>
      )}
      <div className="insight">
        <span className="ia">↳</span>
        <span>{c.insight}</span>
      </div>
      {c.why_this_result && <div className="why">Why: {c.why_this_result}</div>}
    </div>
  );
}

/* ─── DETAIL PANEL */
function DetailPanel({ company, result }: { company: Company | null; result: GTMResult }) {
  const [tab, setTab] = useState<"email" | "personas" | "competitive" | "trace">("email");
  const cs = company ? result.gtm_strategy?.[company.company] : undefined;

  const email = cs?.email as string | undefined;
  const personas = cs?.personas as Array<{ title: string; description: string }> | undefined;
  const competitive = cs?.competitive as Array<{ name: string; score: number }> | undefined;

  const defaultEmail = company
    ? `Hi,\n\nNoticed that ${company.company} is ${company.signals[0]?.replace(/_/g, " ") ?? "scaling rapidly"} — a strong signal.\n\nFor teams at this stage, we typically see the biggest wins by focusing on outbound efficiency and pipeline velocity.\n\nWe've helped similar companies hit their goals faster. Open to a 15-min call?\n\nBest`
    : "";

  const defaultPersonas = [
    { title: "VP of Sales", description: "Focused on pipeline velocity and outbound conversion metrics." },
    { title: "Head of RevOps", description: "Owns data quality and CRM hygiene across the GTM stack." },
    { title: "CMO", description: "Driving brand awareness and inbound lead generation." },
    { title: "CEO / Founder", description: "Early-stage GTM ownership, looking for scalable growth levers." },
  ];

  const defaultCompetitive = [
    { name: "Salesforce", score: 0.82 }, { name: "HubSpot", score: 0.74 },
    { name: "Apollo.io", score: 0.61 }, { name: "Outreach", score: 0.45 },
  ];

  return (
    <div className="detail-panel">
      {company && (
        <div className="dsec">
          <div className="dsec-hdr">
            <div className="ddot" />
            {company.company} — GTM Intelligence
          </div>
          <div className="dtabs">
            {(["email", "personas", "competitive", "trace"] as const).map(t => (
              <button key={t} className={`tab ${tab === t ? "active" : ""}`} onClick={() => setTab(t)}>
                {t.toUpperCase()}
              </button>
            ))}
          </div>

          {tab === "email" && (
            <div className="email-body">{email ?? defaultEmail}</div>
          )}
          {tab === "personas" && (
            <div className="personas-grid">
              {(personas ?? defaultPersonas).map((p, i) => (
                <div key={i} className="persona-card">
                  <div className="persona-title">{p.title}</div>
                  <div className="persona-desc">{p.description}</div>
                </div>
              ))}
            </div>
          )}
          {tab === "competitive" && (
            <div>
              {(competitive ?? defaultCompetitive).map((c, i) => (
                <div key={i} className="comp-row">
                  <div className="comp-name">{c.name}</div>
                  <div className="comp-bar-wrap">
                    <div className="comp-bar" style={{ width: `${Math.round(c.score * 100)}%` }} />
                  </div>
                  <div className="comp-score">{Math.round(c.score * 100)}%</div>
                </div>
              ))}
            </div>
          )}
          {tab === "trace" && (
            <div className="trace-list">
              {result.reasoning_trace.map((t, i) => (
                <div key={i} className="trace-item">
                  <span className="tarr">›</span><span>{t}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!company && (
        <div className="dsec">
          <div className="dsec-hdr"><div className="ddot" />Reasoning Trace</div>
          <div className="trace-list">
            {result.reasoning_trace.map((t, i) => (
              <div key={i} className="trace-item">
                <span className="tarr">›</span><span>{t}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result.errors.length > 0 && (
        <div className="dsec">
          <div className="dsec-hdr">
            <div className="ddot" style={{ background: "var(--danger)" }} />Errors
          </div>
          <div className="error-list">
            {result.errors.map((e, i) => (
              <div key={i} className="err-item"><span>!</span><span>{e}</span></div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── MAIN APP ───────────────────────────────────────────────────────────── */
export default function App() {
  const [query, setQuery]     = useState("");
  const [result, setResult]   = useState<GTMResult | null>(null);
  const [steps, setSteps]     = useState<AgentStep[]>([]);
  const [running, setRunning] = useState(false);
  const [view, setView]       = useState<"companies" | "detail">("companies");
  const [selected, setSelected] = useState<Company | null>(null);
  const [sort, setSort]       = useState<"icp" | "employees" | "confidence">("icp");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const el = document.createElement("style");
    el.id = "gtm-styles-v2";
    el.textContent = CSS;
    if (!document.getElementById("gtm-styles-v2")) document.head.appendChild(el);
    return () => el.remove();
  }, []);

  useEffect(() => () => { wsRef.current?.close(); }, []);

 const runQuery = useCallback(async () => {
    if (!query.trim() || running) return;
    setResult(null); setSteps([]);
    setSelected(null); setView("companies");
    setRunning(true);

    try {
      const res = await fetch("https://gtm-intelligence.onrender.com/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query }),
      });
      const data = await res.json();
      setResult(data);
    } catch (err) {
      console.error(err);
    } finally {
      setRunning(false);
    }
  }, [query, running]);

  const sorted = result?.results ? [...result.results].sort((a, b) =>
    sort === "icp" ? b.icp_score - a.icp_score :
    sort === "employees" ? b.employees - a.employees :
    b.confidence - a.confidence
  ) : [];

  const activePipe = (() => {
    const last = steps[steps.length - 1];
    return last ? (STEP_TO_PIPE[last.step] ?? -1) : -1;
  })();

  return (
    <div className="app">
      {/* TOPBAR */}
      <div className="topbar">
        <div className="logo">◈ GTM Intelligence</div>
        <div className="pipeline-steps">
          {PIPELINE.map((p, i) => (
            <React.Fragment key={p}>
              {i > 0 && <span className="pipe-arrow"> › </span>}
              <span className={`ps ${running && i === activePipe ? "active" : ""}`}>{p}</span>
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* SEARCH */}
      <div className="searchbar">
        <div className="search-row">
          <input
            className="search-input"
            value={query}
            onChange={e => setQuery(e.target.value)}
            onKeyDown={e => e.key === "Enter" && runQuery()}
            placeholder="Describe your ideal customer profile..."
          />
          <button className="run-btn" onClick={runQuery} disabled={running || !query.trim()}>
            {running ? "Running…" : "Run →"}
          </button>
        </div>
        <div className="suggestions">
          {SUGGESTIONS.map(s => (
            <button key={s} className="sug-chip" onClick={() => setQuery(s)}>{s}</button>
          ))}
        </div>
      </div>

      {/* MAIN */}
      <div className="main">
        {/* SIDEBAR */}
        <div className="sidebar">
          <div className="sidebar-hdr">Agent Timeline</div>
          <div className="timeline">
            {steps.length === 0
              ? <div className="tl-empty">Waiting for<br />query…</div>
              : steps.map((s, i) => (
                <div key={i} className="step-item">
                  <div className={`step-dot dot-${s.status}`} />
                  <div>
                    <div className="step-lbl">
                      {STEP_LABELS[s.step] ?? s.step.toUpperCase()}
                      {s.status === "retry" && <span className="retry-badge">RETRY</span>}
                    </div>
                    <div className="step-dtl">{s.detail}</div>
                  </div>
                </div>
              ))
            }
          </div>
          {(result?.confidence ?? 0) > 0 && (
            <div className="conf-section">
              <div className="conf-row">
                <span className="conf-lbl">CONFIDENCE</span>
                <span className="conf-val">{Math.round((result?.confidence ?? 0) * 100)}%</span>
              </div>
              <div className="conf-track">
                <div className="conf-fill" style={{ width: `${(result?.confidence ?? 0) * 100}%` }} />
              </div>
            </div>
          )}
        </div>

        {/* RIGHT */}
        <div className="right-panel">
          {!result && !running && (
            <div className="empty-state">
              <div className="empty-icon">◈</div>
              <h2>Multi-agent outbound engine</h2>
              <p>Enter a natural language ICP query above to identify and score target accounts.</p>
            </div>
          )}

          {(result || running) && (
            <div className="results">
              <div className="results-hdr">
                <div className="tabs">
                  <button className={`tab ${view === "companies" ? "active" : ""}`} onClick={() => setView("companies")}>
                    COMPANIES
                  </button>
                  {selected && (
                    <button className={`tab ${view === "detail" ? "active" : ""}`} onClick={() => setView("detail")}>
                      {selected.company.toUpperCase()}
                    </button>
                  )}
                </div>
                {result && (
                  <div className="res-meta">
                    <span>{result.results.length}</span> accounts · retries <span>{result.retry_count}</span>
                  </div>
                )}
              </div>

              {view === "companies" && (
                <>
                  <div className="sort-bar">
                    <span className="sort-lbl">SORT BY</span>
                    {(["icp", "employees", "confidence"] as const).map(s => (
                      <button
                        key={s}
                        className={`sort-btn ${sort === s ? "active" : ""}`}
                        onClick={() => setSort(s)}
                      >
                        {s === "icp" ? "ICP Score" : s === "employees" ? "Employees" : "Confidence"}
                      </button>
                    ))}
                  </div>
                  <div className="companies-list">
                    {sorted.map((c, i) => (
                      <CompanyCard
                        key={i} c={c}
                        selected={selected?.company === c.company}
                        onClick={() => { setSelected(c); setView("detail"); }}
                      />
                    ))}
                    {running && sorted.length === 0 && (
                      <div style={{ color: "var(--text3)", fontFamily: "var(--mono)", fontSize: 11, padding: "20px 0" }}>
                        Fetching results…
                      </div>
                    )}
                  </div>
                </>
              )}

              {view === "detail" && result && (
                <DetailPanel company={selected} result={result} />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}