import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, API_BASE, apiFetch, toHttps, tokenStore } from './client'

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('toHttps', () => {
  it('공공데이터 원본의 http 주소를 https로 바꾼다', () => {
    // 이 처리를 빠뜨리면 https 페이지에서 브라우저가 혼합 콘텐츠로 이미지를 막는다.
    expect(toHttps('http://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png')).toBe(
      'https://www.foodsafetykorea.go.kr/uploadimg/cook/10_00028_2.png',
    )
  })

  it('이미 https면 그대로 둔다', () => {
    expect(toHttps('https://example.com/a.png')).toBe('https://example.com/a.png')
  })

  it('null을 그대로 통과시킨다', () => {
    // image_url은 타입이 string | null이다. 레시피 1,148개 중 2개가 실제로 비어 있다.
    expect(toHttps(null)).toBeNull()
    expect(toHttps(undefined)).toBeNull()
  })

  it('http가 주소 중간에 있는 경우는 건드리지 않는다', () => {
    expect(toHttps('https://cdn.test/redirect?to=http://x')).toBe(
      'https://cdn.test/redirect?to=http://x',
    )
  })
})

describe('apiFetch', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('배열 쿼리를 같은 키로 반복해서 붙인다', async () => {
    // FastAPI의 list[str] 규약이다. ingredients=고등어&ingredients=두부 형태여야
    // /recommendation/demo가 재료 두 개로 인식한다.
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse([]))

    await apiFetch('/recommendation/demo', { query: { ingredients: ['고등어', '두부'] } })

    const url = new URL(fetchMock.mock.calls[0][0] as string)
    expect(url.searchParams.getAll('ingredients')).toEqual(['고등어', '두부'])
    expect(url.origin + url.pathname).toBe(`${API_BASE}/recommendation/demo`)
  })

  it('undefined인 쿼리 값은 아예 붙이지 않는다', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse([]))

    await apiFetch('/recommendation/recipes/search', {
      query: { keyword: '두부', category: undefined },
    })

    const url = new URL(fetchMock.mock.calls[0][0] as string)
    expect(url.searchParams.has('category')).toBe(false)
    expect(url.searchParams.get('keyword')).toBe('두부')
  })

  it('토큰이 있으면 Authorization 헤더를 붙인다', async () => {
    tokenStore.set('tok-123')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))

    await apiFetch('/profile/1')

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect((init.headers as Record<string, string>).Authorization).toBe('Bearer tok-123')
  })

  it('토큰이 없으면 Authorization 헤더를 붙이지 않는다', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(jsonResponse({}))

    await apiFetch('/recommendation/demo')

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined()
  })

  it('401을 받으면 저장된 토큰을 지운다', async () => {
    // 백엔드가 만료된 토큰을 401로 돌려준다(V3에서 만료를 도입했다). 그대로 두면
    // 이후 모든 요청이 계속 401을 받으면서 사용자는 이유를 모른다.
    tokenStore.set('expired')
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: '로그인이 만료되었습니다. 다시 로그인해주세요.' }, 401),
    )

    await expect(apiFetch('/profile/1')).rejects.toBeInstanceOf(ApiError)
    expect(tokenStore.get()).toBeNull()
  })

  it('오류 응답의 detail 문구를 그대로 전달한다', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: '이미 존재하는 아이디입니다.' }, 409),
    )

    await expect(apiFetch('/auth/signup', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 409,
      detail: '이미 존재하는 아이디입니다.',
    })
  })

  it('422의 detail이 배열이어도 읽을 수 있는 문구로 바꾼다', async () => {
    // FastAPI의 검증 오류는 detail이 객체 배열이라 그대로 보여주면 화면에 [object Object]가 뜬다.
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      jsonResponse({ detail: [{ loc: ['body', 'password'], msg: 'too short' }] }, 422),
    )

    await expect(apiFetch('/auth/signup', { method: 'POST', body: {} })).rejects.toMatchObject({
      status: 422,
      detail: '입력값을 확인해주세요.',
    })
  })

  it('본문이 JSON이 아닌 오류도 터지지 않고 문구를 만든다', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('<html>502 Bad Gateway</html>', { status: 502 }),
    )

    await expect(apiFetch('/recommendation/demo')).rejects.toMatchObject({ status: 502 })
  })
})
