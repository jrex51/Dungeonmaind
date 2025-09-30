import { getApiBase } from '@/config/apiBase.ts';

export type Role = "leader" | "member";
export type PlayerOut = {
  id: string; name: string; role: Role; created_at: string; last_seen_at: string;
}

export async function join(name: string, role: Role): Promise<PlayerOut> {
  const url = new URL("/players", getApiBase().toString()).toString();
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, role }),
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(msg ||`HTTP ${res.status}`);
  }
  return res.json();
}

export async function listPlayers(): Promise<PlayerOut[]> {
  const url = new URL("/players", getApiBase().toString()).toString();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function leave(playerId: string): Promise<void> {
  const url = new URL(`/players/${playerId}`, getApiBase().toString()).toString();
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error('HTTP ${res.status}');
}
