import { useCallback, useEffect, useRef, useState } from "react";
import { buildDrawModel, cellsOf } from "./drawModel.js";
import { statusColor } from "./statusColors.js";

function heatmapLookup(heatmap) {
  if (Array.isArray(heatmap) && heatmap.some((row) => Array.isArray(row))) {
    return (x, y) => Number(heatmap[y]?.[x]) || 0;
  }
  if (Array.isArray(heatmap)) {
    const values = new Map(heatmap.map((cell) => [
      `${Number(cell?.x)},${Number(cell?.y)}`,
      Number(cell?.value ?? cell?.intensity ?? cell?.count) || 0,
    ]));
    return (x, y) => values.get(`${x},${y}`) ?? 0;
  }
  if (heatmap && typeof heatmap === "object") {
    return (x, y) => Number(heatmap[`${x},${y}`] ?? heatmap[y]?.[x]) || 0;
  }
  return () => 0;
}

function drawCellLabels(context, items, prefix, model) {
  cellsOf(items).forEach(({ x, y }, index) => {
    const cellX = model.left + x * model.cellSize;
    const cellY = model.top + y * model.cellSize;
    const label = model.cellSize >= 18 ? `${prefix}${index + 1}` : String(index + 1);
    const palette = getComputedStyle(document.querySelector(".monitor-page") ?? document.documentElement);
    context.fillStyle = palette.getPropertyValue(prefix === "P" ? "--monitor-pickup" : "--monitor-drop").trim();
    context.font = `600 ${Math.max(9, Math.min(model.cellSize * 0.34, 13))}px sans-serif`;
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(label, cellX + model.cellSize / 2, cellY + model.cellSize / 2);
  });
}

function drawState(context, model, state, showHeatmap, view, time) {
  const { width, height, cellSize, left, top } = model;
  if (!width || !height || !cellSize) return;
  const grid = state.grid;
  const palette = getComputedStyle(document.querySelector(".monitor-page") ?? document.documentElement);
  const color = (name, fallback) => palette.getPropertyValue(name).trim() || fallback;
  context.fillStyle = color("--monitor-canvas", "#18201b");
  context.fillRect(left, top, width * cellSize, height * cellSize);

  const obstacles = cellsOf(grid.obstacles ?? grid.blocked ?? []);
  obstacles.forEach(({ x, y }) => {
    context.fillStyle = color("--monitor-obstacle", "#41494d");
    context.fillRect(left + x * cellSize + 1, top + y * cellSize + 1, cellSize - 2, cellSize - 2);
  });

  const userBlocked = cellsOf(grid.user_blocked ?? grid.userBlocked ?? grid.user_blocked_cells ?? []);
  userBlocked.forEach(({ x, y }) => {
    const x0 = left + x * cellSize;
    const y0 = top + y * cellSize;
    context.fillStyle = color("--monitor-blocked-fill", "rgba(204, 54, 60, 0.22)");
    context.fillRect(x0 + 1, y0 + 1, cellSize - 2, cellSize - 2);
    context.strokeStyle = color("--monitor-blocked", "#e34d55");
    context.lineWidth = Math.max(1.5, cellSize * 0.08);
    context.beginPath();
    context.moveTo(x0 + cellSize * 0.25, y0 + cellSize * 0.25);
    context.lineTo(x0 + cellSize * 0.75, y0 + cellSize * 0.75);
    context.moveTo(x0 + cellSize * 0.75, y0 + cellSize * 0.25);
    context.lineTo(x0 + cellSize * 0.25, y0 + cellSize * 0.75);
    context.stroke();
  });

  if (showHeatmap) {
    const heatmap = state.metrics?.congestion?.heatmap ?? [];
    const getHeatValue = heatmapLookup(heatmap);
    let maximum = 0;
    for (let y = 0; y < height; y += 1) {
      for (let x = 0; x < width; x += 1) maximum = Math.max(maximum, getHeatValue(x, y));
    }
    if (maximum > 0) {
      for (let y = 0; y < height; y += 1) {
        for (let x = 0; x < width; x += 1) {
          const value = getHeatValue(x, y);
          if (value <= 0) continue;
          context.fillStyle = `rgba(255, 125, 34, ${Math.min(0.7, 0.12 + value / maximum * 0.58)})`;
          context.fillRect(left + x * cellSize, top + y * cellSize, cellSize, cellSize);
        }
      }
    }
  }

  context.strokeStyle = color("--monitor-grid-line", "rgba(130, 148, 137, 0.28)");
  context.lineWidth = 1;
  for (let x = 0; x <= width; x += 1) {
    context.beginPath();
    context.moveTo(left + x * cellSize, top);
    context.lineTo(left + x * cellSize, top + height * cellSize);
    context.stroke();
  }
  for (let y = 0; y <= height; y += 1) {
    context.beginPath();
    context.moveTo(left, top + y * cellSize);
    context.lineTo(left + width * cellSize, top + y * cellSize);
    context.stroke();
  }

  drawCellLabels(context, grid.pickups, "P", model);
  drawCellLabels(context, grid.drops, "D", model);

  model.robots.forEach(({ robot }) => {
    const robotColor = robot.color ?? statusColor(robot.status);
    const path = Array.isArray(robot.path) ? robot.path.slice(Number(robot.progress) || 0, (Number(robot.progress) || 0) + 6) : [];
    if (path.length > 0) {
      context.beginPath();
      context.moveTo(left + (Number(robot.x) + 0.5) * cellSize, top + (Number(robot.y) + 0.5) * cellSize);
      path.forEach((point) => {
        const x = Array.isArray(point) ? Number(point[0]) : Number(point?.x);
        const y = Array.isArray(point) ? Number(point[1]) : Number(point?.y);
        if (Number.isFinite(x) && Number.isFinite(y)) context.lineTo(left + (x + 0.5) * cellSize, top + (y + 0.5) * cellSize);
      });
      context.globalAlpha = 0.45;
      context.strokeStyle = robotColor;
      context.lineWidth = Math.max(1.5, cellSize * 0.09);
      context.setLineDash([Math.max(2, cellSize * 0.18), Math.max(2, cellSize * 0.16)]);
      context.stroke();
      context.setLineDash([]);
      context.globalAlpha = 1;
    }
  });

  const deadlock = state.deadlock;
  const cycleIds = Array.isArray(deadlock?.cycle)
    ? deadlock.cycle.map((item) => typeof item === "object" ? item.id : item)
    : [];
  model.robots.forEach(({ id, x, y, robot }) => {
    const radius = Math.max(5, cellSize * 0.34);
    const color = statusColor(robot.status);
    context.beginPath();
    context.arc(x, y, radius, 0, Math.PI * 2);
    context.fillStyle = color;
    context.fill();
    context.strokeStyle = "rgba(0, 0, 0, 0.55)";
    context.lineWidth = Math.max(1, cellSize * 0.06);
    context.stroke();

    if (String(robot.status).toLowerCase() === "failed") {
      context.strokeStyle = "#fff";
      context.lineWidth = Math.max(2, cellSize * 0.09);
      context.beginPath();
      context.moveTo(x - radius * 0.45, y - radius * 0.45);
      context.lineTo(x + radius * 0.45, y + radius * 0.45);
      context.moveTo(x + radius * 0.45, y - radius * 0.45);
      context.lineTo(x - radius * 0.45, y + radius * 0.45);
      context.stroke();
    } else {
      context.fillStyle = "#fff";
      context.font = `700 ${Math.max(8, Math.min(cellSize * 0.3, 12))}px sans-serif`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillText(String(id), x, y);
    }

    if (robot.carrying !== null && robot.carrying !== undefined) {
      const badgeSize = Math.max(5, cellSize * 0.18);
      context.fillStyle = "#f4d45e";
      context.fillRect(x + radius * 0.55, y - radius - badgeSize * 0.35, badgeSize, badgeSize);
      context.strokeStyle = "#18201b";
      context.lineWidth = 1;
      context.strokeRect(x + radius * 0.55, y - radius - badgeSize * 0.35, badgeSize, badgeSize);
    }

    if (deadlock?.active && cycleIds.includes(id)) {
      const phase = (Math.sin(time / 220) + 1) / 2;
      context.beginPath();
      context.arc(x, y, radius + 3 + phase * Math.max(2, cellSize * 0.1), 0, Math.PI * 2);
      context.strokeStyle = `rgba(226, 65, 217, ${0.5 + phase * 0.5})`;
      context.lineWidth = Math.max(2, cellSize * 0.09);
      context.stroke();
    }
  });
}

export default function GridCanvas({ state, showHeatmap, onToggleHeatmap }) {
  const canvasRef = useRef(null);
  const canvasWrapRef = useRef(null);
  const drawRef = useRef(() => {});
  const activePointers = useRef(new Map());
  const gesture = useRef({ dragged: false, lastX: 0, lastY: 0, startX: 0, startY: 0, pinchDistance: 0 });
  const [viewport, setViewport] = useState({ width: 0, height: 0 });
  const [view, setView] = useState({ zoom: 1, panX: 0, panY: 0 });
  const [selectedRobot, setSelectedRobot] = useState(null);
  const grid = state?.grid;

  useEffect(() => {
    const container = canvasWrapRef.current;
    if (!container) return undefined;
    const updateSize = () => {
      const bounds = container.getBoundingClientRect();
      setViewport({ width: bounds.width, height: bounds.height });
    };
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    window.addEventListener("orientationchange", updateSize);
    updateSize();
    return () => {
      observer.disconnect();
      window.removeEventListener("orientationchange", updateSize);
    };
  }, []);

  const draw = useCallback((time) => {
    const canvas = canvasRef.current;
    if (!canvas || !viewport.width || !viewport.height || !grid) return;
    const ratio = window.devicePixelRatio || 1;
    const pixelWidth = Math.round(viewport.width * ratio);
    const pixelHeight = Math.round(viewport.height * ratio);
    if (canvas.width !== pixelWidth || canvas.height !== pixelHeight) {
      canvas.width = pixelWidth;
      canvas.height = pixelHeight;
    }
    const context = canvas.getContext("2d");
    if (!context) return;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    context.clearRect(0, 0, viewport.width, viewport.height);
    const model = buildDrawModel(state, viewport.width, viewport.height);
    context.save();
    context.translate(viewport.width / 2 + view.panX, viewport.height / 2 + view.panY);
    context.scale(view.zoom, view.zoom);
    context.translate(-viewport.width / 2, -viewport.height / 2);
    drawState(context, model, state, showHeatmap, view, time);
    context.restore();
  }, [grid, showHeatmap, state, view, viewport]);

  useEffect(() => {
    drawRef.current = draw;
  }, [draw]);

  useEffect(() => {
    let frame;
    const render = (time) => {
      drawRef.current(time);
      if (state?.deadlock?.active) frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);
    return () => cancelAnimationFrame(frame);
  }, [state, showHeatmap, view, viewport]);

  const zoomAt = (factor, x, y) => {
    setView((current) => {
      const zoom = Math.max(0.6, Math.min(5, current.zoom * factor));
      const ratio = zoom / current.zoom;
      return {
        zoom,
        panX: x - (x - current.panX) * ratio,
        panY: y - (y - current.panY) * ratio,
      };
    });
  };

  const onPointerDown = (event) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    activePointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    gesture.current = { ...gesture.current, dragged: false, lastX: event.clientX, lastY: event.clientY, startX: event.clientX, startY: event.clientY };
    if (activePointers.current.size === 2) {
      const points = [...activePointers.current.values()];
      gesture.current.pinchDistance = Math.hypot(points[0].x - points[1].x, points[0].y - points[1].y);
    }
  };

  const onPointerMove = (event) => {
    if (!activePointers.current.has(event.pointerId)) return;
    activePointers.current.set(event.pointerId, { x: event.clientX, y: event.clientY });
    const pointers = [...activePointers.current.values()];
    if (pointers.length >= 2) {
      const distance = Math.hypot(pointers[0].x - pointers[1].x, pointers[0].y - pointers[1].y);
      if (gesture.current.pinchDistance > 0) {
        const bounds = event.currentTarget.getBoundingClientRect();
        zoomAt(distance / gesture.current.pinchDistance, (pointers[0].x + pointers[1].x) / 2 - bounds.left, (pointers[0].y + pointers[1].y) / 2 - bounds.top);
      }
      gesture.current.pinchDistance = distance;
      gesture.current.dragged = true;
      return;
    }
    const deltaX = event.clientX - gesture.current.lastX;
    const deltaY = event.clientY - gesture.current.lastY;
    if (Math.hypot(event.clientX - gesture.current.startX, event.clientY - gesture.current.startY) > 5) gesture.current.dragged = true;
    if (gesture.current.dragged) setView((current) => ({ ...current, panX: current.panX + deltaX, panY: current.panY + deltaY }));
    gesture.current.lastX = event.clientX;
    gesture.current.lastY = event.clientY;
  };

  const onPointerUp = (event) => {
    activePointers.current.delete(event.pointerId);
    if (!gesture.current.dragged && activePointers.current.size === 0) {
      const bounds = event.currentTarget.getBoundingClientRect();
      const screenX = event.clientX - bounds.left;
      const screenY = event.clientY - bounds.top;
      const x = (screenX - viewport.width / 2 - view.panX) / view.zoom + viewport.width / 2;
      const y = (screenY - viewport.height / 2 - view.panY) / view.zoom + viewport.height / 2;
      const model = buildDrawModel(state, viewport.width, viewport.height);
      const hit = model.robots.find((robot) => Math.hypot(x - robot.x, y - robot.y) < Math.max(12, model.cellSize * 0.48));
      if (hit) setSelectedRobot(hit.robot);
    }
    if (activePointers.current.size < 2) gesture.current.pinchDistance = 0;
  };

  const onWheel = (event) => {
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    zoomAt(event.deltaY < 0 ? 1.12 : 1 / 1.12, event.clientX - bounds.left, event.clientY - bounds.top);
  };

  const closeDetails = () => setSelectedRobot(null);
  const robotPath = Array.isArray(selectedRobot?.path)
    ? selectedRobot.path.slice(Number(selectedRobot.progress) || 0, (Number(selectedRobot.progress) || 0) + 5)
    : [];

  return (
    <section className="monitor-card monitor-grid-card" aria-label="Warehouse grid">
      <div className="monitor-card-heading">
        <div><h2>Live grid</h2><span>{grid?.width ?? "—"} × {grid?.height ?? "—"} cells</span></div>
        <button className={`monitor-chip ${showHeatmap ? "is-selected" : ""}`} onClick={onToggleHeatmap} aria-pressed={showHeatmap}>Heatmap</button>
      </div>
      <div className="monitor-canvas-wrap" ref={canvasWrapRef}>
        {grid?.width && grid?.height
          ? <canvas
            ref={canvasRef}
            className="monitor-canvas"
            aria-label={`Live warehouse grid, ${grid.width} columns by ${grid.height} rows. Tap a robot for details.`}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerCancel={onPointerUp}
            onWheel={onWheel}
          />
          : <p className="monitor-empty-grid">The connected state does not include grid dimensions.</p>}
      </div>
      <div className="monitor-grid-controls"><span>Drag to pan · pinch or scroll to zoom</span><button className="monitor-button" onClick={() => setView({ zoom: 1, panX: 0, panY: 0 })}>Reset view</button></div>
      {selectedRobot && <div className="monitor-sheet-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) closeDetails(); }}>
        <section className="monitor-robot-sheet" role="dialog" aria-modal="true" aria-labelledby="robot-detail-title">
          <button className="monitor-sheet-close" onClick={closeDetails} aria-label="Close robot details">×</button>
          <h2 id="robot-detail-title">{selectedRobot.id}</h2>
          <dl>
            <dt>Status</dt><dd>{selectedRobot.status ?? "unknown"}</dd>
            <dt>Job</dt><dd>{selectedRobot.job_id ?? selectedRobot.job ?? "—"}</dd>
            <dt>Carrying</dt><dd>{selectedRobot.carrying ?? "Nothing"}</dd>
            <dt>Wait ticks</dt><dd>{selectedRobot.wait_ticks ?? 0}</dd>
            <dt>Next 5 path cells</dt><dd>{robotPath.length ? robotPath.map((point) => Array.isArray(point) ? `(${point[0]}, ${point[1]})` : `(${point.x}, ${point.y})`).join(" → ") : "No planned path"}</dd>
          </dl>
        </section>
      </div>}
    </section>
  );
}
