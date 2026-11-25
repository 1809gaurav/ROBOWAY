import { Canvas, useFrame } from "@react-three/fiber";
import { ContactShadows, Line, OrbitControls } from "@react-three/drei";
import { useEffect, useRef } from "react";
import type { Group, Mesh } from "three";

export type Robot = {
  id: string;
  name: string;
  x: number;
  y: number;
  color: string;
  status: string;
  target: { x: number; y: number };
  path: number[][];
  progress: number;
  battery: number;
  completed: number;
};

type WarehouseState = {
  width: number;
  height: number;
  blocked: { x: number; y: number }[];
  robots: Robot[];
};

const CELL = 0.72;
const point = (x: number, y: number): [number, number, number] => [
  (x - 8.5) * CELL,
  0.06,
  (5.5 - y) * CELL,
];

function RobotModel({ robot }: { robot: Robot }) {
  const group = useRef<Group>(null);
  const body = useRef<Mesh>(null);
  useFrame((_, delta) => {
    if (!group.current) return;
    const current = group.current.position;
    const targetX = (robot.x - 8.5) * CELL;
    const targetZ = (5.5 - robot.y) * CELL;
    current.x += (targetX - current.x) * Math.min(delta * 6, 1);
    current.z += (targetZ - current.z) * Math.min(delta * 6, 1);
    if (body.current) body.current.rotation.y += delta * 1.4;
  });
  return (
    <group ref={group} position={point(robot.x, robot.y)}>
      <mesh position={[0, 0.22, 0]} castShadow>
        <cylinderGeometry args={[0.22, 0.25, 0.2, 8]} />
        <meshStandardMaterial color={robot.color} metalness={0.16} roughness={0.32} />
      </mesh>
      <mesh ref={body} position={[0, 0.38, 0]} castShadow>
        <boxGeometry args={[0.21, 0.12, 0.18]} />
        <meshStandardMaterial color="#f4f4e9" emissive={robot.color} emissiveIntensity={0.18} />
      </mesh>
      <mesh position={[0, 0.5, 0]} castShadow>
        <sphereGeometry args={[0.055, 12, 12]} />
        <meshStandardMaterial color="#fff4cc" emissive="#ffc767" emissiveIntensity={1.2} />
      </mesh>
    </group>
  );
}

function Scene({ state }: { state: WarehouseState }) {
  return (
    <>
      <color attach="background" args={["#111711"]} />
      <fog attach="fog" args={["#111711", 11, 24]} />
      <ambientLight intensity={1.25} />
      <directionalLight position={[5, 10, 4]} intensity={2.2} castShadow shadow-mapSize={[1024, 1024]} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.07, 0]} receiveShadow>
        <planeGeometry args={[14, 10]} />
        <meshStandardMaterial color="#1a211b" roughness={0.86} />
      </mesh>
      {Array.from({ length: state.width + 1 }, (_, x) => (
        <Line key={`gx-${x}`} points={[[((x - 9) * CELL), 0.005, -4.4], [((x - 9) * CELL), 0.005, 4.4]]} color="#354036" transparent opacity={0.45} lineWidth={0.6} />
      ))}
      {Array.from({ length: state.height + 1 }, (_, y) => (
        <Line key={`gy-${y}`} points={[[-6.3, 0.005, ((y - 6) * CELL)], [6.3, 0.005, ((y - 6) * CELL)]]} color="#354036" transparent opacity={0.45} lineWidth={0.6} />
      ))}
      {state.blocked.map(({ x, y }) => (
        <mesh key={`rack-${x}-${y}`} position={[(x - 8.5) * CELL, 0.36, (5.5 - y) * CELL]} castShadow receiveShadow>
          <boxGeometry args={[CELL * 0.92, 0.68, CELL * 0.92]} />
          <meshStandardMaterial color={(x + y) % 3 === 0 ? "#455142" : "#374333"} roughness={0.72} />
        </mesh>
      ))}
      {state.robots.map((robot) => (
        <group key={`path-${robot.id}`}>
          {robot.path.length > 1 && (
            <Line
              points={robot.path.slice(robot.progress).map(([x, y]) => [(x - 8.5) * CELL, 0.03, (5.5 - y) * CELL])}
              color={robot.color}
              transparent
              opacity={0.5}
              lineWidth={1.2}
              dashed
              dashSize={0.1}
              gapSize={0.08}
            />
          )}
          <RobotModel robot={robot} />
        </group>
      ))}
      <ContactShadows position={[0, -0.04, 0]} opacity={0.28} scale={12} blur={2.4} far={5} />
      <OrbitControls makeDefault minPolarAngle={0.3} maxPolarAngle={Math.PI / 2.15} minDistance={6} maxDistance={17} />
    </>
  );
}

export function Warehouse3D({ state }: { state: WarehouseState }) {
  return (
    <div className="warehouse-canvas">
      <Canvas camera={{ position: [9, 9.5, 10], fov: 37 }} shadows dpr={[1, 1.6]}>
        <Scene state={state} />
      </Canvas>
    </div>
  );
}

export function Warehouse2D({ state }: { state: WarehouseState }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const element = canvas.current;
    const context = element?.getContext("2d");
    if (!element || !context) return;
    const ratio = window.devicePixelRatio || 1;
    const bounds = element.getBoundingClientRect();
    element.width = bounds.width * ratio;
    element.height = bounds.height * ratio;
    context.scale(ratio, ratio);
    context.clearRect(0, 0, bounds.width, bounds.height);
    const cell = Math.min((bounds.width - 48) / state.width, (bounds.height - 48) / state.height);
    const left = (bounds.width - cell * state.width) / 2;
    const top = (bounds.height - cell * state.height) / 2;
    context.fillStyle = "#141b15";
    context.fillRect(left, top, cell * state.width, cell * state.height);
    context.strokeStyle = "#344035";
    context.lineWidth = 1;
    for (let x = 0; x <= state.width; x++) {
      context.beginPath();
      context.moveTo(left + x * cell, top);
      context.lineTo(left + x * cell, top + state.height * cell);
      context.stroke();
    }
    for (let y = 0; y <= state.height; y++) {
      context.beginPath();
      context.moveTo(left, top + y * cell);
      context.lineTo(left + state.width * cell, top + y * cell);
      context.stroke();
    }
    for (const rack of state.blocked) {
      context.fillStyle = "#3c4938";
      context.fillRect(left + rack.x * cell + 2, top + rack.y * cell + 2, cell - 4, cell - 4);
    }
    for (const robot of state.robots) {
      const path = robot.path.slice(robot.progress);
      if (path.length > 1) {
        context.beginPath();
        context.setLineDash([4, 4]);
        context.strokeStyle = `${robot.color}88`;
        context.lineWidth = 2;
        context.moveTo(left + (path[0][0] + 0.5) * cell, top + (path[0][1] + 0.5) * cell);
        path.slice(1).forEach(([x, y]) => context.lineTo(left + (x + 0.5) * cell, top + (y + 0.5) * cell));
        context.stroke();
        context.setLineDash([]);
      }
      context.beginPath();
      context.arc(left + (robot.x + 0.5) * cell, top + (robot.y + 0.5) * cell, Math.max(cell * 0.32, 5), 0, Math.PI * 2);
      context.fillStyle = robot.color;
      context.shadowColor = robot.color;
      context.shadowBlur = 12;
      context.fill();
      context.shadowBlur = 0;
    }
  }, [state]);
  return <canvas ref={canvas} className="warehouse-2d" aria-label="2D warehouse grid" />;
}
