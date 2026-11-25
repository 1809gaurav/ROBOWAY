import type { State } from "./types";

const palette = ["#66d19e", "#69a8ff", "#f2c66d", "#c89af5", "#ef7f78", "#55c7d9"];

export function toViewModel(state: State) {
  const robots = state.robots.map((robot, index) => {
    const job = state.jobs.find((item) => item.id === robot.job_id);
    const target = job
      ? (robot.carrying
          ? state.grid.drops.find((drop) => drop.id === job.drop_id)?.pos
          : state.grid.pickups.find((pickup) => pickup.id === job.pickup_id)?.pos)
      : robot.pos;
    return {
      ...robot,
      name: robot.id,
      x: robot.pos[0],
      y: robot.pos[1],
      color: palette[index % palette.length],
      target: target ? { x: target[0], y: target[1] } : { x: robot.pos[0], y: robot.pos[1] },
      path: robot.path.map(([x, y]) => [x, y]),
      waitTicks: robot.wait_ticks,
    };
  });
  return {
    tick: state.tick,
    running: state.status === "running",
    width: state.grid.width,
    height: state.grid.height,
    blocked: state.grid.blocked.map(([x, y]) => ({ x, y })),
    obstacles: state.grid.obstacles.map(([x, y]) => ({ x, y })),
    pickups: state.grid.pickups,
    drops: state.grid.drops,
    robots,
    jobs: state.jobs,
    completedJobs: state.metrics.completed_jobs,
    collisionsAvoided: state.metrics.conflicts_prevented,
    deadlock: state.deadlock,
    metrics: state.metrics,
    speed: state.speed,
    heatmap: state.metrics.congestion?.heatmap ?? [],
  };
}
