import { apiFetch } from './client'
import type { components } from './schema'

export type Profile = components['schemas']['ProfileGetResponse']
export type ProfileBody = components['schemas']['ProfileRequest']
export type AllergyOption = components['schemas']['AllergyOption']
export type ProfileOptions = components['schemas']['ProfileOptions']

/**
 * 가입·온보딩 선택지. 인가가 없어 가입 전에도 부를 수 있다.
 *
 * 화면이 목록을 따로 들면 서버가 아는 값과 조용히 어긋난다. 성별·연령대는 영양 기준표의
 * 키이고 병력은 조정 규칙의 키라, 어긋나면 그 기능이 통째로 꺼진 채 화면만 정상으로 보인다.
 */
export async function getProfileOptions(signal?: AbortSignal): Promise<ProfileOptions> {
  return apiFetch<ProfileOptions>('/profile/options', { signal })
}

export async function getProfile(userId: number, signal?: AbortSignal): Promise<Profile> {
  return apiFetch<Profile>(`/profile/${userId}`, { signal })
}

export async function updateProfile(userId: number, body: ProfileBody): Promise<void> {
  await apiFetch(`/profile/${userId}`, { method: 'PUT', body })
}

/**
 * 식단 정보 화면에 들어왔다고 알린다. 사용 로그만 남기고 아무것도 돌려받지 않는다.
 *
 * 가입만 하고 멈춘 사람이 이 화면까지 왔는지 가르려고 둔다. 화면은 결과를 기다리지 않고,
 * 실패해도 아무 영향이 없어야 한다 - 호출부에서 오류를 삼킨다.
 */
export async function recordOnboardingView(userId: number): Promise<void> {
  await apiFetch(`/profile/${userId}/onboarding-view`, { method: 'POST' })
}

/**
 * 고를 수 있는 알레르기 목록.
 *
 * 화면이 목록을 지어내지 않는다. 태그에 없는 값을 고르게 하면 사용자는 골랐는데 필터는
 * 아무것도 안 거르고, 본인은 걸러졌다고 믿는다. 서버가 실제 태그에서 만들어 준다.
 */
export async function listAllergyOptions(signal?: AbortSignal): Promise<AllergyOption[]> {
  return apiFetch<AllergyOption[]>('/profile/allergy-options', { signal })
}

/** 선택지는 화면에서 정한다 - 서버는 문자열을 그대로 받는다. */
export const HEALTH_GOALS = ['체중감량', '체중유지', '근육증가', '건강관리'] as const
export const PURPOSES = ['자취생 식단관리', '간단한 한 끼', '다이어트 식단', '가족 식사'] as const
export const COOKING_LEVELS = ['초급', '중급', '고급'] as const
export const NOVELTY_PREFS = ['새로운 메뉴 선호', '익숙한 메뉴 선호'] as const
export const COOKING_TOOLS = [
  '가스레인지',
  '인덕션',
  '전자레인지',
  '오븐',
  '에어프라이어',
  '전기밥솥',
] as const
export const HOUSEHOLD_SIZES = [1, 2, 3, 4, 5, 6] as const

/** 여러 개를 고르는 항목은 콤마로 이어 저장한다(백엔드가 그렇게 읽는다). */
export function joinSelections(values: string[]): string {
  return values.join(',')
}

export function splitSelections(raw: string | null | undefined): string[] {
  return (raw ?? '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean)
}
