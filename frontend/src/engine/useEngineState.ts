import { useEffect, useRef, useState } from "react";
import { API_BASE, wsUrl } from "./config";
import type { State, EventEntry } from "./types";

const MAX_EVENTS = 100;

export function useEngineState() {
  const [state, setState] = useState<State | null>(null);
  const [events, setEvents] = useState<EventEntry[]>([]);
  const [connected, setConnected] = useState(false);
  const [lastUpdateMs, setLastUpdateMs] = useState<number | null>(null);
  const [toast, setToast] = useState("");
  const seen = useRef(new Set<number>());

  const addEvents = (incoming: EventEntry[]) => {
    setEvents((current) => {
      const merged = [...incoming, ...current].filter((event) => {
        if (seen.current.has(event.id)) return false;
        seen.current.add(event.id);
        return true;
      }).slice(0, MAX_EVENTS);
      return merged;
    });
  };

  useEffect(() => {
    let active = true;
    let socket: WebSocket | null = null;
    let timer: number | undefined;
    const delays = [1000, 2000, 4000, 5000];
    let attempt = 0;
    const connect = () => {
      socket = new WebSocket(wsUrl());
      socket.onopen = () => { attempt = 0; setConnected(true); };
      socket.onclose = () => {
        setConnected(false);
        const delay = delays[Math.min(attempt++, delays.length - 1)];
        timer = window.setTimeout(connect, delay);
      };
      socket.onerror = () => socket?.close();
      socket.onmessage = (message) => {
        setLastUpdateMs(Date.now());
        try {
          const envelope = JSON.parse(message.data);
          if (envelope.type === "state") setState(envelope.data);
          if (envelope.type === "event") addEvents([envelope.data]);
          if (envelope.type === "error") setToast(envelope.message || envelope.code);
        } catch {
          setToast("Could not parse an engine message");
        }
      };
    };
    void fetch(`${API_BASE}/api/state`).then(async (response) => {
      if (!response.ok) throw new Error(`Backend returned ${response.status}`);
      if (active) setState(await response.json());
    }).catch((error) => setToast(error instanceof Error ? error.message : "Could not connect"));
    void fetch(`${API_BASE}/api/events?since=0`).then((response) => response.json()).then((payload) => {
      if (active) addEvents(Array.isArray(payload.events) ? payload.events : []);
    }).catch(() => undefined);
    connect();
    return () => { active = false; if (timer) window.clearTimeout(timer); socket?.close(); };
  }, []);

  async function command(path: string, options: RequestInit = {}): Promise<unknown> {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers: { "Content-Type": "application/json", ...options.headers },
      });
      const payload = await response.json().catch(() => ({ ok: false, error: "INVALID_RESPONSE", message: `Backend returned ${response.status}` }));
      if (!response.ok || payload.ok === false) {
        setToast(payload.message || payload.error || `Request failed (${response.status})`);
        return null;
      }
      return payload;
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Request failed");
      return null;
    }
  }

  const post = (path: string, body?: unknown) => command(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
  const patch = (path: string, body: unknown) => command(path, { method: "PATCH", body: JSON.stringify(body) });

  return {
    state, events, connected, lastUpdateMs, toast, clearToast: () => setToast(""),
    start: () => post("/api/sim/start"),
    pause: () => post("/api/sim/pause"),
    setSpeed: (speed: number) => post("/api/sim/speed", { speed }),
    step: () => post("/api/sim/step"),
    loadScenario: (scenarioId: string) => post(`/api/scenarios/${scenarioId}/load`),
    addJob: (pickupId: string, dropId: string) => post("/api/jobs", { pickup_id: pickupId, drop_id: dropId }),
    validateJob: (jobId: string, pickupId: string, dropId: string) => post("/api/jobs/validate", { job_id: jobId, pickup_id: pickupId, drop_id: dropId }),
    editJob: (jobId: string, pickupId: string, dropId: string) => patch(`/api/jobs/${jobId}`, { pickup_id: pickupId, drop_id: dropId }),
    blockCell: (x: number, y: number) => post("/api/cells/block", { x, y }),
    unblockCell: (x: number, y: number) => post("/api/cells/unblock", { x, y }),
    failRobot: (robotId: string) => post(`/api/robots/${robotId}/fail`),
  };
}
