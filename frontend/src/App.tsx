import React, { useState, useRef, useEffect, useCallback } from "react";

const CSS = `
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

:root {
  --bg:      #0a0c10;
  --bg1:     #0f1218;
  --bg2:     #141820;
  --bg3:     #1a2030;
  --border:  rgba(255,255,255,0.06);
  --border2: rgba(255,255,255,0.11);
  --text:    #e4e8f0;
  --text2:   #7a8499;
  --text3:   #444e62;
  --accent:  #00e5b0;
  --accent2: #0ab4e8;
  --gold:    #f0a830;
  --danger:  #ff5060;
  --radius:  8px;
  --radius2: 12px;
  --mono:    'JetBrains Mono', monospace;
  --sans:    'Space Grotesk', sans-serif;
}

html, body { height: 100%; background: var(--bg); color: var(--text); font-family: var(--sans); font-size: 13px; overflow: hidden; }

::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 2px; }

.app { display: flex; flex-direction: column; height: 100vh; overflow: hidden; }

/* ── HERO ── */
.hero {
  text-align: center;
  padding: 36px 20px 24px;
  background: var(--bg);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.hero-title { font-size: 42px; font-weight: 700; letter-spacing: -0.03em; line-height: 1; margin-bottom: 10px; }
.hero-title span:first-child { color: var(--text); }
.hero-title span:last-child  { color: var(--accent); }
.hero-sub { font-family: var(--mono); font-size: 11px; color: var(--text3); letter-spacing: 0.06em; margin-bottom: 24px; }
.hero-sub .arr { color: var(--accent); margin: 0 4px; }

/* ── SEARCH ── */
.search-wrap { display: flex; gap: 10px; max-width: 780px; margin: 0 auto 14px; }
.search-input {
  flex: 1; background: var(--bg2); border: 1px solid var(--border2); border-radius: var(--radius);
  padding: 12px 16px; color: var(--text); font-family: var(--mono); font-size: 13px; outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.search-input::placeholder { color: var(--text3); }
.search-input:focus { border-color: var(--accent); box-shadow: 0 0 0 3px rgba(0,229,176,0.08); }
.run-btn {
  background: var(--accent); color: #000; border: none; border-radius: var(--radius);
  padding: 12px 24px; font-family: var(--mono); font-size: 13px; font-weight: 600;
  cursor: pointer; letter-spacing: 0.04em; transition: opacity 0.15s, transform 0.1s; white-space: nowrap;
}
.run-btn:hover { opacity: 0.85; }
.run-btn:active { transform: scale(0.97); }
.run-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.suggestions { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; max-width: 780px; margin: 0 auto; }
.sug-chip {
  background: var(--bg2); border: 1px solid var(--border); border-radius: 20px;
  padding: 5px 14px; font-size: 11px; color: var(--text2); cursor: pointer;
  transition: border-color 0.15s, color 0.15s; font-family: var(--sans);
}
.sug-chip:hover { border-color: var(--accent); color: var(--accent); }

/* ── RETRY BANNER ── */
.retry-banner {
  display: flex; align-items: center; gap: 10px;
  background: rgba(240,168,48,0.08);
  border-bottom: 1px solid rgba(240,168,48,0.2);
  padding: 7px 20px;
  font-family: var(--mono); font-size: 11px; color: var(--gold);
  flex-shrink: 0;
}
.retry-banner-dot {
  width: 7px; height: 7px; border-radius: 50%; background: var(--gold); flex-shrink: 0;
}
.retry-banner-count {
  font-weight: 700; margin-right: 4px;
}

/* ── BODY ── */
.body { display: grid; grid-template-columns: 260px 1fr; flex: 1; overflow: hidden; }

/* ── SIDEBAR ── */
.sidebar { background: var(--bg1); border-right: 1px solid var(--border); display: flex; flex-direction: column; overflow: hidden; }
.sidebar-hdr {
  padding: 16px 18px 10px; font-family: var(--mono); font-size: 9px; font-weight: 600;
  letter-spacing: 0.16em; text-transform: uppercase; color: var(--text3);
  border-bottom: 1px solid var(--border);
}
.timeline { flex: 1; overflow-y: auto; padding: 12px 0; }
.tl-empty { padding: 28px 18px; font-size: 11px; color: var(--text3); font-family: var(--mono); line-height: 1.7; }

.step-item { display: flex; gap: 12px; padding: 10px 18px; position: relative; animation: stepIn 0.25s ease; }
@keyframes stepIn {
  from { opacity: 0; transform: translateX(-8px); }
  to   { opacity: 1; transform: translateX(0); }
}
.step-item::before {
  content: ''; position: absolute; left: 23px; top: 26px; bottom: -10px;
  width: 1px; background: var(--border);
}
.step-item:last-child::before { display: none; }

.step-dot { width: 11px; height: 11px; border-radius: 50%; flex-shrink: 0; margin-top: 3px; position: relative; z-index: 1; }
.dot-running { background: var(--gold); box-shadow: 0 0 0 3px rgba(240,168,48,0.2); animation: pulse 1.2s ease-in-out infinite; }
@keyframes pulse {
  0%,100% { box-shadow: 0 0 0 3px rgba(240,168,48,0.2); }
  50%      { box-shadow: 0 0 0 6px rgba(240,168,48,0.35); }
}
.dot-done  { background: var(--accent); box-shadow: 0 0 0 3px rgba(0,229,176,0.15); }
.dot-error { background: var(--danger); }
.dot-retry { background: var(--gold); }

.step-lbl {
  font-family: var(--mono); font-size: 11px; font-weight: 600; letter-spacing: 0.06em;
  color: var(--text); display: flex; align-items: center; gap: 6px; margin-bottom: 3px;
}
.retry-badge {
  background: rgba(240,168,48,0.15); color: var(--gold);
  border: 1px solid rgba(240,168,48,0.3); border-radius: 3px; font-size: 8px; padding: 1px 5px;
}
.step-dtl { font-size: 10px; color: var(--text3); font-family: var(--mono); line-height: 1.5; }

.conf-section { padding: 14px 18px; border-top: 1px solid var(--border); background: var(--bg2); }
.conf-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.conf-lbl { font-size: 10px; color: var(--text3); font-family: var(--mono); letter-spacing: 0.08em; }
.conf-val { font-size: 14px; font-weight: 700; color: var(--accent); font-family: var(--mono); }
.conf-track { height: 3px; background: var(--border2); border-radius: 99px; overflow: hidden; }
.conf-fill { height: 100%; background: var(--accent); border-radius: 99px; transition: width 0.9s cubic-bezier(0.4,0,0.2,1); }

/* ── RIGHT PANEL ── */
.right-panel { display: flex; flex-direction: column; overflow: hidden; }

.empty-state {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: var(--text3); gap: 12px; font-family: var(--mono);
}
.empty-icon { font-size: 36px; opacity: 0.2; margin-bottom: 6px; }
.empty-state h2 { font-size: 14px; color: var(--text2); font-weight: 500; }
.empty-state p  { font-size: 11px; line-height: 1.7; text-align: center; max-width: 260px; }

/* ── RESULTS ── */
.results { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.results-hdr {
  display: flex; align-items: center; justify-content: space-between;
  padding: 10px 20px; border-bottom: 1px solid var(--border);
  background: var(--bg1); flex-shrink: 0;
}
.tabs { display: flex; gap: 2px; }
.tab {
  padding: 5px 14px; font-size: 11px; font-family: var(--mono); letter-spacing: 0.04em;
  color: var(--text2); border: 1px solid transparent; border-radius: var(--radius);
  cursor: pointer; transition: all 0.15s; background: transparent;
}
.tab:hover { color: var(--text); background: var(--bg2); }
.tab.active { color: var(--accent); border-color: rgba(0,229,176,0.3); background: rgba(0,229,176,0.07); }
.res-meta { font-family: var(--mono); font-size: 10px; color: var(--text3); }
.res-meta span { color: var(--accent); }

.sort-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 20px; border-bottom: 1px solid var(--border); background: var(--bg); flex-shrink: 0;
}
.sort-lbl { font-size: 10px; color: var(--text3); font-family: var(--mono); }
.sort-btn {
  padding: 3px 10px; font-size: 10px; font-family: var(--mono); color: var(--text2);
  border: 1px solid var(--border); border-radius: 20px; background: transparent; cursor: pointer; transition: all 0.15s;
}
.sort-btn:hover { border-color: var(--border2); color: var(--text); }
.sort-btn.active { border-color: var(--accent); color: var(--accent); background: rgba(0,229,176,0.07); }

.companies-list { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 10px; }

/* ── COMPANY CARD ── */
.co-card {
  background: var(--bg1); border: 1px solid var(--border); border-radius: var(--radius2);
  padding: 18px 18px; cursor: pointer; transition: border-color 0.15s, background 0.15s;
  position: relative; overflow: hidden;
}
.co-card::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
  background: var(--accent); opacity: 0; transition: opacity 0.15s;
}
.co-card:hover { border-color: var(--border2); background: var(--bg2); }
.co-card:hover::before { opacity: 1; }
.co-card.sel { border-color: rgba(0,229,176,0.35); background: var(--bg2); }
.co-card.sel::before { opacity: 1; }

.card-top { display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 12px; }
.co-name { font-size: 16px; font-weight: 700; color: var(--text); letter-spacing: -0.02em; }
.icp-badge { font-family: var(--mono); font-size: 10px; font-weight: 600; padding: 4px 10px; border-radius: 5px; white-space: nowrap; }
.icp-high { background: rgba(0,229,176,0.12); color: var(--accent); border: 1px solid rgba(0,229,176,0.25); }
.icp-mid  { background: rgba(240,168,48,0.1);  color: var(--gold);   border: 1px solid rgba(240,168,48,0.22); }
.icp-low  { background: rgba(255,80,96,0.08);  color: var(--danger); border: 1px solid rgba(255,80,96,0.18); }

.card-meta { display: flex; flex-wrap: wrap; gap: 0; margin-bottom: 10px; }
.mpill { display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text2); padding-right: 12px; margin-right: 12px; border-right: 1px solid var(--border); }
.mpill:last-child { border-right: none; margin-right: 0; }
.mkey { color: var(--text3); font-family: var(--mono); font-size: 9px; letter-spacing: 0.07em; text-transform: uppercase; }

.signals { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 12px; }
.sig { font-size: 10px; padding: 2px 8px; border-radius: 4px; font-family: var(--mono); background: rgba(10,180,232,0.08); color: var(--accent2); border: 1px solid rgba(10,180,232,0.18); }

.insight { font-size: 12px; color: var(--text2); line-height: 1.6; display: flex; gap: 7px; align-items: flex-start; font-style: italic; margin-bottom: 6px;}
.ia { color: var(--accent); flex-shrink: 0; font-style: normal; }
.why { font-size: 10px; color: var(--text3); font-family: var(--mono); line-height: 1.5; margin-top: 12px; padding-top: 8px; border-top: 1px solid var(--border); }

/* ── DETAIL PANEL ── */
.detail-panel { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 14px; }
.dsec { background: var(--bg1); border: 1px solid var(--border); border-radius: var(--radius2); overflow: hidden; }
.dsec-hdr {
  padding: 10px 16px; font-family: var(--mono); font-size: 9px; font-weight: 600;
  letter-spacing: 0.13em; text-transform: uppercase; color: var(--text3);
  border-bottom: 1px solid var(--border); background: var(--bg2);
  display: flex; align-items: center; gap: 8px;
}
.ddot { width: 6px; height: 6px; border-radius: 50%; background: var(--accent); flex-shrink: 0; }
.dtabs { display: flex; gap: 6px; padding: 10px 16px; border-bottom: 1px solid var(--border); }
.email-body { padding: 16px; font-family: var(--mono); font-size: 12px; line-height: 1.9; color: var(--text2); white-space: pre-wrap; }
.trace-list { padding: 10px 16px; display: flex; flex-direction: column; gap: 4px; }
.trace-item { display: flex; gap: 8px; align-items: flex-start; font-size: 11px; color: var(--text2); font-family: var(--mono); padding: 4px 0; border-bottom: 1px solid var(--border); line-height: 1.5; }
.trace-item:last-child { border-bottom: none; }
.tarr { color: var(--accent); flex-shrink: 0; font-size: 10px; margin-top: 1px; }

.personas-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; padding: 14px; }
.persona-card { background: var(--bg2); border: 1px solid var(--border); border-radius: var(--radius); padding: 13px; }
.persona-title { font-size: 12px; font-weight: 600; color: var(--text); margin-bottom: 5px; }
.persona-desc  { font-size: 11px; color: var(--text2); line-height: 1.55; }

.comp-row { display: grid; grid-template-columns: 120px 1fr 40px; gap: 12px; align-items: center; padding: 9px 16px; border-bottom: 1px solid var(--border); font-size: 11px; }
.comp-row:last-child { border-bottom: none; }
.comp-name { font-weight: 500; color: var(--text); font-size: 12px; }
.comp-bar-wrap { height: 3px; background: var(--border2); border-radius: 99px; overflow: hidden; }
.comp-bar { height: 100%; background: var(--accent2); border-radius: 99px; }
.comp-score { font-family: var(--mono); font-size: 11px; color: var(--text2); text-align: right; }

.error-list { padding: 14px; }
.err-item { font-family: var(--mono); font-size: 11px; color: var(--danger); padding: 4px 0; border-bottom: 1px solid var(--border); display: flex; gap: 8px; }

.fetching { color: var(--text3); font-family: var(--mono); font-size: 11px; padding: 24px 0; display: flex; align-items: center; gap: 8px; }
.fetching::before { content: ''; width: 8px; height: 8px; border-radius: 50%; background: var(--gold); animation: pulse 1.2s ease-in-out infinite; flex-shrink: 0; }
`;

/* ─── TYPES ── */
type AgentStep = { step: string; status: "running"|"done"|"error"|"retry"; detail: string; ts: number; };
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
  spans?: Array<{ event: string }>;
};

/* ─── CONSTANTS ── */
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

const WS_URL = "ws://localhost:8000/ws/run";

function icpClass(s: number) { return s >= 0.7 ? "icp-high" : s >= 0.4 ? "icp-mid" : "icp-low"; }
function icpLabel(s: number) {
  return `${s >= 0.7 ? "High ICP" : s >= 0.4 ? "Mid ICP" : "Low ICP"} · ${s.toFixed(2)}`;
}

/* ─── COMPANY CARD ── */
function CompanyCard({ c, selected, onClick }: { c: Company; selected: boolean; onClick: () => void }) {
  return (
    <div className={`co-card ${selected ? "sel" : ""}`} onClick={onClick}>
      
      <div className="card-top">
        <div className="co-name">{c.company}</div>
        <div className={`icp-badge ${icpClass(c.icp_score)}`}>
          {icpLabel(c.icp_score)}
        </div>
      </div>

      <div className="card-meta">
        {[["Industry", c.industry],
          ["Region", c.region],
          ["Employees", c.employees.toLocaleString()],
          ["Funding", c.funding],
          ["Confidence", `${Math.round(c.confidence * 100)}%`]
        ].map(([k, v]) => (
          <div key={k} className="mpill">
            <span className="mkey">{k}</span>
            <span>{v}</span>
          </div>
        ))}
      </div>

      {c.signals.length > 0 && (
        <div className="signals">
          {c.signals.map(s => (
            <span key={s} className="sig">{s.replace(/_/g, " ")}</span>
          ))}
        </div>
      )}

      {/* SINGLE insight + spacing */}
      <div style={{ marginTop: "6px" }}>
        <div className="insight">
          <span className="ia">↳</span>
          <span>{c.insight}</span>
        </div>

        {c.why_this_result && (
          <div className="why">
            Why: {c.why_this_result}
          </div>
        )}
      </div>

    </div>
  );
}

/* ─── DETAIL PANEL ── */
function DetailPanel({ company, result }: { company: Company | null; result: GTMResult }) {
  const [tab, setTab] = useState<"email"|"personas"|"competitive"|"trace">("email");
  const cs = company ? result.gtm_strategy?.[company.company] : undefined;

  // Pull per-company GTM data from gtm_strategy arrays
  const emailEntry = result.gtm_strategy?.email_snippets as Array<{ company: string; email: string }> | undefined;
  const personaEntry = result.gtm_strategy?.persona_targeting as Array<{ company: string; personas: Record<string, unknown> }> | undefined;
  const compEntry = result.gtm_strategy?.competitive_intelligence as Array<{ company: string; competitive: Record<string, string> }> | undefined;

  const email = company
    ? emailEntry?.find(e => e.company === company.company)?.email
    : undefined;

  const personasRaw = company
    ? personaEntry?.find(p => p.company === company.company)?.personas
    : undefined;
  const personasArr = personasRaw
    ? Object.values(personasRaw).map((p: unknown) => {
        const persona = p as Record<string, string>;
        return { title: persona.persona ?? "", description: persona.value_prop ?? persona.pain_point ?? "" };
      })
    : undefined;

  const compRaw = company
    ? compEntry?.find(c => c.company === company.company)?.competitive
    : undefined;
  const compArr = compRaw?.likely_stack
    ? compRaw.likely_stack.split(",").map((name: string, i: number) => ({
        name: name.trim(), score: Math.max(0.3, 0.85 - i * 0.12),
      }))
    : undefined;

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
          <div className="dsec-hdr"><div className="ddot" />{company.company} — GTM Intelligence</div>
          <div className="dtabs">
            {(["email","personas","competitive","trace"] as const).map(t => (
              <button key={t} className={`tab ${tab===t?"active":""}`} onClick={() => setTab(t)}>{t.toUpperCase()}</button>
            ))}
          </div>
          {tab === "email" && <div className="email-body">{email ?? defaultEmail}</div>}
          {tab === "personas" && (
            <div className="personas-grid">
              {(personasArr ?? defaultPersonas).map((p, i) => (
                <div key={i} className="persona-card">
                  <div className="persona-title">{p.title}</div>
                  <div className="persona-desc">{p.description}</div>
                </div>
              ))}
            </div>
          )}
          {tab === "competitive" && (
            <div>
              {(compArr ?? defaultCompetitive).map((c, i) => (
                <div key={i} className="comp-row">
                  <div className="comp-name">{c.name}</div>
                  <div className="comp-bar-wrap"><div className="comp-bar" style={{ width: `${Math.round(c.score*100)}%` }} /></div>
                  <div className="comp-score">{Math.round(c.score*100)}%</div>
                </div>
              ))}
            </div>
          )}
          {tab === "trace" && (
            <div className="trace-list">
              {result.reasoning_trace.map((t, i) => (
                <div key={i} className="trace-item"><span className="tarr">›</span><span>{t}</span></div>
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
              <div key={i} className="trace-item"><span className="tarr">›</span><span>{t}</span></div>
            ))}
          </div>
        </div>
      )}
      {result.errors.length > 0 && (
        <div className="dsec">
          <div className="dsec-hdr"><div className="ddot" style={{ background: "var(--danger)" }} />Errors</div>
          <div className="error-list">
            {result.errors.map((e, i) => <div key={i} className="err-item"><span>!</span><span>{e}</span></div>)}
          </div>
        </div>
      )}
    </div>
  );
}

/* ── MAIN APP ── */
export default function App() {
  const [query, setQuery]       = useState("");
  const [result, setResult]     = useState<GTMResult | null>(null);
  const [steps, setSteps]       = useState<AgentStep[]>([]);
  const [running, setRunning]   = useState(false);
  const [view, setView]         = useState<"companies"|"detail">("companies");
  const [selected, setSelected] = useState<Company | null>(null);
  const [sort, setSort]         = useState<"icp"|"employees"|"confidence">("icp");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const el = document.createElement("style");
    el.id = "gtm-styles-v4";
    el.textContent = CSS;
    if (!document.getElementById("gtm-styles-v4")) document.head.appendChild(el);
    return () => el.remove();
  }, []);

  useEffect(() => () => { wsRef.current?.close(); }, []);

  const runQuery = useCallback(() => {
    if (!query.trim() || running) return;
    setResult(null);
    setSteps([]);
    setSelected(null);
    setView("companies");
    setRunning(true);

    // #2: WebSocket for real streaming step updates
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => ws.send(JSON.stringify({ query }));

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      // #: stream each agent step live as it arrives
      if (msg.type === "agent_update") {
        const step: AgentStep = {
          step: msg.step,
          status: msg.status,
          detail: msg.detail,
          ts: Date.now(),
        };
        setSteps(prev => {
          // replace existing entry for same step+status=running, or append
          const idx = prev.findIndex(s => s.step === msg.step && s.status === "running");
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = step;
            return updated;
          }
          return [...prev, step];
        });
      }

      // Final result
      if (msg.type === "result") {
        setResult(msg.data);
        ws.close();
        setRunning(false);
      }

      if (msg.type === "fatal" || msg.type === "error") {
        console.error("WS error:", msg.message);
        setRunning(false);
      }
    };

    ws.onerror = () => setRunning(false);
    ws.onclose = () => setRunning(false);
  }, [query, running]);

  const sorted = result?.results ? [...result.results].sort((a, b) =>
    sort === "icp" ? b.icp_score - a.icp_score :
    sort === "employees" ? b.employees - a.employees :
    b.confidence - a.confidence
  ) : [];

  //  show retry count from result
  const retryCount = result?.retry_count ?? 0;

  return (
    <div className="app">
      {/* HERO */}
      <div className="hero">
        <div className="hero-title"><span>GTM </span><span>Intelligence</span></div>
        <div className="hero-sub">
          Multi-agent outbound intelligence engine
          <span className="arr">→</span>Plan
          <span className="arr">→</span>Retrieve
          <span className="arr">→</span>Enrich
          <span className="arr">→</span>Validate
          <span className="arr">→</span>Target
        </div>
        <div className="search-wrap">
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

      {/*  retry banner — shown when pipeline had to retry */}
      {result && retryCount > 0 && (
        <div className="retry-banner">
          <div className="retry-banner-dot" />
          <span className="retry-banner-count">{retryCount} retry{retryCount > 1 ? " attempts" : ""}</span>
          — critic rejected initial results and re-planned to improve quality
        </div>
      )}

      {/* BODY */}
      <div className="body">
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
                      {/*  retry badge on critic step */}
                      {s.status === "retry" && <span className="retry-badge">RETRY</span>}
                    </div>
                    <div className="step-dtl">{s.detail}</div>
                  </div>
                </div>
              ))
            }
            {running && steps[steps.length - 1]?.status !== "running" && (
              <div className="step-item">
                <div className="step-dot dot-running" />
                <div>
                  <div className="step-lbl">PROCESSING</div>
                  <div className="step-dtl">Running pipeline…</div>
                </div>
              </div>
            )}
          </div>
          {(result?.confidence ?? 0) > 0 && (
            <div className="conf-section">
              <div className="conf-row">
                <span className="conf-lbl">Confidence</span>
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
                  <button className={`tab ${view==="companies"?"active":""}`} onClick={() => setView("companies")}>COMPANIES</button>
                  {selected && (
                    <button className={`tab ${view==="detail"?"active":""}`} onClick={() => setView("detail")}>
                      {selected.company.toUpperCase()}
                    </button>
                  )}
                </div>
                {result && (
                  <div className="res-meta">
                    <span>{result.results.length}</span> accounts
                    {retryCount > 0 && <> · retried <span>{retryCount}×</span></>}
                  </div>
                )}
              </div>

              {view === "companies" && (
                <>
                  <div className="sort-bar">
                    <span className="sort-lbl">SORT BY</span>
                    {(["icp","employees","confidence"] as const).map(s => (
                      <button key={s} className={`sort-btn ${sort===s?"active":""}`} onClick={() => setSort(s)}>
                        {s === "icp" ? "ICP Score" : s === "employees" ? "Employees" : "Confidence"}
                      </button>
                    ))}
                  </div>
                  <div className="companies-list">

                   {sorted.map((c, i) => (
                    <div key={i}>
                     <CompanyCard
                       c={c}
                       selected={selected?.company === c.company}
                       onClick={() => {
                        setSelected(c);
                        setView("detail");
                      }}
                     />

                     {/* preview insight */}
                     <div style={{ marginTop: "-4px", marginBottom: "10px", paddingLeft: "12px" }}>
                       <span style={{ color: "var(--text3)", fontSize: "12px", fontStyle: "italic" }}>
                         ↳ {c.insight?.slice(0, 90)}
                         {c.insight?.length > 90 ? "..." : ""}
                       </span>
                     </div>
                   </div>
                  ))}

                 {running && sorted.length === 0 && (
                  <div className="fetching">Fetching results…</div>
                )}

               </div>  {/* ← VERY IMPORTANT: close list */}
              </>
             )} {/* Close view === "companies" block */}

             {/* Detail View */}
             {view === "detail" && result && (
              <DetailPanel company={selected} result={result} />
             )}

            </div>
          )} 
        </div> {/* Close right-panel */}
      </div> {/* Close body */}
    </div> 
  );
}
