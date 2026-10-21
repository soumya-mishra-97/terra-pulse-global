import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ChatResponse, Health } from "../api/types";
import { SpecChart } from "./charts";
import { Icon } from "./Icon";

const SUGGESTED = [
  "Which countries are contributing most to population growth?",
  "Compare India and China population growth since 2015",
  "How is world population estimated and how uncertain is it?",
  "Tell me about ageing in Japan over the last 10 years",
  "Is the population counter a real-time count?",
];

type Turn = { role: "user"; text: string } | { role: "assistant"; res: ChatResponse } | { role: "error"; text: string };

/** Escape-free rendering: answer text is shown as plain text; citation labels are highlighted. */
function AnswerText({ text }: { text: string }) {
  const parts = text.split(/(\[(?:[FDS]\d+(?:,\s*)?)+\])/g);
  return (
    <div className="answer">
      {parts.map((p, i) => (/^\[[FDS]\d/.test(p) ? <sup key={i} style={{ fontSize: 10.5 }}>{p}</sup> : <span key={i}>{p}</span>))}
    </div>
  );
}

function ModeTag({ res }: { res: ChatResponse }) {
  const label = res.mode === "claude" ? `Claude · ${res.model}` : res.mode === "demo" ? "Demo mode · no LLM" : "Fallback · deterministic";
  return <span className={`tag pill-tag ${res.mode === "claude" ? "estimate" : "illustrative"}`}>{label}</span>;
}

function AssistantMessage({ res }: { res: ChatResponse }) {
  const passed = res.validation.output?.passed;
  return (
    <article className="msg" aria-label="Assistant answer">
      <div className="meta" style={{ marginTop: 0, marginBottom: 8 }}>
        <ModeTag res={res} />
        {!res.refused && (
          <span className={`tag pill-tag ${passed ? "fresh" : "stale"}`}>
            {passed ? "Validated" : "Validation warnings"}
          </span>
        )}
        {res.refused && <span className="tag pill-tag demo">Out of scope</span>}
      </div>
      <AnswerText text={res.answer} />
      {res.chart && <div className="mini-chart"><SpecChart spec={res.chart} height={170} /></div>}
      {res.citations.length > 0 && (
        <div className="cite" style={{ marginTop: 8 }}>
          <b>Sources</b>
          <ul style={{ margin: "4px 0 0", paddingLeft: 16 }}>
            {res.citations.map((c) => (
              <li key={c.label}>
                [{c.label}] {c.url ? <a href={c.url} target="_blank" rel="noreferrer noopener">{c.title}</a> : c.title}
                {c.published && <> · {c.kind === "dataset" ? "release" : "published"} {c.published}</>}
                {c.reference_date && <> · ref. {c.reference_date}</>}
              </li>
            ))}
          </ul>
        </div>
      )}
      {res.limitations.length > 0 && (
        <details style={{ marginTop: 6 }}>
          <summary className="cite" style={{ cursor: "pointer" }}>Limitations ({res.limitations.length})</summary>
          <ul className="cite" style={{ margin: "4px 0 0", paddingLeft: 16 }}>{res.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
        </details>
      )}
      <details style={{ marginTop: 6 }}>
        <summary className="cite" style={{ cursor: "pointer" }}>
          Agent trace · {res.trace.length} steps · {Math.round(res.latency_ms)} ms{res.plan ? ` · planner: ${res.plan.planner}` : ""}
        </summary>
        <ol className="trace">
          {res.trace.map((t, i) => (
            <li key={i}><span className={`dot ${t.status}`} aria-label={t.status} /><b>{t.agent}</b>
              <span style={{ color: "var(--text-muted)" }}>{t.detail}</span></li>
          ))}
        </ol>
      </details>
    </article>
  );
}

export function CopilotPanel({ health, onClose }: { health: Health | null; onClose: () => void }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => { bodyRef.current?.scrollTo({ top: bodyRef.current.scrollHeight, behavior: "smooth" }); }, [turns, busy]);
  useEffect(() => () => abortRef.current?.abort(), []);
  // Deep link: /?ask=<question> pre-runs a question (shareable example queries).
  useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("ask");
    if (q) void ask(q.slice(0, 1000));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function ask(q: string) {
    const question = q.trim();
    if (question.length < 3 || busy) return;
    setInput("");
    setTurns((t) => [...t, { role: "user", text: question }]);
    setBusy(true);
    abortRef.current = new AbortController();
    try {
      const res = await api.chat(question, abortRef.current.signal);
      setTurns((t) => [...t, { role: "assistant", res }]);
    } catch (e) {
      setTurns((t) => [...t, { role: "error", text: e instanceof ApiError || e instanceof Error ? e.message : "Request failed" }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="copilot" aria-label="Pulse AI copilot">
      <div className="copilot-head">
        <span className="avatar" style={{ width: 30, height: 30 }}><Icon name="sparkle" size={16} /></span>
        <h2>Pulse AI</h2>
        <span className="tag pill-tag estimate">
          {health?.llm_mode === "claude" ? `Claude · ${health.llm_model}` : "Demo mode"}
        </span>
        <span style={{ flex: 1 }} />
        <button className="icon-btn" onClick={() => setTurns([])} aria-label="New conversation"><Icon name="plus" size={16} /></button>
        <button className="icon-btn" onClick={onClose} aria-label="Hide copilot"><Icon name="close" size={16} /></button>
      </div>
      <div className="copilot-body" ref={bodyRef} aria-live="polite">
        {turns.length === 0 && (
          <>
            <div className="msg">
              <b className="accent-text">Multi-agent demographic copilot</b>
              <p style={{ margin: "6px 0 0", color: "var(--text-secondary)", fontSize: 13 }}>
                A Supervisor plans the task, then Data, Analysis, Research (RAG) and Validation agents gather evidence.
                Every number comes from the dataset and deterministic Python — the AI only explains it.
              </p>
            </div>
            {health?.llm_mode !== "claude" && (
              <div className="msg warn">
                <b>Demo mode</b>
                <p style={{ margin: "6px 0 0", color: "var(--text-secondary)", fontSize: 13 }}>
                  No ANTHROPIC_API_KEY is configured on the server, so answers are deterministic templates built from
                  the same validated facts. Add a key to <code>.env</code> to enable Claude explanations.
                </p>
              </div>
            )}
          </>
        )}
        {turns.map((t, i) =>
          t.role === "user" ? <div key={i} className="msg user">{t.text}</div>
            : t.role === "assistant" ? <AssistantMessage key={i} res={t.res} />
              : <div key={i} className="msg error" role="alert">{t.text}</div>)}
        {busy && (
          <div className="msg" role="status">
            <div className="cite">Agents working: planning → data → analysis → research → validation…</div>
            <div className="skeleton" style={{ height: 10, marginTop: 8 }} />
          </div>
        )}
        <p className="disclaimer">Assistant can make mistakes. Figures are dated estimates — check the cited sources.</p>
        <div>
          <div className="card-sub" style={{ marginBottom: 6 }}>Suggested prompts</div>
          <div className="chips">
            {SUGGESTED.map((s) => <button key={s} className="chip-btn" onClick={() => ask(s)} disabled={busy}>{s}</button>)}
          </div>
        </div>
      </div>
      <form className="composer" onSubmit={(e) => { e.preventDefault(); void ask(input); }}>
        <label htmlFor="copilot-input" className="sr-only">Ask a question</label>
        <textarea id="copilot-input" rows={1} maxLength={1000} placeholder="Ask about population trends…" value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void ask(input); } }} />
        <button className="icon-btn primary" type="submit" disabled={busy || input.trim().length < 3} aria-label="Send">
          <Icon name="send" size={16} />
        </button>
      </form>
    </aside>
  );
}
