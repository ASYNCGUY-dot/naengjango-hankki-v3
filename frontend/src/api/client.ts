/**
 * 백엔드(FastAPI) 호출을 한 군데로 모은다.
 *
 * 응답 타입은 src/api/schema.d.ts에서 가져온다. 그 파일은 배포된 API의 OpenAPI 명세로
 * 자동 생성한 것이라 손으로 고치지 않는다(백엔드가 바뀌면 `npm run gen:api`).
 *
 * 콜드스타트: Render 무료 티어라 15분 유휴 후 첫 요청이 30~60초 걸린다(실측 34.6초).
 * 기본 fetch는 타임아웃이 없어서 그동안 아무 신호도 없이 멈춘 것처럼 보이므로,
 * 여기서 명시적으로 길게 잡고 "깨우는 중"을 화면이 판단할 수 있게 상태를 알려준다.
 */

import type { components } from './schema'

export type RecommendationItem = components['schemas']['RecommendationItem']
export type RecipeDetail = components['schemas']['RecipeDetail']
export type RecipeSummary = components['schemas']['RecipeSummary']
export type LoginResponse = components['schemas']['LoginResponse']
export type SignupResponse = components['schemas']['SignupResponse']

/** 배포 환경에서는 VITE_API_BASE로 덮어쓴다. 없으면 살아 있는 V2 백엔드를 본다. */
export const API_BASE: string =
  import.meta.env.VITE_API_BASE ?? 'https://naengjango-hankki-v2-api.onrender.com'

/** 콜드스타트 실측이 34.6초라 그보다 넉넉하게 잡는다. */
const REQUEST_TIMEOUT_MS = 90_000

/** 응답이 이 시간을 넘기면 "서버 깨우는 중" 안내를 띄울 만하다고 본다. */
export const SLOW_RESPONSE_HINT_MS = 3_000

export class ApiError extends Error {
  // 생성자 파라미터 프로퍼티(constructor(readonly x))를 쓰지 않는다 - TypeScript 6의
  // erasableSyntaxOnly가 금지한다. 타입만 지우면 되는 문법이 아니라 코드를 만들어내기 때문이다.
  readonly status: number
  readonly detail: string

  constructor(status: number, detail: string) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

export class TimeoutError extends Error {
  constructor() {
    super('서버가 응답하지 않습니다. 잠시 후 다시 시도해주세요.')
    this.name = 'TimeoutError'
  }
}

const TOKEN_KEY = 'naengjango.token'

export const tokenStore = {
  get: (): string | null => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

type RequestOptions = {
  method?: string
  body?: unknown
  /** 쿼리 파라미터. 배열이면 같은 키를 반복해서 붙인다(FastAPI의 list[str] 규약). */
  query?: Record<string, string | number | boolean | string[] | undefined>
  signal?: AbortSignal
}

function buildUrl(path: string, query?: RequestOptions['query']): string {
  const url = new URL(path, API_BASE)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined) continue
      if (Array.isArray(value)) {
        for (const item of value) url.searchParams.append(key, item)
      } else {
        url.searchParams.set(key, String(value))
      }
    }
  }
  return url.toString()
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, query, signal } = options

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS)
  // 호출부가 준 signal(화면 언마운트 등)과 타임아웃을 함께 본다.
  signal?.addEventListener('abort', () => controller.abort(), { once: true })

  const headers: Record<string, string> = {}
  const token = tokenStore.get()
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let response: Response
  try {
    response = await fetch(buildUrl(path, query), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    })
  } catch (error) {
    if (controller.signal.aborted) throw new TimeoutError()
    throw error
  } finally {
    clearTimeout(timer)
  }

  if (response.status === 401) {
    // 토큰이 만료됐거나 무효하다. 남겨두면 이후 요청이 계속 401을 받는다.
    tokenStore.clear()
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response))
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data = await response.json()
    const detail = (data as { detail?: unknown }).detail
    if (typeof detail === 'string') return detail
    // FastAPI의 422는 detail이 배열이다.
    if (Array.isArray(detail)) return '입력값을 확인해주세요.'
  } catch {
    // 본문이 JSON이 아닌 경우(프록시 오류 페이지 등)
  }
  return `요청에 실패했습니다 (${response.status})`
}

/**
 * 레시피 이미지 주소는 공공데이터 원본이 http다. 우리 페이지는 https로 서비스되므로
 * 그대로 쓰면 브라우저가 혼합 콘텐츠로 막는다. 같은 주소를 https로 요청해도 동일한
 * 파일이 오는 것을 확인했으므로(2026-08-12) 스킴만 바꿔서 쓴다.
 */
export function toHttps(url: string | null | undefined): string | null {
  if (!url) return null
  return url.startsWith('http://') ? `https://${url.slice('http://'.length)}` : url
}
