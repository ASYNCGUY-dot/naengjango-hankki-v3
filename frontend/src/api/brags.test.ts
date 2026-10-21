import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

describe('자랑 사진 업로드 주소', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllEnvs()
    vi.resetModules()
    localStorage.clear()
  })

  it.each([
    ['/api', `${window.location.origin}/api/brags/photo?user_id=7`],
    ['/api/', `${window.location.origin}/api/brags/photo?user_id=7`],
    ['https://api.example.test', 'https://api.example.test/brags/photo?user_id=7'],
  ])('기준 주소 %s에서도 multipart와 인증을 유지한다', async (base, expected) => {
    vi.stubEnv('VITE_API_BASE', base)
    const { uploadBragPhoto } = await import('./brags')
    const { tokenStore } = await import('./client')
    tokenStore.set('upload-token')
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(
      JSON.stringify({ image_url: 'https://images.example.test/photo.jpg' }),
      { status: 200, headers: { 'Content-Type': 'application/json' } },
    ))

    await expect(uploadBragPhoto(7, new Blob(['사진'], { type: 'image/jpeg' }))).resolves.toBe(
      'https://images.example.test/photo.jpg',
    )

    expect(fetchMock.mock.calls[0][0]).toBe(expected)
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.headers).toEqual({ Authorization: 'Bearer upload-token' })
    expect(init.body).toBeInstanceOf(FormData)
    const file = (init.body as FormData).get('file') as File
    expect(file.name).toBe('photo.jpg')
    expect(file.type).toBe('image/jpeg')
  })
})
