// Normalisiert Eingaben wie "localhost:8000/health" -> "http://localhost:8000"
export function toOrigin(input: string, endpoint = ""): string {
  // Protokoll sicherstellen (http/https) oder protokoll-relative //host zulassen
  const withProtocol = /^(https?:)?\/\//i.test(input) ? input : `http://${input}`;
  // Nur die Origin verwenden (Schema + Host + Port), Pfade abschneiden
  //    (damit "http://host:8000/health" -> "http://host:8000")
  const base = new URL(withProtocol).origin;
  // Leeren Endpoint speziell behandeln -> Origin unverändert zurückgeben
  if (!endpoint) return base;
  // Falls Endpoint schon absolut ist, direkt zurückgeben
  if (/^(https?:)?\/\//i.test(endpoint)) return endpoint;
  // Führenden Slash sicherstellen und zusammensetzen
  const path = endpoint.startsWith("/") ? endpoint : `/${endpoint}`;
  return `${base}${path}`;
}

let _apiBase =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ||
  localStorage.getItem("apiBaseUrl") ||
  "";

export function setApiBaseFromInput(input: string) {
  _apiBase = toOrigin(input);
  localStorage.setItem("apiBaseUrl", _apiBase);
}

export function getApiBase(): string {
  if (!_apiBase) throw new Error("API base URL unknown. Please configure the backend address.");
  return _apiBase;
}
