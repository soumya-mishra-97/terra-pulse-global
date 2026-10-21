import { lazy, Suspense, useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, currentUser } from "./api/client";
import type { Health } from "./api/types";
import { Icon, Logo } from "./components/Icon";
import { Skeleton } from "./components/States";
import { useTheme } from "./lib/theme";

// Route-level code splitting: the shell paints first, each page (and the chart/markdown libraries it needs) loads on demand.
const Overview = lazy(() => import("./pages/Overview").then((m) => ({ default: m.Overview })));
const Countries = lazy(() => import("./pages/Countries").then((m) => ({ default: m.Countries })));
const Reports = lazy(() => import("./pages/Reports").then((m) => ({ default: m.Reports })));
const AiDocs = lazy(() => import("./pages/HowItWorks").then((m) => ({ default: m.HowItWorks })));
const DocPage = lazy(() => import("./pages/HowItWorks").then((m) => ({ default: m.DocsViewer })));
const CopilotPanel = lazy(() => import("./components/CopilotPanel").then((m) => ({ default: m.CopilotPanel })));

const NAV: [string, string][] = [
  ["/", "Overview"], ["/countries", "Countries"], ["/reports", "Country Reports"], ["/ai-docs", "AI Docs"],
  ["/project-structure", "Project Structure"],
];

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [copilot, setCopilot] = useState(true);
  const [search, setSearch] = useState("");
  const [theme, toggleTheme] = useTheme();
  const location = useLocation();
  const navigate = useNavigate();
  const title = NAV.find(([p]) => p === location.pathname)?.[1] ?? "Overview";
  useEffect(() => { api.health().then(setHealth).catch(() => setHealth(null)); }, []);
  useEffect(() => { document.title = `${title} · TerraPulse Global AI`; }, [title]);
  const user = currentUser();

  return (
    <div className={`shell ${copilot ? "" : "copilot-hidden"}`}>
      <div className="main">
        <header className="topbar">
          <NavLink to="/" className="logo" aria-label="TerraPulse Global AI home">
            <Logo /><span><span className="cap">T</span>erra<span className="cap">P</span>ulse</span><small>Global AI</small>
          </NavLink>
          <nav className="crumbs" aria-label="Breadcrumb">
            <button className="icon-btn" onClick={() => navigate(-1)} aria-label="Back"><Icon name="back" size={16} /></button>
            <span>{title}</span>
          </nav>
          <span className="spacer" />
          {!copilot && <button className="pill-btn" onClick={() => setCopilot(true)}><Icon name="sparkle" size={15} />Pulse AI</button>}
          <span className={`tag status ${health?.status === "ok" ? "fresh" : "stale"}`}
            title={health ? `API ${health.version} · database ${health.database}` : "API unreachable"}>
            {health ? (health.status === "ok" ? "API online" : "API degraded") : "API offline"}
          </span>
          <button className="icon-btn" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}
            title={theme === "dark" ? "Light theme" : "Dark theme"}>
            <Icon name={theme === "dark" ? "sun" : "moon"} size={16} />
          </button>
          <div className="user">
            <span className="avatar" aria-hidden="true">{user.slice(0, 2).toUpperCase()}</span>
            <div><div style={{ fontWeight: 600 }}>{user}</div><small>Demo identity</small></div>
          </div>
        </header>
        <div className="subbar">
          <nav className="tabs" aria-label="Primary">
            {NAV.map(([p, l]) => <NavLink key={p} to={p} end={p === "/"} className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>{l}</NavLink>)}
            <a className="tab" href="/docs" target="_blank" rel="noreferrer noopener">Swagger API<Icon name="external" size={13} /></a>
          </nav>
          <span style={{ flex: 1 }} />
          <label className="search">
            <Icon name="search" size={16} />
            <span className="sr-only">Search countries</span>
            <input placeholder="Search countries" value={search}
              onChange={(e) => { setSearch(e.target.value); if (location.pathname !== "/countries") navigate("/countries"); }} />
          </label>
        </div>
        <main className="content" id="main">
          <Suspense fallback={<Skeleton height={420} />}>
            <Routes>
              <Route path="/" element={<Overview />} />
              <Route path="/countries" element={<Countries search={search} />} />
              <Route path="/reports" element={<Reports />} />
              <Route path="/ai-docs" element={<AiDocs />} />
              <Route path="/project-structure" element={<DocPage initial="project-structure" />} />
              <Route path="/how-it-works" element={<Navigate to="/ai-docs" replace />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </div>
      {copilot && <Suspense fallback={null}><CopilotPanel health={health} onClose={() => setCopilot(false)} /></Suspense>}
    </div>
  );
}
