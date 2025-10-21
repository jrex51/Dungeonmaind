import { SERVER_CONFIG } from '@/config/config'

export async function fetchConfig() {
  const res = await fetch(`${SERVER_CONFIG.BASE_URL}${SERVER_CONFIG.ENDPOINTS.GET_CONFIG}`)
  if (!res.ok) {
    throw new Error(`Failed to fetch config: ${res.status}`)
  }
  return res.json()
}
