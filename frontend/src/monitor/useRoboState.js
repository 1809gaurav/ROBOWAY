import { useEffect, useRef, useState } from "react";

const MAX_EVENTS = 100;

export function resolveApiBase() {
  const queryApi = new URLSearchParams(window.location.search).get("api");
  if (queryApi) {
    try {
      sessionStorage.setItem("roboway-api-base", queryApi);
    } catch (error) {
      console.warn("Could not remember the monitor API URL for this session.", error);
    }
    return queryApi.replace(/\/$/, "");
  }
  try {
    const rememberedApi = sessionStorage.getItem("roboway-api-base");
    if (rememberedApi) return rememberedApi.replace(/\/$/, "");
  } catch (error) {
    console.warn("Could not read the remembered monitor API URL.", error);
  }
  return (import.meta.env.VITE_API_BASE ?? "http://localhost:8000").replace(/\/$/, "");
}

export function getWebSocketUrl(apiBase) {
  const url = new URL(apiBase);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws";
  url.search = "";
  url.hash = "";
  return url.toString();
}

function eventFromMessage(message) {
  if (message?.type !== "event") return null;
  return message.event ?? message.data ?? message;
}

function eventsFromResponse(payload) {
  if (Array.isArray(payload)) return payload;
  if (Array.isArray(payload?.events)) return payload.events;
  return [];
}

export function useRoboState(url) {
  const [state, setState] = useState(null);
  const [events, setEvents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [connectedAtMs, setConnectedAtMs] = useState(null);
  const [lastUpdateMs, setLastUpdateMs] = useState(null);
  const [eventsError, setEventsError] = useState("");
  const seenIds = useRef(new Set());
  const prefillPromise = useRef(null);

  useEffect(() => {
    let active = true;
    let socket;
    let reconnectTimer;
    let reconnectDelay = 1000;

    const addEvents = (incoming) => {
      if (!active || !incoming.length) return;
      const fresh = incoming.filter((item) => {
        if (item?.id === undefined) return true;
        if (seenIds.current.has(item.id)) return false;
        seenIds.current.add(item.id);
        return true;
      });
      if (fresh.length) setEvents((current) => [...current, ...fresh].slice(-MAX_EVENTS));
    };

    const prefillEvents = async () => {
      if (!prefillPromise.current) {
        prefillPromise.current = fetch(`${url.replace(/\/ws$/, "").replace(/\/$/, "").replace(/^ws:/, "http:").replace(/^wss:/, "https:")}/api/events?since=0`)
          .then((response) => {
            if (!response.ok) throw new Error(`Event history returned ${response.status}`);
            return response.json();
          })
          .then(eventsFromResponse)
          .catch((error) => ({ error }));
      }
      const result = await prefillPromise.current;
      if (!active) return;
      if (result?.error) {
        const message = result.error instanceof Error ? result.error.message : "Could not load event history.";
        setEventsError(message);
      } else {
        addEvents(result);
        setEventsError("");
      }
    };

    const connect = () => {
      if (!active) return;
      socket = new WebSocket(url);
      socket.onopen = () => {
        if (!active) return;
        reconnectDelay = 1000;
        setConnected(true);
        setConnectedAtMs(Date.now());
        void prefillEvents();
      };
      socket.onmessage = (event) => {
        if (!active) return;
        setLastUpdateMs(Date.now());
        try {
          const message = JSON.parse(event.data);
          if (message?.type === "event") {
            const item = eventFromMessage(message);
            if (item) addEvents([item]);
          } else if (message?.type === "state") {
            setState(message.state ?? message.data ?? null);
          } else if (message && typeof message === "object" && message.grid) {
            setState(message);
          }
        } catch (error) {
          console.error("Could not parse a RoboWay WebSocket message.", error);
        }
      };
      socket.onclose = () => {
        if (!active) return;
        setConnected(false);
        setConnectedAtMs(null);
        reconnectTimer = window.setTimeout(connect, reconnectDelay);
        reconnectDelay = Math.min(reconnectDelay * 2, 5000);
      };
      socket.onerror = () => socket.close();
    };

    connect();
    return () => {
      active = false;
      window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [url]);

  return { state, events, connected, connectedAtMs, lastUpdateMs, eventsError };
}
