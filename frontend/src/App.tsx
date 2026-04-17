import { useState, useRef, useEffect } from "react";

/*  Types */
type AgentStep = {
  step: string;
  status: "running" | "done" | "error" | "retry";
  detail: string;
  data?: Record<string, unknown>;
  ts: number;
};

type Company = {
  company: string;
  industry: string;
  region: string;
  employees: number;
  funding: string;
  icp_score: number;
  confidence: number;
  signals: string[];
  insight: string;
  why_this_result?: string;
};

type PersonaTarget = {
  persona: string;
  pain_point: string;
  value_prop: string;
  hook: string;
  cta: string;
};

type CompetitiveIntel = {
  likely_stack: string;
  positioning_strategy: string;
  differentiation: string;
};

type GTMResult = {
  plan: Record<string, unknown>;
  results: Company[];
  signals: string[];
  gtm_strategy: {
    hooks: { company: string; hook: string }[];
    angles: { company: string; angle: string }[];
    email_snippets: { company: string; email: string }[];
    persona_targeting?: { company: string; personas: Record<string, PersonaTarget> }[];
    competitive_intelligence?: { company: string; competitive: CompetitiveIntel }[];
  };
  confidence: number;
  reasoning_trace: string[];
  errors: string[];
  retry_count: number;
};

/* ─── Styles (injected once) ────────────────────────────── */
const STYLES = `
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Syne:wght@400;600;700;800&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg: #080b0f;
    --bg2: #0f1318;
    --bg3: #161c24;
    --border: rgba(255,255,255,0.07);
    --border2: rgba(255,255,255,0.12);
    --text: #e8edf2;
    --muted: #6b7a8d;
    --accent: #00e5c0;
    --accent2: #0090ff;
    --warn: #f5a623;
    --danger: #ff4d4d;
    --success: #00e5c0;
    --mono: 'IBM Plex Mono', monospace;
    --sans: 'Syne', sans-serif;
  }

  body { background: var(--bg); color: var(--text); font-family: var(--mono); }

  .app {
    min-height: 100vh;
    max-width: 1100px;
    margin: 0 auto;
    padding: 48px 24px;
  }

  /* header */
  .header { margin-bottom: 48px; }
  .header h1 {
    font-family: var(--sans);
    font-size: 36px;
    font-weight: 800;
    letter-spacing: -1px;
    color: var(--text);
    line-height: 1;
  }
  .header h1 span { color: var(--accent); }
  .header p { color: var(--muted); font-size: 13px; margin-top: 8px; letter-spacing: 0.5px; }

  /* input row */
  .input-row {
    display: flex;
    gap: 10px;
    margin-bottom: 40px;
  }
  .query-input {
    flex: 1;
    background: var(--bg3);
    border: 1px solid var(--border2);
    border-radius: 8px;
    padding: 14px 18px;
    color: var(--text);
    font-family: var(--mono);
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
  }
  .query-input::placeholder { color: var(--muted); }
  .query-input:focus { border-color: var(--accent); }
  .run-btn {
    background: var(--accent);
    color: #000;
    border: none;
    border-radius: 8px;
    padding: 14px 28px;
    font-family: var(--sans);
    font-weight: 700;
    font-size: 14px;
    cursor: pointer;
    letter-spacing: 0.5px;
    transition: opacity 0.15s, transform 0.1s;
    white-space: nowrap;
  }
  .run-btn:hover { opacity: 0.85; }
  .run-btn:active { transform: scale(0.98); }
  .run-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* example queries */
  .examples { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 40px; }
  .ex-chip {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 6px 14px;
    font-size: 11px;
    color: var(--muted);
    cursor: pointer;
    transition: border-color 0.15s, color 0.15s;
    white-space: nowrap;
  }
  .ex-chip:hover { border-color: var(--accent); color: var(--accent); }

  /* layout */
  .main-grid {
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 20px;
    align-items: start;
  }

  /* timeline panel */
  .timeline-panel {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    position: sticky;
    top: 24px;
  }
  .panel-title {
    font-family: var(--sans);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 16px;
  }

  /* agent step */
  .step-row {
    display: flex;
    align-items: flex-start;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid var(--border);
    animation: fadeIn 0.3s ease;
  }
  .step-row:last-child { border-bottom: none; }

  @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; } }

  .step-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-top: 5px;
    flex-shrink: 0;
  }
  .dot-running { background: var(--warn); animation: pulse 1s infinite; }
  .dot-done    { background: var(--success); }
  .dot-retry   { background: var(--warn); }
  .dot-error   { background: var(--danger); }

  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.4; } }

  .step-body { flex: 1; min-width: 0; }
  .step-name {
    font-size: 12px;
    font-weight: 500;
    color: var(--text);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .step-detail { font-size: 11px; color: var(--muted); margin-top: 2px; line-height: 1.4; }
  .step-retry-badge {
    display: inline-block;
    background: rgba(245,166,35,0.15);
    color: var(--warn);
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
    margin-left: 6px;
  }

  /* confidence meter */
  .confidence-block { margin-top: 20px; }
  .conf-label { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); margin-bottom: 6px; }
  .conf-val { color: var(--accent); font-weight: 600; }
  .conf-track { height: 4px; background: var(--border2); border-radius: 2px; overflow: hidden; }
  .conf-fill {
    height: 100%;
    border-radius: 2px;
    background: linear-gradient(90deg, var(--accent2), var(--accent));
    transition: width 0.6s ease;
  }

  /* results area */
  .results-area { display: flex; flex-direction: column; gap: 16px; }

  /* section heading */
  .section-heading {
    display: flex;
    align-items: center;
    gap: 12px;
    font-family: var(--sans);
    font-size: 13px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--muted);
    margin: 8px 0 4px;
  }
  .section-heading::after { content: ''; flex: 1; height: 1px; background: var(--border); }

  /* company card */
  .company-card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    transition: border-color 0.2s;
    animation: fadeIn 0.4s ease;
  }
  .company-card.high { border-color: rgba(0,229,192,0.3); }
  .company-card:hover { border-color: var(--border2); }

  .card-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 14px; }
  .company-name { font-family: var(--sans); font-size: 20px; font-weight: 700; color: var(--text); }
  .icp-badge {
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 6px;
    white-space: nowrap;
    flex-shrink: 0;
  }
  .icp-high { background: rgba(0,229,192,0.15); color: var(--accent); }
  .icp-mid  { background: rgba(0,144,255,0.15); color: var(--accent2); }
  .icp-low  { background: rgba(255,255,255,0.05); color: var(--muted); }

  .card-meta { display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 12px; }
  .meta-item { font-size: 12px; color: var(--muted); }
  .meta-item span { color: var(--text); }

  .signals-row { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
  .signal-chip {
    font-size: 11px;
    padding: 3px 8px;
    border-radius: 4px;
    background: rgba(0,144,255,0.1);
    color: var(--accent2);
    border: 1px solid rgba(0,144,255,0.2);
  }

  .insight-text { font-size: 12px; color: var(--muted); font-style: italic; line-height: 1.5; }

  /* GTM section tabs */
  .gtm-card {
    background: var(--bg2);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    animation: fadeIn 0.4s ease;
  }
  .gtm-card-header { padding: 16px 20px; border-bottom: 1px solid var(--border); }
  .gtm-company-name { font-family: var(--sans); font-size: 17px; font-weight: 700; }
  .hook-text { font-size: 12px; color: var(--muted); margin-top: 4px; }

  .tab-bar { display: flex; border-bottom: 1px solid var(--border); }
  .tab-btn {
    padding: 10px 16px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    color: var(--muted);
    background: none;
    border: none;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: color 0.15s, border-color 0.15s;
    font-family: var(--mono);
  }
  .tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
  .tab-btn:hover:not(.active) { color: var(--text); }

  .tab-content { padding: 16px 20px; }

  /* persona cards */
  .persona-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }
  .persona-card {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
  }
  .persona-role {
    font-size: 11px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-bottom: 8px;
  }
  .persona-hook { font-size: 12px; color: var(--text); margin-bottom: 8px; line-height: 1.5; }
  .persona-cta  { font-size: 11px; color: var(--accent2); font-style: italic; }

  /* email block */
  .email-block {
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px 16px;
    font-size: 13px;
    color: var(--text);
    white-space: pre-wrap;
    line-height: 1.7;
  }

  /* competitive card */
  .comp-item { margin-bottom: 12px; }
  .comp-label { font-size: 11px; color: var(--accent); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; }
  .comp-text  { font-size: 12px; color: var(--text); line-height: 1.6; }

  /* trace */
  .trace-list { list-style: none; }
  .trace-list li {
    padding: 6px 0;
    font-size: 12px;
    color: var(--muted);
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }
  .trace-list li::before { content: '›'; color: var(--accent); flex-shrink: 0; }

  /* empty state */
  .empty-state { text-align: center; padding: 80px 20px; }
  .empty-state p { color: var(--muted); font-size: 13px; line-height: 1.7; }
  .empty-code {
    display: inline-block;
    background: var(--bg3);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 2px 8px;
    color: var(--accent);
    font-size: 12px;
    margin-top: 12px;
  }

  @media (max-width: 700px) {
    .main-grid { grid-template-columns: 1fr; }
    .persona-grid { grid-template-columns: 1fr; }
    .timeline-panel { position: static; }
  }
`;

/* Sub-components */
const STEP_LABELS: Record<string, string> = {
  planner: "Planner",
  retrieval: "Retrieval",
  enrichment: "Enrichment",
  critic: "Critic",
  gtm_strategy: "GTM Strategy",
};

function AgentTimeline({ steps, confidence }: { steps: AgentStep[]; confidence: number }) {
  return (
    <div className="timeline-panel">
      <div className="panel-title">Agent Timeline</div>
      {steps.length === 0 && (
        <div style={{ color: "var(--muted)", fontSize: 12, textAlign: "center", padding: "20px 0" }}>
          Waiting for query...
        </div>
      )}
      {steps.map((s, i) => (
        <div key={i} className="step-row">
          <div className={`step-dot dot-${s.status}`} />
          <div className="step-body">
            <div className="step-name">
              {STEP_LABELS[s.step] ?? s.step}
              {s.status === "retry" && <span className="step-retry-badge">RETRY</span>}
            </div>
            <div className="step-detail">{s.detail}</div>
          </div>
        </div>
      ))}
      {confidence > 0 && (
        <div className="confidence-block">
          <div className="conf-label">
            <span>Confidence</span>
            <span className="conf-val">{Math.round(confidence * 100)}%</span>
          </div>
          <div className="conf-track">
            <div className="conf-fill" style={{ width: `${confidence * 100}%` }} />
          </div>
        </div>
      )}
    </div>
  );
}

function IcpBadge({ score }: { score: number }) {
  const cls = score >= 0.7 ? "icp-high" : score >= 0.4 ? "icp-mid" : "icp-low";
  const label = score >= 0.7 ? "High ICP" : score >= 0.4 ? "Mid ICP" : "Low ICP";
  return <span className={`icp-badge ${cls}`}>{label} · {score.toFixed(2)}</span>;
}

function GtmCard({ idx, result }: { idx: number; result: GTMResult }) {
  const [tab, setTab] = useState<"email" | "personas" | "competitive">("email");

  const hook = result.gtm_strategy.hooks[idx];
  const email = result.gtm_strategy.email_snippets[idx];
  const personas = result.gtm_strategy.persona_targeting?.[idx];
  const comp = result.gtm_strategy.competitive_intelligence?.[idx];

  if (!hook) return null;

  return (
    <div className="gtm-card">
      <div className="gtm-card-header">
        <div className="gtm-company-name">{hook.company}</div>
        <div className="hook-text">{hook.hook}</div>
      </div>
      <div className="tab-bar">
        <button className={`tab-btn ${tab === "email" ? "active" : ""}`} onClick={() => setTab("email")}>Email</button>
        {personas && <button className={`tab-btn ${tab === "personas" ? "active" : ""}`} onClick={() => setTab("personas")}>Personas</button>}
        {comp && <button className={`tab-btn ${tab === "competitive" ? "active" : ""}`} onClick={() => setTab("competitive")}>Competitive</button>}
      </div>
      <div className="tab-content">
        {tab === "email" && (
          <div className="email-block">{email?.email ?? "No email generated."}</div>
        )}
        {tab === "personas" && personas && (
          <div className="persona-grid">
            {Object.values(personas.personas).map((p, i) => (
              <div key={i} className="persona-card">
                <div className="persona-role">{p.persona}</div>
                <div className="persona-hook">{p.hook}</div>
                <div className="persona-cta">{p.cta}</div>
              </div>
            ))}
          </div>
        )}
        {tab === "competitive" && comp && (
          <div>
            <div className="comp-item">
              <div className="comp-label">Likely Stack</div>
              <div className="comp-text">{comp.competitive.likely_stack}</div>
            </div>
            <div className="comp-item">
              <div className="comp-label">Positioning</div>
              <div className="comp-text">{comp.competitive.positioning_strategy}</div>
            </div>
            <div className="comp-item">
              <div className="comp-label">Our Differentiation</div>
              <div className="comp-text">{comp.competitive.differentiation}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ─── Main App ──────────────────────────────────────────── */
const EXAMPLES = [
  "Find high-growth AI SaaS companies in the US",
  "Identify fintech startups hiring aggressively",
  "Find companies likely to churn their current GTM tools",
  "Enterprise health tech companies scaling in Europe",
];

export default function App() {
  const [query, setQuery] = useState("");
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [result, setResult] = useState<GTMResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [confidence, setConfidence] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);

  // inject styles once
  useEffect(() => {
    const style = document.createElement("style");
    style.textContent = STYLES;
    document.head.appendChild(style);
    return () => { document.head.removeChild(style); };
  }, []);

  const runQuery = () => {
    if (!query.trim() || loading) return;
    setSteps([]);
    setResult(null);
    setConfidence(0);
    setLoading(true);

    const ws = new WebSocket("ws://127.0.0.1:8000/ws/run");
    wsRef.current = ws;

    ws.onopen = () => ws.send(JSON.stringify({ query }));

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === "agent_update") {
        setSteps((prev) => {
          // Update existing step if same step+status, else append
          const existing = prev.findIndex((s) => s.step === msg.step && s.status === "running");
          const entry: AgentStep = {
            step: msg.step,
            status: msg.status,
            detail: msg.detail,
            data: msg.data,
            ts: Date.now(),
          };
          if (existing !== -1 && msg.status !== "running") {
            const next = [...prev];
            next[existing] = entry;
            return next;
          }
          return [...prev, entry];
        });
      }

      if (msg.type === "result") {
        setResult(msg.data);
        setConfidence(msg.data.confidence ?? 0);
        setLoading(false);
        ws.close();
      }

      if (msg.type === "error" || msg.type === "fatal") {
        setSteps((prev) => [
          ...prev,
          { step: "system", status: "error", detail: msg.message, ts: Date.now() },
        ]);
        setLoading(false);
        ws.close();
      }
    };

    ws.onerror = () => {
      setSteps((prev) => [
        ...prev,
        { step: "system", status: "error", detail: "WebSocket connection failed — is the backend running?", ts: Date.now() },
      ]);
      setLoading(false);
    };
  };

  const handleKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") runQuery();
  };

  const showPanel = loading || result || steps.length > 0;

  return (
    <div className="app">
      {/* Header */}
      <div className="header">
        <h1>GTM <span>Intelligence</span></h1>
        <p>Multi-agent outbound intelligence engine · Plan → Retrieve → Enrich → Validate → Target</p>
      </div>

      {/* Input */}
      <div className="input-row">
        <input
          className="query-input"
          placeholder="Describe your target market..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKey}
        />
        <button className="run-btn" onClick={runQuery} disabled={loading || !query.trim()}>
          {loading ? "Running..." : "Run →"}
        </button>
      </div>

      {/* Example chips */}
      <div className="examples">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="ex-chip" onClick={() => setQuery(ex)}>
            {ex}
          </button>
        ))}
      </div>

      {/* Main layout */}
      {showPanel ? (
        <div className="main-grid">
          {/* Timeline */}
          <AgentTimeline steps={steps} confidence={confidence} />

          {/* Results */}
          <div className="results-area">
            {result ? (
              <>
                {/* Companies */}
                <div className="section-heading">Companies</div>
                {result.results.map((c, i) => (
                  <div key={i} className={`company-card ${c.icp_score >= 0.7 ? "high" : ""}`}>
                    <div className="card-header">
                      <div className="company-name">{c.company}</div>
                      <IcpBadge score={c.icp_score} />
                    </div>
                    <div className="card-meta">
                      <div className="meta-item">Industry <span>{c.industry}</span></div>
                      <div className="meta-item">Region <span>{c.region}</span></div>
                      <div className="meta-item">Employees <span>{c.employees?.toLocaleString()}</span></div>
                      <div className="meta-item">Funding <span>{c.funding}</span></div>
                      <div className="meta-item">Confidence <span>{Math.round((c.confidence ?? 0) * 100)}%</span></div>
                    </div>
                    <div className="signals-row">
                      {c.signals?.map((s) => (
                        <span key={s} className="signal-chip">{s.replace(/_/g, " ")}</span>
                      ))}
                    </div>
                    <div className="insight-text">↳ {c.insight}</div>
                    <div className="insight-text" style={{ fontSize: "11px", marginTop: "4px", opacity: 0.8 }}>
                       Why this result: {c.why_this_result}
                  </div>

                
                  </div>
                ))}

                {/* GTM Strategy */}
                {result.gtm_strategy.hooks.length > 0 && (
                  <>
                    <div className="section-heading">GTM Strategy</div>
                    {result.gtm_strategy.hooks.map((_, i) => (
                      <GtmCard key={i} idx={i} result={result} />
                    ))}
                  </>
                )}

                {/* Reasoning trace */}
                {result.reasoning_trace.length > 0 && (
                  <>
                    <div className="section-heading">Reasoning Trace</div>
                    <ul className="trace-list">
                      {result.reasoning_trace.map((t, i) => (
                        <li key={i}>{t}</li>
                      ))}
                    </ul>
                  </>
                )}

                {/* Errors */}
                {result.errors.length > 0 && (
                  <>
                    <div className="section-heading">Errors</div>
                    {result.errors.map((e, i) => (
                      <div key={i} style={{ color: "var(--danger)", fontSize: 12, padding: "4px 0" }}>⚠ {e}</div>
                    ))}
                  </>
                )}
              </>
            ) : (
              <div style={{ padding: "40px 0" }}>
                {steps.map((s, i) => (
                  <div key={i} style={{ color: "var(--muted)", fontSize: 12, padding: "4px 0" }}>
                    <span style={{ color: s.status === "error" ? "var(--danger)" : "var(--accent)" }}>
                      {s.status === "running" ? "⟳" : s.status === "done" ? "✓" : s.status === "retry" ? "↺" : "✗"}
                    </span>{" "}
                    {s.step} — {s.detail}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="empty-state">
          <p>Enter a natural language query about your target market above.<br />The agent pipeline will plan, retrieve, enrich, validate, and generate personalized outreach.</p>
          <div className="empty-code">ws://localhost:8000/ws/run</div>
        </div>
      )}
    </div>
  );
}