import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, Line, OrbitControls } from "@react-three/drei";
import { useEffect, useRef, useState } from "react";
import type { MouseEvent as ReactMouseEvent } from "react";
import type { Group } from "three";
import * as THREE from "three";

export type Robot = {
  id: string;
  name: string;
  x: number;
  y: number;
  color: string;
  status: string;
  target: { x: number; y: number };
  path: number[][];
  waitTicks: number;
  carrying: string | null;
};

type Point = { x: number; y: number };
type WarehouseState = {
  width: number;
  height: number;
  blocked: Point[];
  obstacles: Point[];
  pickups: Array<{ id: string; pos: [number, number] }>;
  drops: Array<{ id: string; pos: [number, number] }>;
  robots: Robot[];
  tick: number;
  speed?: number;
  deadlock?: { active: boolean; cycle: string[] };
  heatmap?: Array<{ x: number; y: number; count?: number } | [number, number, number?]>;
};

export const toWorld = (x: number, y: number, width: number, height: number, cell = 0.72): [number, number, number] =>
  [(x - (width - 1) / 2) * cell, 0.06, ((height - 1) / 2 - y) * cell];

function statusColor(status: string) {
  if (status === "failed") return "#ef4444";
  if (status === "waiting") return "#f59e0b";
  if (status === "yielding") return "#22d3ee";
  if (status === "picking" || status === "dropping") return "#3b82f6";
  return "#22c55e";
}

function RobotModel({ robot, width, height, speed = 1, onSelect }: { robot: Robot; width: number; height: number; speed?: number; onSelect?: (id: string) => void }) {
  const group = useRef<Group>(null);
  const previous = useRef<[number, number]>([robot.x, robot.y]);
  const [display, setDisplay] = useState<[number, number]>([robot.x, robot.y]);
  useEffect(() => {
    const distance = Math.max(Math.abs(previous.current[0] - robot.x), Math.abs(previous.current[1] - robot.y));
    if (distance > 2) {
      setDisplay([robot.x, robot.y]);
      previous.current = [robot.x, robot.y];
    } else {
      previous.current = [robot.x, robot.y];
    }
  }, [robot.x, robot.y]);
  useThree(() => {});
  useEffect(() => {
    let frame = 0;
    const start = display;
    const end: [number, number] = [robot.x, robot.y];
    const duration = 0.5 / speed;
    const started = performance.now();
    const animate = () => {
      const alpha = Math.min((performance.now() - started) / (duration * 1000), 1);
      setDisplay([start[0] + (end[0] - start[0]) * alpha, start[1] + (end[1] - start[1]) * alpha]);
      if (alpha < 1) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate);
    return () => cancelAnimationFrame(frame);
  }, [robot.x, robot.y, speed]);
  const point = toWorld(display[0], display[1], width, height);
  return (
    <group ref={group} position={point} onClick={(event) => { event.stopPropagation(); onSelect?.(robot.id); }}>
      <mesh position={[0, 0.22, 0]} castShadow={false}>
        <cylinderGeometry args={[0.22, 0.25, 0.2, 8]} />
        <meshStandardMaterial color={statusColor(robot.status)} />
      </mesh>
      {robot.carrying && <mesh position={[0, 0.48, 0]}><boxGeometry args={[0.16, 0.16, 0.16]} /><meshStandardMaterial color="#f4e9a3" /></mesh>}
      <Html position={[0, 0.62, 0]} center distanceFactor={12}><span className="three-robot-label">{robot.id}</span></Html>
    </group>
  );
}

function FollowCamera({ robot, width, height }: { robot: Robot | undefined; width: number; height: number }) {
  const { camera } = useThree();
  useFrame((_, delta) => {
    if (!robot) return;
    const target = toWorld(robot.x, robot.y, width, height);
    const desired = new THREE.Vector3(target[0] + 3.2, 4.2, target[2] + 3.2);
    const alpha = 1 - Math.exp(-delta * 4);
    camera.position.lerp(desired, alpha);
    camera.lookAt(target[0], 0.15, target[2]);
  });
  return null;
}

export function Scene({ state, blockMode = false, onBlockCell, onRobotSelect, readOnly = false, heatmap = false, followedRobot, onInteract }: { state: WarehouseState; blockMode?: boolean; onBlockCell?: (x: number, y: number) => void; onRobotSelect?: (id: string) => void; readOnly?: boolean; heatmap?: boolean; followedRobot?: string | null; onInteract?: () => void }) {
  const { camera } = useThree();
  const maxSize = Math.max(state.width, state.height);
  const cell = 0.72;
  const obstacleMesh = useRef<THREE.InstancedMesh>(null);
  const obstacleCount = state.obstacles.length;
  useEffect(() => {
    if (!obstacleMesh.current || obstacleCount <= 150) return;
    const dummy = new THREE.Object3D();
    state.obstacles.forEach((point, index) => {
      const [x, _y, z] = toWorld(point.x, point.y, state.width, state.height, cell);
      dummy.position.set(x, 0.36, z);
      dummy.updateMatrix();
      obstacleMesh.current!.setMatrixAt(index, dummy.matrix);
    });
    obstacleMesh.current.instanceMatrix.needsUpdate = true;
  }, [obstacleCount, state.width, state.height, state.obstacles]);
  useEffect(() => {
    return () => {
      obstacleMesh.current?.geometry.dispose();
      if (obstacleMesh.current?.material instanceof THREE.Material) obstacleMesh.current.material.dispose();
    };
  }, []);
  const cameraDistance = Math.max(8, maxSize * 0.9);
  useEffect(() => {
    camera.position.set(cameraDistance * 0.7, cameraDistance * 0.65, cameraDistance * 0.7);
    camera.updateProjectionMatrix();
  }, [camera, cameraDistance]);
  return (
    <>
      <color attach="background" args={["#111711"]} />
      <fog attach="fog" args={["#111711", maxSize * 0.55, maxSize * 1.35]} />
      <ambientLight intensity={1.25} />
      <directionalLight position={[cameraDistance * 0.5, cameraDistance, cameraDistance * 0.4]} intensity={2.2} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.07, 0]} onClick={(event) => {
        if (!blockMode || readOnly) return;
        const point = event.point;
        const x = Math.round(point.x / cell + (state.width - 1) / 2);
        const y = Math.round((state.height - 1) / 2 - point.z / cell);
        if (x >= 0 && x < state.width && y >= 0 && y < state.height) onBlockCell?.(x, y);
      }}>
        <planeGeometry args={[state.width * cell, state.height * cell]} />
        <meshStandardMaterial color="#1a211b" roughness={0.86} />
      </mesh>
      {Array.from({ length: state.width + 1 }, (_, x) => {
        const wx = toWorld(x - 0.5, 0, state.width, state.height, cell)[0];
        return <Line key={`gx-${x}`} points={[[wx, 0.005, -state.height * cell / 2], [wx, 0.005, state.height * cell / 2]]} color="#354036" transparent opacity={0.45} />;
      })}
      {Array.from({ length: state.height + 1 }, (_, y) => {
        const wz = toWorld(0, y - 0.5, state.width, state.height, cell)[2];
        return <Line key={`gy-${y}`} points={[[-state.width * cell / 2, 0.005, wz], [state.width * cell / 2, 0.005, wz]]} color="#354036" transparent opacity={0.45} />;
      })}
      {heatmap && state.heatmap?.map((point, index) => {
        const x = Array.isArray(point) ? point[0] : point.x;
        const y = Array.isArray(point) ? point[1] : point.y;
        const count = Array.isArray(point) ? (point[2] ?? 1) : (point.count ?? 1);
        return <mesh key={`heat-${x}-${y}-${index}`} position={toWorld(x, y, state.width, state.height, cell)} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[cell * 0.9, cell * 0.9]} /><meshBasicMaterial color="#a855f7" transparent opacity={Math.min(0.15 + (count * 0.12), 0.7)} depthWrite={false} />
        </mesh>;
      })}
      {obstacleCount <= 150 ? state.obstacles.map((point) => (
        <mesh key={`obstacle-${point.x}-${point.y}`} position={toWorld(point.x, point.y, state.width, state.height, cell)} castShadow={false}>
          <boxGeometry args={[cell * 0.92, 0.72, cell * 0.92]} /><meshStandardMaterial color="#455142" roughness={0.72} />
        </mesh>
      )) : (
        <instancedMesh ref={obstacleMesh} args={[undefined, undefined, obstacleCount]} castShadow={false}>
          <boxGeometry args={[cell * 0.92, 0.72, cell * 0.92]} /><meshStandardMaterial color="#455142" roughness={0.72} />
        </instancedMesh>
      )}
      {state.blocked.map((point) => (
        <mesh key={`blocked-${point.x}-${point.y}`} position={toWorld(point.x, point.y, state.width, state.height, cell)}><boxGeometry args={[cell * 0.84, 0.38, cell * 0.84]} /><meshStandardMaterial color="#dc2626" emissive="#7f1d1d" emissiveIntensity={0.35} /></mesh>
      ))}
      {state.pickups.map((pickup, index) => {
        const [x, _y, z] = toWorld(pickup.pos[0], pickup.pos[1], state.width, state.height, cell);
        return <group key={pickup.id}><mesh position={[x, 0.01, z]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[cell * 0.8, cell * 0.8]} /><meshStandardMaterial color="#22c55e" transparent opacity={0.8} /></mesh><Html position={[x, 0.15, z]} center><span className="three-pad-label">P{index + 1}</span></Html></group>;
      })}
      {state.drops.map((drop, index) => {
        const [x, _y, z] = toWorld(drop.pos[0], drop.pos[1], state.width, state.height, cell);
        return <group key={drop.id}><mesh position={[x, 0.01, z]} rotation={[-Math.PI / 2, 0, 0]}><planeGeometry args={[cell * 0.8, cell * 0.8]} /><meshStandardMaterial color="#3b82f6" transparent opacity={0.8} /></mesh><Html position={[x, 0.15, z]} center><span className="three-pad-label">D{index + 1}</span></Html></group>;
      })}
      {state.robots.map((robot) => (
        <group key={robot.id}>
          {robot.path.length > 1 && <Line points={robot.path.map(([x, y]) => toWorld(x, y, state.width, state.height, cell))} color={robot.color} transparent opacity={0.55} lineWidth={1.2} dashed />}
          <RobotModel robot={robot} width={state.width} height={state.height} speed={state.speed} onSelect={onRobotSelect} />
          {state.deadlock?.active && state.deadlock.cycle.includes(robot.id) && <mesh position={toWorld(robot.x, robot.y, state.width, state.height, cell)} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.28, 0.34, 24]} /><meshBasicMaterial color="#d946ef" transparent opacity={0.9} /></mesh>}
        </group>
      ))}
      <FollowCamera robot={state.robots.find((robot) => robot.id === followedRobot)} width={state.width} height={state.height} />
      <OrbitControls makeDefault onStart={onInteract} minPolarAngle={0.3} maxPolarAngle={Math.PI / 2.15} minDistance={maxSize * 0.35} maxDistance={maxSize * 1.8} />
    </>
  );
}

export function Warehouse3D({ state, blockMode, onBlockCell, onRobotSelect, readOnly, heatmap, followedRobot, onInteract }: { state: WarehouseState; blockMode?: boolean; onBlockCell?: (x: number, y: number) => void; onRobotSelect?: (id: string) => void; readOnly?: boolean; heatmap?: boolean; followedRobot?: string | null; onInteract?: () => void }) {
  const isTouch = typeof window !== "undefined" && window.matchMedia("(pointer: coarse)").matches;
  const maxSize = Math.max(state.width, state.height);
  return (
    <div className="warehouse-canvas" style={{ touchAction: "none" }}>
      <Canvas camera={{ position: [maxSize * 0.7, maxSize * 0.65, maxSize * 0.7], fov: 37 }} dpr={[1, 1.5]} shadows={!isTouch}>
        <Scene state={state} blockMode={blockMode} onBlockCell={onBlockCell} onRobotSelect={onRobotSelect} readOnly={readOnly} heatmap={heatmap} followedRobot={followedRobot} onInteract={onInteract} />
      </Canvas>
    </div>
  );
}

export function Warehouse2D({ state, blockMode = false, onBlockCell }: { state: WarehouseState; blockMode?: boolean; onBlockCell?: (x: number, y: number) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;
    const ratio = window.devicePixelRatio || 1;
    const bounds = element.getBoundingClientRect();
    element.width = bounds.width * ratio; element.height = bounds.height * ratio;
    context.scale(ratio, ratio); context.clearRect(0, 0, bounds.width, bounds.height);
    const cell = Math.min((bounds.width - 48) / state.width, (bounds.height - 48) / state.height);
    const left = (bounds.width - cell * state.width) / 2; const top = (bounds.height - cell * state.height) / 2;
    context.fillStyle = "#141b15"; context.fillRect(left, top, cell * state.width, cell * state.height);
    context.strokeStyle = "#344035";
    for (let x = 0; x <= state.width; x++) { context.beginPath(); context.moveTo(left + x * cell, top); context.lineTo(left + x * cell, top + state.height * cell); context.stroke(); }
    for (let y = 0; y <= state.height; y++) { context.beginPath(); context.moveTo(left, top + y * cell); context.lineTo(left + state.width * cell, top + y * cell); context.stroke(); }
    state.obstacles.forEach((rack) => { context.fillStyle = "#455142"; context.fillRect(left + rack.x * cell + 2, top + rack.y * cell + 2, cell - 4, cell - 4); });
    state.blocked.forEach((rack) => { context.fillStyle = "#dc2626"; context.fillRect(left + rack.x * cell + 3, top + rack.y * cell + 3, cell - 6, cell - 6); });
    state.pickups.forEach((pickup) => { context.fillStyle = "#22c55e"; context.fillRect(left + pickup.pos[0] * cell + 4, top + pickup.pos[1] * cell + 4, cell - 8, cell - 8); });
    state.drops.forEach((drop) => { context.fillStyle = "#3b82f6"; context.fillRect(left + drop.pos[0] * cell + 4, top + drop.pos[1] * cell + 4, cell - 8, cell - 8); });
    state.robots.forEach((robot) => { context.beginPath(); context.arc(left + (robot.x + 0.5) * cell, top + (robot.y + 0.5) * cell, Math.max(cell * 0.32, 5), 0, Math.PI * 2); context.fillStyle = statusColor(robot.status); context.fill(); });
  }, [state]);
  const click = (event: ReactMouseEvent<HTMLCanvasElement>) => {
    if (!blockMode) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const cell = Math.min((bounds.width - 48) / state.width, (bounds.height - 48) / state.height);
    const left = (bounds.width - cell * state.width) / 2; const top = (bounds.height - cell * state.height) / 2;
    const x = Math.floor((event.clientX - bounds.left - left) / cell); const y = Math.floor((event.clientY - bounds.top - top) / cell);
    if (x >= 0 && x < state.width && y >= 0 && y < state.height) onBlockCell?.(x, y);
  };
  return <canvas ref={canvas} className="warehouse-2d" aria-label="2D warehouse grid" onClick={click} />;
}
