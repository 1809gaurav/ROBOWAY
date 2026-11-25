import { describe, expect, it } from "vitest";
import sampleState from "./mock_state.json";
import { buildDrawModel } from "./drawModel.js";

describe("buildDrawModel", () => {
  it.each([
    [12, 7, 368 / 12],
    [16, 10, 23],
    [40, 30, 268 / 30],
  ])("fits a %sx%s grid and positions each robot", (width, height, expectedCellSize) => {
    const state = {
      ...sampleState,
      grid: { ...sampleState.grid, width, height },
    };
    const model = buildDrawModel(state, 400, 300);
    expect(model.width).toBe(width);
    expect(model.height).toBe(height);
    expect(model.cellSize).toBeCloseTo(expectedCellSize);
    expect(model.robots).toHaveLength(1);
    expect(model.robots[0]).toMatchObject({
      id: "R1",
      gridX: 2,
      gridY: 3,
      x: model.left + 2.5 * model.cellSize,
      y: model.top + 3.5 * model.cellSize,
    });
  });

  it("uses changed grid dimensions from a new state without a reload", () => {
    const first = buildDrawModel(sampleState, 400, 300);
    const nextState = {
      ...sampleState,
      tick: sampleState.tick + 1,
      grid: { ...sampleState.grid, width: 40, height: 30 },
      robots: [{ ...sampleState.robots[0], x: 20, y: 12 }],
    };
    const next = buildDrawModel(nextState, 400, 300);
    expect(first).toMatchObject({ width: 12, height: 7 });
    expect(next).toMatchObject({ width: 40, height: 30 });
    expect(next.robots[0].x).not.toBe(first.robots[0].x);
    expect(next.cellSize).not.toBe(first.cellSize);
  });
});
