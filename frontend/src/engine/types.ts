export type Position = [number, number];

export interface Grid {
  width: number;
  height: number;
  obstacles: Position[];
  blocked: Position[];
  pickups: Array<{ id: string; pos: Position }>;
  drops: Array<{ id: string; pos: Position }>;
}

export interface Robot {
  id: string;
  pos: Position;
  status: "idle" | "moving" | "waiting" | "picking" | "dropping" | "yielding" | "failed";
  carrying: string | null;
  job_id: string | null;
  path: Array<[number, number, number]>;
  wait_ticks: number;
}

export interface Job {
  id: string;
  pickup_id: string;
  drop_id: string;
  state: "Waiting" | "Assigned" | "PickedUp" | "Stranded" | "Delivered" | "Blocked";
  owner: string | null;
  delivered_by?: string | null;
  created_tick: number;
  assigned_tick: number | null;
  picked_tick: number | null;
  delivered_tick: number | null;
  history: string[];
}

export interface Metrics {
  completed_jobs: number;
  total_jobs: number;
  total_wait_ticks: number;
  avg_wait_ticks_per_job: number | null;
  congestion: { index: number; heatmap: Position[] };
  planner_rejections: number;
  conflicts_prevented: number;
  invariant_violations: number;
  deadlocks_resolved: number;
  reassignments: number;
}

export interface EventEntry {
  id: number;
  tick: number;
  type: string;
  robot: string | null;
  job: string | null;
  msg: string;
  data: Record<string, unknown>;
}

export interface State {
  tick: number;
  status: "running" | "paused";
  speed: number;
  scenario_id: string;
  grid: Grid;
  robots: Robot[];
  jobs: Job[];
  reservations_count: number;
  deadlock: { active: boolean; cycle: string[] };
  metrics: Metrics;
  events_tail: EventEntry[];
}
