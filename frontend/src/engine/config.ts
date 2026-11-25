export function resolveApiBase(): string {
  const params = new URLSearchParams(window.location.search);
  const queryApi = params.get("api");
  if (queryApi) {
    sessionStorage.setItem("roboway-api-base", queryApi);
    return queryApi.replace(/\/$/, "");
  }
  const remembered = sessionStorage.getItem("roboway-api-base");
  if (remembered) return remembered.replace(/\/$/, "");
  const configured = import.meta.env.VITE_API_BASE as string | undefined;
  if (configured) return configured.replace(/\/$/, "");
  const host = window.location.hostname;
  if (host !== "localhost" && host !== "127.0.0.1") {
    return `http://${host}:8000`;
  }
  return "http://localhost:8000";
}

export const API_BASE = resolveApiBase();

export function wsUrl(): string {
  const url = new URL(API_BASE);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.pathname = "/ws";
  url.search = "";
  url.hash = "";
  return url.toString();
}
