import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api/client";
import type { Architecture } from "../api/types";
import { Icon } from "../components/Icon";
import { ErrorState, Skeleton } from "../components/States";
import { useAsync } from "../lib/useAsync";

const KIND_COLOR: Record<string, string> = {
  planner: "var(--series-1)", tool: "var(--series-3)", deterministic: "var(--series-3)", rag: "var(--series-2)",
  rules: "var(--text-muted)", llm: "var(--series-1)", synthesis: "var(--series-1)",
};
const EDGE = "var(--border-strong)";
const LOOP = "var(--series-2)";
// Fixed layout for the 8-node copilot graph (left -> right).
const POS: Record<string, [number, number]> = {
  START: [40, 150], supervisor: [150, 150], data_agent: [300, 70], analysis_agent: [450, 70], research_agent: [450, 230],
  evidence_validator: [600, 150], responder: [740, 150], output_validator: [880, 150], finalize: [1020, 150], END: [1120, 150],
};

function AgentGraph({ arch }: { arch: Architecture }) {
  const label = (id: string) => arch.graph.nodes.find((n) => n.id === id)?.agent ?? id;
  return (
    <div className="graph" style={{ overflowX: "auto" }}>
      <svg viewBox="0 0 1160 300" role="img" aria-label="LangGraph workflow: supervisor, data, analysis, research, validation, responder, output validation, finalize">
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill={EDGE} />
          </marker>
        </defs>
        {arch.graph.edges.map(([a, b], i) => {
          const [x1, y1] = POS[a] ?? [0, 0];
          const [x2, y2] = POS[b] ?? [0, 0];
          const back = x2 < x1;
          const vertical = x1 === x2;
          const d = back ? `M${x1} ${y1 + 22} C ${x1} ${y1 + 90}, ${x2} ${y2 + 90}, ${x2} ${y2 + 22}`
            : vertical ? `M${x1} ${y1 + 21} L ${x2} ${y2 - 23}`
              : `M${x1 + 52} ${y1} L ${x2 - 56} ${y2}`;
          return <path key={i} d={d} fill="none" stroke={back ? LOOP : EDGE} strokeDasharray={back ? "4 4" : undefined} strokeWidth={1.5} markerEnd="url(#arrow)" />;
        })}
        {Object.entries(POS).map(([id, [x, y]]) => {
          const node = arch.graph.nodes.find((n) => n.id === id);
          const terminal = id === "START" || id === "END";
          return (
            <g key={id} transform={`translate(${x},${y})`}>
              <rect x={terminal ? -30 : -55} y={-20} width={terminal ? 60 : 110} height={40} rx={terminal ? 20 : 10}
                className="node" stroke={node ? KIND_COLOR[node.kind] : EDGE} strokeWidth={1.5} />
              <text textAnchor="middle" dy="-2" style={{ fontWeight: 600, fontSize: 11 }}>{terminal ? id : label(id).replace(" Agent", "")}</text>
              {!terminal && <text className="node-id" textAnchor="middle" dy="12">{id}</text>}
            </g>
          );
        })}
      </svg>
      <div className="legend"><span><i style={{ background: EDGE }} />forward edge</span><span><i style={{ background: LOOP }} />retry / correction loop</span></div>
    </div>
  );
}

const DOCS: [string, string][] = [
  ["readme", "README"], ["project-structure", "Project structure"], ["architecture", "Architecture"], ["adr-001", "ADR-001"],
  ["review", "Production review"], ["ui-guide", "UI guide"],
];
// FastAPI's built-in API docs, proxied on the UI origin by Vite (dev) and nginx (Docker).
const API_DOCS: [string, string][] = [["/docs", "Swagger UI"], ["/redoc", "ReDoc"], ["/openapi.json", "OpenAPI JSON"]];

/** Tabbed viewer for the whitelisted project documents served by /api/v1/docs. */
export function DocsViewer({ initial = "readme" }: { initial?: string }) {
  const [slug, setSlug] = useState(initial);
  const doc = useAsync(() => api.doc(slug), [slug]);
  return (
    <section className="card" aria-labelledby="docs-title">
      <div className="card-head" style={{ flexWrap: "wrap" }}>
        <div>
          <h3 className="card-title" id="docs-title">Project documentation</h3>
          <div className="doc-links" style={{ marginTop: 8 }}>
            {API_DOCS.map(([href, label]) => (
              <a key={href} className="pill-btn" href={href} target="_blank" rel="noreferrer noopener">
                <Icon name="code" size={14} />{label}<Icon name="external" size={12} />
              </a>
            ))}
          </div>
        </div>
        <div className="seg" role="tablist" aria-label="Documents" style={{ flexWrap: "wrap", borderRadius: 12 }}>
          {DOCS.map(([k, l]) => <button key={k} role="tab" aria-selected={slug === k} aria-pressed={slug === k} onClick={() => setSlug(k)}>{l}</button>)}
        </div>
      </div>
      {doc.error ? <ErrorState error={doc.error} onRetry={doc.reload} /> : !doc.data ? <Skeleton height={400} /> : (
        // react-markdown does not render raw HTML by default, so document content cannot inject markup.
        <div className="markdown">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{
            // Repo-relative screenshot paths (docs/images/x.png) are served by the API.
            img: ({ src, alt }) => {
              const name = typeof src === "string" ? /(?:^|\/)images\/([a-z0-9-]+\.png)$/.exec(src)?.[1] : undefined;
              return name ? <img src={`/api/v1/docs/images/${name}`} alt={alt ?? ""} loading="lazy" decoding="async" /> : null;
            },
            a: ({ href, children }) => <a href={href} target="_blank" rel="noreferrer noopener">{children}</a>,
          }}>{doc.data.markdown}</ReactMarkdown>
        </div>
      )}
    </section>
  );
}

export function HowItWorks() {
  const arch = useAsync(() => api.architecture());
  return (
    <>
      <section className="card" aria-labelledby="arch-title">
        <div className="card-head">
          <div><h3 className="card-title" id="arch-title">How the agent works</h3>
            <div className="card-sub">Live description from <code>/api/v1/copilot/architecture</code> · mode: {arch.data?.mode ?? "…"}{arch.data?.model ? ` (${arch.data.model})` : ""}</div></div>
        </div>
        {arch.error ? <ErrorState error={arch.error} onRetry={arch.reload} /> : !arch.data ? <Skeleton height={260} /> : (
          <>
            <AgentGraph arch={arch.data} />
            <div className="grid two" style={{ marginTop: 12 }}>
              <table className="data">
                <thead><tr><th>Agent / node</th><th>Responsibility</th></tr></thead>
                <tbody>{arch.data.graph.nodes.map((n) => <tr key={n.id}><td><b>{n.agent}</b><div className="note">{n.id} · {n.kind}</div></td><td>{n.does}</td></tr>)}</tbody>
              </table>
              <div>
                <table className="data">
                  <thead><tr><th>Deterministic tool</th><th>What it does</th></tr></thead>
                  <tbody>{Object.entries(arch.data.tools).map(([k, v]) => <tr key={k}><td><code>{k}</code></td><td>{v}</td></tr>)}</tbody>
                </table>
                <h4 style={{ margin: "14px 0 6px" }}>Approved knowledge base (RAG)</h4>
                <ul className="note" style={{ marginTop: 0 }}>{arch.data.documents.map((d) => <li key={d}>{d}</li>)}</ul>
              </div>
            </div>
          </>
        )}
      </section>
      <DocsViewer />
    </>
  );
}
