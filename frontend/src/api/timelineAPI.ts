import { SERVER_CONFIG } from '@/config/config'

export type TimelineEvent = {
  timestamp: number
  title: string
  description: string
}

export async function fetchTimelineEvents(baseUrl?: string): Promise<TimelineEvent[]> {
  const url = new URL(SERVER_CONFIG.ENDPOINTS.TIMELINE, baseUrl ?? SERVER_CONFIG.BASE_URL).toString()
  const res = await fetch(url)

  if (!res.ok) {
    throw new Error(`Failed to fetch timeline events: HTTP ${res.status}`)
  }

  return (await res.json()) as TimelineEvent[]
}