import { SERVER_CONFIG } from '@/config/config'

export type Role = "leader" | "member";
export type PlayerOut = {
  id: string;
  name: string;
  role: Role;
  hp: number;
  max_hp: number;
  temp_hp: number;
  attributes?: Record<string, number> | null;
  created_at: string;
  last_seen_at: string;
  backend_url: string;
}

export async function join(name: string, role: Role, reuse_id?: string): Promise<PlayerOut> {
  const url = new URL("/players", SERVER_CONFIG.BASE_URL).toString();
  const body: any = { name, role };
  if (reuse_id) body.reuse_id = reuse_id; console.debug(`api/players.ts: reuse_id=${reuse_id} angegeben`);

  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText);
    throw new Error(msg ||`HTTP ${res.status}`);
  }
  return res.json();
}

export async function listPlayers(): Promise<PlayerOut[]> {
  const url = new URL("/players", SERVER_CONFIG.BASE_URL).toString();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

export async function leave(playerId: string): Promise<void> {
  const url = new URL(`/players/${playerId}`, SERVER_CONFIG.BASE_URL).toString();
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error('HTTP ${res.status}');
}

export async function checkPlayerExists(playerId: string): Promise<{ exists: boolean }> {
  const url = new URL(`/players/${playerId}/exists`, SERVER_CONFIG.BASE_URL).toString();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}
