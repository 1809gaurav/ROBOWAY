export function buildDrawModel(state, viewportWidth, viewportHeight) {
  const grid = state?.grid;
  const width = Number(grid?.width) || 0;
  const height = Number(grid?.height) || 0;
  const padding = 16;
  const cellSize = width > 0 && height > 0
    ? Math.max(0, Math.min((viewportWidth - padding * 2) / width, (viewportHeight - padding * 2) / height))
    : 0;
  const left = (viewportWidth - cellSize * width) / 2;
  const top = (viewportHeight - cellSize * height) / 2;
  const robots = (Array.isArray(state?.robots) ? state.robots : []).map((robot) => ({
    id: robot.id,
    gridX: Number(robot.x) || 0,
    gridY: Number(robot.y) || 0,
    x: left + (Number(robot.x) + 0.5) * cellSize,
    y: top + (Number(robot.y) + 0.5) * cellSize,
    robot,
  }));
  return { width, height, cellSize, left, top, robots };
}

export function pointOf(value) {
  if (Array.isArray(value)) return { x: Number(value[0]), y: Number(value[1]) };
  if (value && typeof value === "object") {
    const position = value.position ?? value.cell ?? value;
    return { x: Number(position.x), y: Number(position.y) };
  }
  return { x: Number.NaN, y: Number.NaN };
}

export function cellsOf(values) {
  if (!Array.isArray(values)) return [];
  return values.map((value) => ({ ...pointOf(value), source: value }))
    .filter(({ x, y }) => Number.isFinite(x) && Number.isFinite(y));
}
