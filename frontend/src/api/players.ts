import { SERVER_CONFIG } from '@/config/config'

export type Role = 'leader' | 'member'

export type AbilityScores = {
  str?: number
  dex?: number
  con?: number
  int_?: number
  wis?: number
  cha?: number
} & Record<string, number | string | undefined>

export type Hp = {
  current: number
  max: number
  temp: number
}

/** Server + client mirror */
export type PlayerOut = {
  id: string
  name: string
  role: Role
  created_at: string
  last_seen_at: string
  backend_url: string
  hp: Hp
  abilities?: AbilityScores | { [k: string]: any } | undefined
}

export async function join(name: string, role: Role): Promise<PlayerOut> {
  const url = new URL('/players', SERVER_CONFIG.BASE_URL).toString()
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, role }),
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => res.statusText)
    throw new Error(msg || `HTTP ${res.status}`)
  }
  return (await res.json()) as PlayerOut
}

export async function leave(playerId: string): Promise<void> {
  const url = new URL(`/players/${playerId}`, SERVER_CONFIG.BASE_URL).toString()
  const res = await fetch(url, { method: 'DELETE' })
  if (!res.ok && res.status !== 204) throw new Error(`HTTP ${res.status}`)
}

export async function listPlayers(): Promise<PlayerOut[]> {
  const url = new URL('/players', SERVER_CONFIG.BASE_URL).toString()
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return (await res.json()) as PlayerOut[]
}
