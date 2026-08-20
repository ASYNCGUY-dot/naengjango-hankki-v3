import { API_BASE, apiFetch, tokenStore } from './client'
import type { components } from './schema'

export type BragItem = components['schemas']['BragItem']
export type BragLikeStatus = components['schemas']['BragLikeStatus']

/**
 * 자랑하기 - 이 서비스로 만들어본 결과를 올리고 서로 좋아요를 누른다.
 *
 * 여기 좋아요는 그 글이 고른 레시피의 추천에도 반영된다. 다만 **사람당 레시피당
 * 1회**라, 같은 레시피로 쓴 글이 여럿이고 전부 눌러도 레시피 추천은 하나만 오른다.
 * 그 계산은 서버가 한다(src/agents/brag_agent.py).
 */
export async function listBrags(
  { limit = 20, offset = 0 }: { limit?: number; offset?: number } = {},
  signal?: AbortSignal,
): Promise<BragItem[]> {
  return apiFetch<BragItem[]>('/brags', { query: { limit, offset }, signal })
}

export async function createBrag(
  userId: number,
  body: { recipe_id: number; body: string; image_url: string | null },
): Promise<BragItem> {
  return apiFetch<BragItem>('/brags', { method: 'POST', query: { user_id: userId }, body })
}

export async function deleteBrag(bragId: number, userId: number): Promise<void> {
  await apiFetch(`/brags/${bragId}`, { method: 'DELETE', query: { user_id: userId } })
}

export async function toggleBragLike(bragId: number, userId: number): Promise<BragLikeStatus> {
  return apiFetch<BragLikeStatus>(`/brags/${bragId}/like/toggle`, {
    method: 'POST',
    query: { user_id: userId },
  })
}

/** 서버가 사진 상한으로 쓰는 값과 같다(src/agents/storage_agent.py). */
export const MAX_PHOTO_BYTES = 2 * 1024 * 1024

/** 올리기 전에 브라우저에서 줄일 긴 변 길이. */
const RESIZE_MAX_EDGE = 1200

/**
 * 사진을 올리고 공개 주소를 받는다.
 *
 * apiFetch를 쓰지 않는다 - 그쪽은 본문을 JSON으로 직렬화하는데 여기는 multipart여야
 * 하고, Content-Type을 우리가 지정하면 boundary가 빠져서 서버가 파싱하지 못한다.
 * 브라우저가 알아서 붙이도록 비워둔다.
 */
export async function uploadBragPhoto(userId: number, file: Blob): Promise<string> {
  const form = new FormData()
  form.append('file', file, 'photo.jpg')

  const url = new URL('/brags/photo', API_BASE)
  url.searchParams.set('user_id', String(userId))

  const token = tokenStore.get()
  const res = await fetch(url.toString(), {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  })
  if (!res.ok) {
    const detail = await res
      .json()
      .then((data: { detail?: string }) => data.detail)
      .catch(() => undefined)
    throw new Error(detail ?? '사진을 올리지 못했어요.')
  }
  return ((await res.json()) as { image_url: string }).image_url
}

/**
 * 휴대폰 사진을 그대로 올리면 5~10MB라 서버 상한(2MB)에 걸린다. 긴 변을 1200px로
 * 줄이고 JPEG로 다시 굽는다 - 피드에 보이는 크기에는 이걸로 충분하고, 무료 티어의
 * 저장 용량과 대역폭을 아낀다.
 *
 * 브라우저가 canvas를 못 쓰는 등 어떤 이유로든 실패하면 원본을 그대로 돌려준다.
 * 상한을 넘으면 서버가 413으로 답하고 화면이 그 이유를 보여준다.
 */
export async function shrinkForUpload(file: File): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, RESIZE_MAX_EDGE / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)

    const context = canvas.getContext('2d')
    if (context === null) return file
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)

    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.85),
    )
    return blob ?? file
  } catch {
    return file
  }
}
