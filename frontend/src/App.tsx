import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import {
  Activity, ArrowRight, ArrowUpRight, Battery, Boxes, ChevronDown, CircleHelp,
  Clock3, Command, Compass, Factory, Gauge, LayoutDashboard, Map, Menu, Pause,
  Play, RotateCcw, Settings2, ShieldCheck, Sparkles, Truck, WifiOff, X, Zap,
} from "lucide-react";
import { Warehouse2D, Warehouse3D } from "./Warehouse";
import type { Robot } from "./Warehouse";
import MonitorPage from "./monitor/MonitorPage.jsx";
import MonitorShareModal from "./monitor/MonitorShareModal.jsx";
import { API_BASE } from "./engine/config";
import { useEngineState } from "./engine/useEngineState";
import { toViewModel } from "./engine/adapter";
import type { State as ContractState } from "./engine/types";
import PredictionsCard from "./engine/PredictionsCard";

type Page = "Home" | "About" | "Product" | "Simulator" | "Manage" | "Profile";
type Job = { id: string; pickup_id: string; drop_id: string; state: string; owner: string | null; delivered_by?: string | null };
type SimulationState = {
  running: boolean;
  tick: number;
  collisionsAvoided: number;
  completedJobs: number;
  width: number;
  height: number;
  blocked: { x: number; y: number }[];
  robots: Robot[];
  jobs: Job[];
};

const initialState: SimulationState = {
  running: false, tick: 0, collisionsAvoided: 0, completedJobs: 0,
  width: 18, height: 12, blocked: [], robots: [], jobs: [],
};
const pages: Page[] = ["Home", "About", "Product", "Simulator", "Manage", "Profile"];

function App() {
  if (window.location.pathname === "/monitor") return <MonitorPage />;
  return <MainApp />;
}

function MainApp() {
  const [page, setPage] = useState<Page>("Home");
  const engine = useEngineState();
  const state = engine.state ? toViewModel(engine.state as ContractState) as unknown as SimulationState : initialState;
  const connected = engine.connected;
  const [view, setView] = useState<"3d" | "2d">("3d");
  const [menuOpen, setMenuOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [monitorShareOpen, setMonitorShareOpen] = useState(false);
  const action = async (name: "start" | "pause" | "reset" | "step") => {
    if (name === "start") await engine.start();
    if (name === "pause") await engine.pause();
    if (name === "step") await engine.step();
    if (name === "reset" && engine.state) await engine.loadScenario(engine.state.scenario_id);
  };

  const goTo = (destination: Page) => {
    setPage(destination);
    setMenuOpen(false);
  };
  const robots = state.robots;

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menuOpen ? "sidebar-open" : ""}`}>
        <div className="brand" onClick={() => goTo("Home")} role="button" tabIndex={0}>
          <div className="brand-mark"><Command size={19} strokeWidth={2.5} /></div>
          <span>robo<span className="brand-light">way</span></span>
          <span className="brand-version">BETA</span>
        </div>
        <div className="workspace-picker">
          <div className="workspace-icon"><Factory size={17} /></div>
          <div><strong>Northstar Logistics</strong><small>Workspace</small></div>
          <ChevronDown size={15} className="muted" />
        </div>
        <div className="nav-caption">WORKSPACE</div>
        <nav className="side-nav">
          {pages.map((item) => {
            const Icon = ({ Home: LayoutDashboard, About: Sparkles, Product: Boxes, Simulator: Activity, Manage: Settings2, Profile: Gauge } as const)[item];
            return (
              <button key={item} className={`nav-item ${page === item ? "active" : ""}`} onClick={() => goTo(item)}>
                <Icon size={17} /><span>{item === "Manage" ? "Fleet manage" : item}</span>
                {item === "Simulator" && state.running && <i className="nav-live-dot" />}
              </button>
            );
          })}
        </nav>
        <div className="side-spacer" />
        <div className="sidebar-bottom">
          <div className="plan-card">
            <div className="plan-icon"><Zap size={15} /></div>
            <div><strong>Operations are smooth</strong><span>3 of 10 robots online</span></div>
            <ArrowUpRight size={14} />
          </div>
          <button className="help-link"><CircleHelp size={16} /> Help center <ArrowRight size={14} /></button>
          <button className="user-card" onClick={() => goTo("Profile")}>
            <div className="avatar">KB</div><div><strong>Kanishka B.</strong><small>Fleet administrator</small></div><ChevronDown size={14} />
          </button>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <button className="mobile-menu icon-button" onClick={() => setMenuOpen(!menuOpen)} aria-label="Open navigation">
            {menuOpen ? <X size={19} /> : <Menu size={19} />}
          </button>
          <div className="breadcrumbs"><span>Northstar Logistics</span><span className="crumb-slash">/</span><strong>{page}</strong></div>
          <div className="topbar-actions">
            <div className={`connection ${connected ? "online" : "offline"}`}><span className="connection-dot" />{connected ? "Live connection" : "Connecting"}</div>
            <button className="icon-button notification-button" aria-label="Activity"><Activity size={17} /><i /></button>
            <button className="top-profile" onClick={() => setProfileOpen(!profileOpen)} aria-label="Profile menu"><div className="avatar small">KB</div><ChevronDown size={14} /></button>
            {profileOpen && <div className="profile-popover"><strong>Kanishka Butolia</strong><span>Administrator</span><button onClick={() => { goTo("Profile"); setProfileOpen(false); }}>View profile <ArrowRight size={13} /></button></div>}
          </div>
        </header>

        {!connected && <div className="error-banner"><WifiOff size={16} /><span>Backend offline — reconnecting to the engine.</span></div>}
        {engine.toast && <div className="error-banner"><WifiOff size={16} /><span>{engine.toast}</span><button onClick={engine.clearToast}>Dismiss</button></div>}
        {page === "Home" && <HomePage goTo={goTo} state={state} connected={connected} />}
        {page === "Simulator" && <SimulatorPage state={state} action={action} view={view} setView={setView} connected={connected} engine={engine} onShowMonitor={() => setMonitorShareOpen(true)} />}
        {page === "About" && <AboutPage goTo={goTo} />}
        {page === "Product" && <ProductPage goTo={goTo} />}
        {page === "Manage" && <ManagePage robots={robots} />}
        {page === "Profile" && <ProfilePage />}
      </main>
      {monitorShareOpen && <MonitorShareModal apiBase={API_BASE} onClose={() => setMonitorShareOpen(false)} />}
    </div>
  );
}

function HomePage({ goTo, state, connected }: { goTo: (page: Page) => void; state: SimulationState; connected: boolean }) {
  return (
    <div className="page-content home-page">
      <div className="hero-grid">
        <section className="hero-copy">
          <div className="eyebrow"><span className="eyebrow-line" />THE NEXT MOVE IN WAREHOUSING</div>
          <h1>Make every<br />move <em>count.</em></h1>
          <p>One intelligent layer for your entire warehouse. Orchestrate every robot, route, and order — in real time.</p>
          <div className="hero-actions">
            <button className="primary-button" onClick={() => goTo("Simulator")}>Open simulator <ArrowRight size={16} /></button>
            <button className="text-button" onClick={() => goTo("Product")}>Explore platform <ArrowUpRight size={16} /></button>
          </div>
          <div className="hero-proof"><div className="proof-avatars"><span>AR</span><span>MK</span><span>JL</span><span>+</span></div><span>Built for the people moving things forward.</span></div>
        </section>
        <div className="hero-visual">
          <div className="visual-glow" />
          <div className="warehouse-illustration">
            <div className="illus-label label-top"><span className="live-pulse" /> LIVE FLEET <b>03</b></div>
            <div className="illus-grid">
              {Array.from({ length: 60 }, (_, i) => <div key={i} className={`illus-cell ${[7, 8, 9, 10, 11, 12, 22, 23, 24, 25, 26, 27, 38, 39, 40, 41, 42, 43].includes(i) ? "shelf" : ""}`} />)}
              <div className="illus-bot bot-a">↗</div><div className="illus-bot bot-b">↙</div><div className="illus-bot bot-c">↗</div>
              <div className="illus-route route-a" /><div className="illus-route route-b" />
            </div>
            <div className="illus-label label-bottom"><Map size={13} /> NORTHSTAR · ZONE A <span>● ALL SYSTEMS NOMINAL</span></div>
          </div>
          <div className="floating-stat stat-efficiency"><div className="stat-icon green"><ArrowUpRight size={15} /></div><div><strong>+28.4%</strong><span>Throughput</span></div><div className="sparkline">▂▃▂▅▄▆▅█</div></div>
          <div className="floating-stat stat-time"><span className="time-icon"><Clock3 size={15} /></span><div><strong>1,204</strong><span>moves this hour</span></div></div>
          <div className="hero-orbit orbit-one" /><div className="hero-orbit orbit-two" />
        </div>
      </div>

      <section className="home-status">
        <div className="section-heading"><div><div className="eyebrow">YOUR WAREHOUSE, AT A GLANCE</div><h2>Everything in motion.</h2></div><button className="text-button compact" onClick={() => goTo("Simulator")}>View live simulator <ArrowRight size={15} /></button></div>
        <div className="metric-grid">
          <MetricCard label="Active robots" value={`${state.robots.length || 3}`} suffix="/ 10" trend="+2 this week" icon={<Truck size={17} />} trendUp />
          <MetricCard label="Orders in motion" value={`${Math.max(3, state.jobs.length)}`} suffix="" trend="Across 4 zones" icon={<Boxes size={17} />} />
          <MetricCard label="Avg. pick time" value="00:42" suffix="" trend="−12% vs. last week" icon={<Clock3 size={17} />} trendUp />
          <MetricCard label="System health" value={connected ? "99.9" : "—"} suffix={connected ? "%" : ""} trend={connected ? "All systems nominal" : "Waiting for API"} icon={<ShieldCheck size={17} />} />
        </div>
      </section>
      <footer className="footer-line"><span>© 2025 RoboWay Systems</span><span>Intelligence in every aisle.</span><span className="footer-status"><i /> {connected ? "All systems operational" : "Backend not connected"}</span></footer>
    </div>
  );
}

function MetricCard({ label, value, suffix, trend, icon, trendUp = false }: { label: string; value: string; suffix: string; trend: string; icon: ReactNode; trendUp?: boolean }) {
  return <article className="metric-card"><div className="metric-top"><span>{label}</span><div className="metric-icon">{icon}</div></div><div className="metric-value">{value}<small>{suffix}</small></div><div className={`metric-trend ${trendUp ? "trend-up" : ""}`}>{trendUp ? <ArrowUpRight size={13} /> : <span className="trend-dot" />}{trend}</div></article>;
}

function SimulatorPage({ state, action, view, setView, connected, engine, onShowMonitor }: { state: SimulationState; action: (name: "start" | "pause" | "reset" | "step") => Promise<void>; view: "3d" | "2d"; setView: (view: "3d" | "2d") => void; connected: boolean; engine: ReturnType<typeof useEngineState>; onShowMonitor: () => void }) {
  const robotCount = state.robots.length;
  const [scenarios, setScenarios] = useState<Array<{id:string;name:string}>>([]);
  const [scenarioId, setScenarioId] = useState(engine.state?.scenario_id ?? "narrow_passage");
  const [pickupId, setPickupId] = useState("");
  const [dropId, setDropId] = useState("");
  const [failRobotId, setFailRobotId] = useState("");
  const [blockMode, setBlockMode] = useState(false);
  const [heatmap, setHeatmap] = useState(false);
  useEffect(() => {
    fetch(`${API_BASE}/api/scenarios`).then((response) => response.json()).then((payload) => setScenarios(payload.scenarios ?? [])).catch(() => setScenarios([]));
  }, []);
  useEffect(() => {
    if (engine.state) setScenarioId(engine.state.scenario_id);
  }, [engine.state?.scenario_id]);
  return (
    <div className="page-content simulator-page">
      <div className="sim-header"><div><div className="eyebrow"><span className="eyebrow-line" />SIMULATION CONTROL</div><h1>Warehouse <em>simulator.</em></h1><p>Watch your fleet think, route, and move — all in real time.</p></div><div className="sim-header-actions"><button className="secondary-button" onClick={onShowMonitor}>Monitor on phone</button><button className="secondary-button" onClick={() => void action("reset")}><RotateCcw size={15} /> Reset</button><button className="primary-button" onClick={() => void action(state.running ? "pause" : "start")}>{state.running ? <Pause size={15} /> : <Play size={15} fill="currentColor" />}{state.running ? "Pause simulation" : "Run simulation"}</button></div></div>
      <div className="sim-header-actions" style={{ flexWrap: "wrap", marginBottom: 12 }}>
        <select aria-label="Scenario" value={scenarioId} onChange={(event) => setScenarioId(event.target.value)}>{scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}</select>
        <button className="secondary-button" onClick={() => void engine.loadScenario(scenarioId)}>Load scenario</button>
        <select aria-label="Speed" value={engine.state?.speed ?? 1} onChange={(event) => void engine.setSpeed(Number(event.target.value))}><option value="0.5">0.5x</option><option value="1">1x</option><option value="2">2x</option><option value="4">4x</option></select>
        <select aria-label="Pickup" value={pickupId} onChange={(event) => setPickupId(event.target.value)}><option value="">Pickup</option>{engine.state?.grid.pickups.map((pickup) => <option key={pickup.id} value={pickup.id}>{pickup.id}</option>)}</select>
        <select aria-label="Drop" value={dropId} onChange={(event) => setDropId(event.target.value)}><option value="">Drop</option>{engine.state?.grid.drops.map((drop) => <option key={drop.id} value={drop.id}>{drop.id}</option>)}</select>
        <button className="secondary-button" disabled={!pickupId || !dropId} onClick={() => void engine.addJob(pickupId, dropId)}>Add job</button>
        <select aria-label="Robot" value={failRobotId} onChange={(event) => setFailRobotId(event.target.value)}><option value="">Robot</option>{engine.state?.robots.map((robot) => <option key={robot.id} value={robot.id}>{robot.id}</option>)}</select>
        <button className="secondary-button" disabled={!failRobotId} onClick={() => void engine.failRobot(failRobotId)}>Fail robot</button>
        <button className={blockMode ? "primary-button" : "secondary-button"} onClick={() => setBlockMode((value) => !value)}>{blockMode ? "Blocking: click a cell" : "Block mode"}</button>
        <button className={heatmap ? "primary-button" : "secondary-button"} onClick={() => setHeatmap((value) => !value)}>Heatmap</button>
      </div>
      <div className="sim-stat-strip">
        <div className="sim-stat"><span className="stat-dot green-dot" /><span>SIMULATION</span><strong>{state.running ? "RUNNING" : "PAUSED"}</strong></div>
        <div className="sim-stat"><span className="stat-icon-mini"><Activity size={14} /></span><span>SIM TICK</span><strong className="mono">{String(state.tick).padStart(5, "0")}</strong></div>
        <div className="sim-stat"><span className="stat-icon-mini"><ShieldCheck size={14} /></span><span>CONFLICTS AVOIDED</span><strong className="mono">{state.collisionsAvoided}</strong></div>
        <div className="sim-stat"><span className={`connection-dot ${connected ? "" : "disconnected"}`} /><span>ENGINE</span><strong>{connected ? "CONNECTED" : "OFFLINE"}</strong></div>
      </div>
      <div className="sim-layout">
        <section className="sim-map-panel">
          <div className="panel-heading"><div><h2>Northstar distribution center</h2><span>Zone A · 18 × 12 grid · {robotCount} active units</span></div><div className="map-actions"><div className="view-switch"><button className={view === "3d" ? "selected" : ""} onClick={() => setView("3d")}>3D view</button><button className={view === "2d" ? "selected" : ""} onClick={() => setView("2d")}>2D grid</button></div><button className="icon-button" aria-label="Map settings"><Settings2 size={16} /></button></div></div>
          <div className="map-viewport">
            {robotCount ? view === "3d" ? <Warehouse3D state={{ ...state, ...({ obstacles: engine.state?.grid.obstacles.map(([x, y]) => ({ x, y })) ?? [], pickups: engine.state?.grid.pickups ?? [], drops: engine.state?.grid.drops ?? [], heatmap: engine.state?.metrics.congestion.heatmap as Array<[number, number, number?]> ?? [] }) }} heatmap={heatmap} blockMode={blockMode} onBlockCell={(x, y) => { const blocked = state.blocked.some((cell) => cell.x === x && cell.y === y); void (blocked ? engine.unblockCell(x, y) : engine.blockCell(x, y)); }} /> : <Warehouse2D state={{ ...state, ...({ obstacles: engine.state?.grid.obstacles.map(([x, y]) => ({ x, y })) ?? [], pickups: engine.state?.grid.pickups ?? [], drops: engine.state?.grid.drops ?? [] }) }} blockMode={blockMode} onBlockCell={(x, y) => { const blocked = state.blocked.some((cell) => cell.x === x && cell.y === y); void (blocked ? engine.unblockCell(x, y) : engine.blockCell(x, y)); }} /> : <div className="map-loading">Waiting for the simulation engine…</div>}
            <div className="map-legend"><span><i className="legend-robot" /> Robots</span><span><i className="legend-rack" /> Storage racks</span><span><i className="legend-route" /> Planned route</span></div>
            <div className="map-coordinate">NORTHSTAR DC <span>·</span> ZONE A</div>
          </div>
          <div className="map-controls"><div className="map-status"><span className="live-pulse" /> {state.running ? "LIVE SIMULATION" : "SIMULATION PAUSED"} <span className="separator">/</span> SPACE-TIME A*</div><button onClick={() => void action("step")} className="step-button">Step forward <ArrowRight size={14} /></button></div>
        </section>
        <aside className="sim-right">
          {engine.state && <section className="panel-card"><div className="panel-title"><h3>Metrics</h3></div><div className="job-list">
            <div className="job-row"><strong>Completed / total</strong><span>{engine.state.metrics.completed_jobs} / {engine.state.metrics.total_jobs}</span></div>
            <div className="job-row"><strong>Total wait ticks</strong><span>{engine.state.metrics.total_wait_ticks}</span></div>
            <div className="job-row"><strong>Conflicts prevented</strong><span>{engine.state.metrics.conflicts_prevented}</span></div>
            <div className="job-row"><strong>Planner rejections</strong><span>{engine.state.metrics.planner_rejections}</span></div>
            <div className="job-row"><strong>Deadlocks resolved</strong><span>{engine.state.metrics.deadlocks_resolved}</span></div>
            <div className="job-row"><strong>Reassignments</strong><span>{engine.state.metrics.reassignments}</span></div>
            <div className="job-row"><strong>Invariant violations</strong><span style={{ color: engine.state.metrics.invariant_violations === 0 ? "#22c55e" : "#ef4444" }}>{engine.state.metrics.invariant_violations}</span></div>
          </div></section>}
          <PredictionsCard />
          <section className="panel-card fleet-panel"><div className="panel-title"><div><h3>Robot fleet</h3><span>{robotCount} units active</span></div><button className="link-button">View all <ArrowRight size={13} /></button></div>
            <div className="fleet-list">{state.robots.map((robot) => <article className="fleet-row" key={robot.id}>            <div className="robot-avatar" style={{ "--robot-color": robot.color } as CSSProperties}><Truck size={17} /></div><div className="robot-details"><strong>{robot.name}<small>{robot.id.toUpperCase()}</small></strong><div className="robot-meta"><span><span className="tiny-green" /> {robot.status}</span><span>↗ {robot.target.x}, {robot.target.y}</span></div></div><div className="battery"><span>Wait {robot.waitTicks}</span></div></article>)}</div>
          </section>
          <section className="panel-card jobs-panel"><div className="panel-title"><div><h3>Active missions</h3><span>Latest assignments</span></div><button className="link-button">Queue <ArrowRight size={13} /></button></div>
            <div className="job-list">{state.jobs.map((job, index) => <div className="job-row" key={job.id}><span className={`job-number ${index === 0 ? "job-active" : ""}`}>{String(index + 1).padStart(2, "0")}</span><div className="job-info"><strong>{job.id}</strong><span>{job.pickup_id} <ArrowRight size={11} /> {job.drop_id}</span></div><span className={`job-status ${job.state === "PickedUp" ? "in-progress" : ""}`}>{job.state}</span></div>)}</div>
          </section>
          <section className="panel-card"><div className="panel-title"><h3>Event log</h3></div><div className="job-list">{[...engine.events].sort((a, b) => b.id - a.id).slice(0, 20).map((event) => <div className="job-row" key={event.id}><strong>[{event.tick}]</strong><span>{event.msg}</span></div>)}</div></section>
        </aside>
      </div>
      <footer className="footer-line"><span>RoboWay simulation engine · v1.0</span><span>Space-time A* · Conflict reservations</span><span className="footer-status"><i /> {connected ? "WebSocket live" : "Reconnecting"}</span></footer>
    </div>
  );
}

function AboutPage({ goTo }: { goTo: (page: Page) => void }) {
  return <div className="page-content info-page"><div className="eyebrow"><span className="eyebrow-line" />OUR NORTH STAR</div><h1>Work should move<br /><em>forward.</em></h1><p className="info-lead">Warehouses are the heartbeat of the modern world. RoboWay makes them more human, more thoughtful, and a lot more intelligent.</p><div className="info-feature-grid"><InfoCard icon={<Compass />} title="Built for the real world" text="Designed for the messy, moving, beautifully complex work that keeps the world running." /><InfoCard icon={<Activity />} title="Intelligence, in motion" text="We bring planning, live operations, and simulation into one clear view." /><InfoCard icon={<Sparkles />} title="Better by design" text="Technology should make work feel lighter — and the people behind it feel seen." /></div><button className="primary-button" onClick={() => goTo("Product")}>Meet the platform <ArrowRight size={15} /></button></div>;
}

function ProductPage({ goTo }: { goTo: (page: Page) => void }) {
  return <div className="page-content info-page"><div className="eyebrow"><span className="eyebrow-line" />THE ROBO WAY PLATFORM</div><h1>One brain.<br /><em>Every aisle.</em></h1><p className="info-lead">Plan, dispatch, and adapt your robotic fleet with an orchestration layer that understands your entire operation.</p><div className="product-list"><ProductRow number="01" icon={<Compass />} title="Intelligent routing" text="Space-time path planning keeps every robot moving without collisions or gridlock." /><ProductRow number="02" icon={<Zap />} title="Live orchestration" text="A central dispatcher balances work across robots, orders, and warehouse zones." /><ProductRow number="03" icon={<ShieldCheck />} title="Resilient operations" text="Detect conflicts early and recover from blocked paths without stopping the floor." /><ProductRow number="04" icon={<Map />} title="Warehouse digital twin" text="Explore the operation in interactive 3D, or switch instantly to a lightweight 2D grid." /></div><button className="primary-button" onClick={() => goTo("Simulator")}>Try the simulator <ArrowRight size={15} /></button></div>;
}

function InfoCard({ icon, title, text }: { icon: ReactNode; title: string; text: string }) {
  return <article className="info-card"><div className="info-icon">{icon}</div><h3>{title}</h3><p>{text}</p></article>;
}

function ProductRow({ number, icon, title, text }: { number: string; icon: ReactNode; title: string; text: string }) {
  return <article className="product-row"><span className="product-number">{number}</span><div className="info-icon">{icon}</div><div><h3>{title}</h3><p>{text}</p></div><ArrowUpRight size={16} className="muted" /></article>;
}

function ManagePage({ robots }: { robots: Robot[] }) {
  return <div className="page-content secondary-page"><div className="page-title-row"><div><div className="eyebrow"><span className="eyebrow-line" />FLEET OPERATIONS</div><h1>Fleet <em>manage.</em></h1><p>Every unit, every status, one clear view.</p></div><button className="secondary-button"><Settings2 size={15} /> Fleet settings</button></div><div className="manage-grid">{robots.map((robot) => <article className="manage-card" key={robot.id}><div className="manage-card-top"><div className="robot-avatar large" style={{ "--robot-color": robot.color } as CSSProperties}><Truck size={20} /></div><span className="status-pill"><i /> {robot.status}</span></div><h3>{robot.name}</h3><span className="robot-id">{robot.id.toUpperCase()} · AUTONOMOUS MOBILE ROBOT</span><div className="manage-divider" /><div className="manage-details"><span><Map size={14} /> Current position <b>{robot.x}, {robot.y}</b></span><span><Battery size={14} /> Battery <b>n/a</b></span><span><Boxes size={14} /> Wait ticks <b>{robot.waitTicks}</b></span></div><button className="manage-action">View robot details <ArrowRight size={14} /></button></article>)}</div><div className="empty-add-card"><div className="empty-add-icon"><Truck size={19} /></div><div><strong>Connect another robot</strong><span>Bring more of your fleet into RoboWay.</span></div><button className="secondary-button">Add robot <ArrowRight size={14} /></button></div></div>;
}

function ProfilePage() {
  return <div className="page-content secondary-page profile-page"><div className="eyebrow"><span className="eyebrow-line" />YOUR ACCOUNT</div><h1>Your <em>profile.</em></h1><p>Manage your personal details and preferences.</p><section className="profile-card"><div className="profile-banner" /><div className="profile-main"><div className="avatar profile-avatar">KB</div><div className="profile-identity"><h2>Kanishka Butolia</h2><span>Fleet administrator · Northstar Logistics</span></div><button className="secondary-button"><Settings2 size={14} /> Edit profile</button></div><div className="profile-fields"><div><span>EMAIL ADDRESS</span><strong>kanishka@northstar.example</strong></div><div><span>ROLE</span><strong>Administrator</strong></div><div><span>WORKSPACE</span><strong>Northstar Logistics</strong></div><div><span>MEMBER SINCE</span><strong>November 2024</strong></div></div></section><div className="profile-note"><ShieldCheck size={17} /><span><strong>Your account is secure.</strong> Two-factor authentication is enabled for your workspace.</span><ArrowRight size={14} /></div></div>;
}

export default App;
