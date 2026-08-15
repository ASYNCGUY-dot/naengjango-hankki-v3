import { apiFetch } from './client'
import type { components } from './schema'

export type Profile = components['schemas']['ProfileGetResponse']

export async function getProfile(userId: number, signal?: AbortSignal): Promise<Profile> {
  return apiFetch<Profile>(`/profile/${userId}`, { signal })
}
