const STATUS_VARIABLES = {
  moving: "--monitor-moving",
  waiting: "--monitor-waiting",
  picking: "--monitor-working",
  dropping: "--monitor-working",
  yielding: "--monitor-yielding",
  failed: "--monitor-failed",
  idle: "--monitor-idle",
};

const FALLBACK_COLORS = {
  moving: "#27b36a",
  waiting: "#e9a23b",
  picking: "#4285e8",
  dropping: "#4285e8",
  yielding: "#22b8c7",
  failed: "#e24a4a",
  idle: "#858b92",
};

export function statusColor(status) {
  const normalized = String(status ?? "idle").toLowerCase();
  const variable = STATUS_VARIABLES[normalized] ?? STATUS_VARIABLES.idle;
  const page = document.querySelector(".monitor-page") ?? document.documentElement;
  return getComputedStyle(page).getPropertyValue(variable).trim() || FALLBACK_COLORS[normalized] || FALLBACK_COLORS.idle;
}
