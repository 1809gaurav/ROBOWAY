import { memo, useEffect, useMemo, useRef, useState } from "react";
import GridCanvas from "./GridCanvas.jsx";
import { Warehouse3D } from "../Warehouse";
import PredictionsCard from "../engine/PredictionsCard";
import { useEngineState } from "../engine/useEngineState";
import { statusColor } from "./statusColors.js";
import "./monitor.css";

function firstValue(...values) {
  return values.find((value) => value !== undefined && value !== null);
}

function metricValue(metrics, ...keys) {
  for (const key of keys) {
    const value = key.split(".").reduce((object, part) => object?.[part], metrics);
    if (value !== undefined && value !== null) return value;
  }
  return 0;
}

function coordinate(value) {
  if (Array.isArray(value)) return `(${value[0]}, ${value[1]})`;
  if (value && typeof value === "object") {
    const point = value.position ?? value.cell ?? value;
    return `(${point.x}, ${point.y})`;
  }
  return value ?? "—";
}

const RobotRows = memo(function RobotRows({ robots, onFollow }) {
  return <div className="monitor-list">
    {robots.length ? robots.map((robot) => <button type="button" className="monitor-list-row" key={robot.id} onClick={() => onFollow?.(robot.id)}>
      <span className="monitor-status-mark" style={{ "--status-color": statusColor(robot.status) }} aria-hidden="true" />
      <span className="monitor-row-primary"><strong>{robot.id}</strong><small>{robot.status ?? "unknown"}</small></span>
      <span className="monitor-row-secondary"><small>Job</small>{robot.job_id ?? robot.job ?? "—"}</span>
      <span className="monitor-row-secondary"><small>Carrying</small>{robot.carrying ?? "—"}</span>
      <span className="monitor-row-secondary"><small>Wait ticks</small>{robot.wait_ticks ?? 0}</span>
    </button>) : <p className="monitor-empty">No robots in this state.</p>}
  </div>;
});

const JobRows = memo(function JobRows({ jobs }) {
  return <div className="monitor-list">
    {jobs.length ? jobs.map((job) => <div className="monitor-job-row" key={job.id}>
      <strong>{job.id}</strong>
      <span>{coordinate(firstValue(job.pickup, job.from))} <span aria-label="to">→</span> {coordinate(firstValue(job.drop, job.to))}</span>
      <span className="monitor-state-chip">{job.state ?? job.status ?? "unknown"}</span>
      <span className="monitor-job-owner">{job.delivered_by ?? job.owner ?? job.robot ?? "—"}</span>
    </div>) : <p className="monitor-empty">No jobs in this state.</p>}
  </div>;
});

function eventColor(type) {
  const normalized = String(type ?? "").toUpperCase();
  if (normalized.startsWith("DEADLOCK_")) return "magenta";
  if (normalized === "ROBOT_FAILED" || normalized === "PACKAGE_STRANDED") return "red";
  if (normalized === "DELIVERED") return "green";
  if (normalized.includes("WAIT")) return "amber";
  if (normalized.startsWith("REPLAN") || normalized === "CELL_BLOCKED") return "blue";
  return "muted";
}

const EventRows = memo(function EventRows({ events }) {
  return <div className="monitor-events">
    {events.length ? events.map((event, index) => <article className={`monitor-event ${eventColor(event.type)}`} key={event.id ?? `${event.tick}-${event.type}-${index}`}>
      <span>[{event.tick ?? "—"}]</span><strong>{event.msg ?? event.message ?? event.type ?? "Event"}</strong>
    </article>) : <p className="monitor-empty">Waiting for events.</p>}
  </div>;
});

function LoadingSkeleton() {
  return <main className="monitor-page"><div className="monitor-skeleton" aria-label="Waiting for live simulation state" role="status">
    <span className="monitor-skeleton-line" /><span className="monitor-skeleton-line short" /><span className="monitor-skeleton-panel" /><span className="monitor-skeleton-line" />
  </div></main>;
}

export default function MonitorPage() {
  const { state: contractState, events, connected, lastUpdateMs } = useEngineState();
  const state = contractState;
  const [now, setNow] = useState(Date.now());
  const [showHeatmap, setShowHeatmap] = useState(false);
  const [pauseScroll, setPauseScroll] = useState(false);
  const [followedRobot, setFollowedRobot] = useState(null);
  const [viewMode, setViewMode] = useState(() => {
    if (window.innerWidth < 360) return "2d";
    try {
      const canvas = document.createElement("canvas");
      return canvas.getContext("webgl") || canvas.getContext("experimental-webgl") ? "3d" : "2d";
    } catch {
      return "2d";
    }
  });
  const eventContainer = useRef(null);
  const robots = useMemo(() => Array.isArray(state?.robots) ? state.robots : [], [state?.tick, state?.robots]);
  const jobs = useMemo(() => Array.isArray(state?.jobs) ? state.jobs : [], [state?.tick, state?.jobs]);
  const visibleEvents = useMemo(() => events.slice(-50).reverse(), [events]);
  const metrics = state?.metrics ?? {};

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!pauseScroll && eventContainer.current) eventContainer.current.scrollTop = 0;
  }, [visibleEvents.length, pauseScroll]);

  if (!state) return <LoadingSkeleton />;

  const silenceOrigin = lastUpdateMs;
  const silenceMs = silenceOrigin === null ? Infinity : now - silenceOrigin;
  const banner = connected
    ? silenceMs > 5000
      ? { className: "silent", text: "No updates for 5s" }
      : lastUpdateMs === null
        ? { className: "silent", text: "Waiting for first update..." }
        : { className: "live", text: "Live" }
    : { className: "offline", text: "Disconnected, retrying..." };
  const cycle = state.deadlock?.cycle ?? state.deadlock?.robots ?? [];
  const cycleText = cycle.map((robot) => typeof robot === "object" ? robot.id : robot).join(" → ");
  const failed = robots.find((robot) => String(robot.status).toLowerCase() === "failed");
  const failedJob = jobs.find((job) => [failed?.job_id, failed?.job, failed?.package_id].includes(job.id));
  const strandedPackage = failedJob?.package_id ?? failedJob?.id ?? failed?.package_id ?? failed?.job_id ?? failed?.job ?? "package";
  const scenarioName = typeof state.scenario === "object"
    ? state.scenario?.name ?? state.scenario?.id ?? "Scenario"
    : state.scenario?.name ?? state.scenario_name ?? state.scenario ?? "Scenario";

  return <main className="monitor-page">
    <header className="monitor-header">
      <div className="monitor-title-line">
        <div><h1>ROBOWAY Live</h1><p>{scenarioName} · Tick {state.tick ?? "—"}</p></div>
        <span className={`monitor-state-chip ${state.running ? "running" : "paused"}`}>{state.running ? "Running" : "Paused"}</span>
      </div>
      <div className={`monitor-connection ${banner.className}`} role="status" aria-live="polite">
        <span className="monitor-banner-symbol" aria-hidden="true">{banner.className === "live" ? "●" : banner.className === "silent" ? "◷" : "!"}</span>
        <span>{banner.text}</span>
      </div>
    </header>

    <div className="monitor-content">
      <div className="monitor-view-toolbar">
        <div className="view-switch"><button className={viewMode === "2d" ? "selected" : ""} onClick={() => setViewMode("2d")}>2D</button><button className={viewMode === "3d" ? "selected" : ""} onClick={() => setViewMode("3d")}>3D</button></div>
        <button className="monitor-chip" onClick={() => setShowHeatmap((visible) => !visible)} aria-pressed={showHeatmap}>Heatmap</button>
      </div>
      {followedRobot && <div className="monitor-follow-chip">Follow {followedRobot} · {robots.find((robot) => robot.id === followedRobot)?.status ?? "n/a"} · Job {robots.find((robot) => robot.id === followedRobot)?.job_id ?? "—"} · Carrying {robots.find((robot) => robot.id === followedRobot)?.carrying ?? "—"} · Wait {robots.find((robot) => robot.id === followedRobot)?.wait_ticks ?? 0}<button onClick={() => setFollowedRobot(null)}>Stop following</button></div>}
      {viewMode === "3d" ? <Warehouse3D
        readOnly
        heatmap={showHeatmap}
        followedRobot={followedRobot}
        onInteract={() => { if (followedRobot) setFollowedRobot(null); }}
        onRobotSelect={(robotId) => setFollowedRobot(robotId)}
        state={{
          width: state.grid?.width ?? 12,
          height: state.grid?.height ?? 7,
          blocked: (state.grid?.blocked ?? []).map(([x, y]) => ({ x, y })),
          obstacles: (state.grid?.obstacles ?? []).map(([x, y]) => ({ x, y })),
          pickups: state.grid?.pickups ?? [],
          drops: state.grid?.drops ?? [],
          tick: state.tick,
          speed: state.speed,
          heatmap: state.metrics?.congestion?.heatmap ?? [],
          deadlock: state.deadlock,
          robots: robots.map((robot) => ({ id: robot.id, name: robot.id, x: robot.pos[0], y: robot.pos[1], color: "#66d19e", status: robot.status, target: { x: robot.pos[0], y: robot.pos[1] }, path: (robot.path ?? []).map(([x, y]) => [x, y]), waitTicks: robot.wait_ticks, carrying: robot.carrying })),
        }}
      /> : <GridCanvas state={state} showHeatmap={showHeatmap} onToggleHeatmap={() => setShowHeatmap((visible) => !visible)} />}

      {(state.deadlock?.active || failed) && <section className={`monitor-alert-strip ${failed ? "failed" : "deadlock"}`} role="alert">
        {state.deadlock?.active && <p>Deadlock detected: {cycleText || "cycle unavailable"}</p>}
        {failed && <p>{failed.id} failed, package {strandedPackage} stranded</p>}
      </section>}

      <PredictionsCard />

      <section className="monitor-card">
        <h2>Metrics</h2>
        <div className="monitor-metrics-primary">
          <Metric label="Completed / total jobs" value={`${metricValue(metrics, "completed_jobs", "jobs.completed", "completedJobs")} / ${metricValue(metrics, "total_jobs", "jobs.total") || jobs.length}`} />
          <Metric label="Total wait ticks" value={metricValue(metrics, "total_wait_ticks", "wait_ticks.total", "totalWaitTicks")} />
          <Metric label="Conflicts prevented" value={metricValue(metrics, "conflicts_prevented", "conflicts_avoided", "conflictsPrevented")} />
          <Metric label="Planner rejections" value={metricValue(metrics, "planner_rejections", "plannerRejections")} />
        </div>
        <div className="monitor-metrics-secondary">
          <Metric label="Invariant violations" value={metricValue(metrics, "invariant_violations", "invariantViolations")} goodWhenZero />
          <Metric label="Deadlocks resolved" value={metricValue(metrics, "deadlocks_resolved", "deadlocksResolved")} />
          <Metric label="Reassignments" value={metricValue(metrics, "reassignments")} />
          <Metric label="Congestion index" value={metricValue(metrics, "congestion_index", "congestion.index")} />
        </div>
      </section>

      <section className="monitor-card">
        <h2>Robots</h2>
        <RobotRows robots={robots} onFollow={(robotId) => setFollowedRobot(robotId)} />
      </section>

      <section className="monitor-card">
        <h2>Jobs</h2>
        <JobRows jobs={jobs} />
      </section>

      <section className="monitor-card monitor-event-card">
        <div className="monitor-card-heading"><h2>Event log</h2><button className={`monitor-chip ${pauseScroll ? "is-selected" : ""}`} onClick={() => setPauseScroll((paused) => !paused)} aria-pressed={pauseScroll}>Pause scroll</button></div>
        <div className="monitor-event-scroll" ref={eventContainer}><EventRows events={visibleEvents} /></div>
      </section>
    </div>
    <footer className="monitor-footer">Read-only live view · Updates arrive over WebSocket</footer>
  </main>;
}

function Metric({ label, value, goodWhenZero = false }) {
  const isGood = goodWhenZero && Number(value) === 0;
  return <div className={`monitor-metric ${goodWhenZero ? (isGood ? "good" : "bad") : ""}`}><span>{label}</span><strong>{value}</strong></div>;
}
