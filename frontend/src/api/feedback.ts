import { apiFetch } from './client'
import type { components } from './schema'

export type FeedbackItem = components['schemas']['FeedbackItem']

/**
 * 앱에 대한 피드백.
 *
 * 레시피 후기(api/reviews.ts)와 다르다. 후기는 레시피에 붙고, 이건 앱 전체에
 * 대한 것이라 붙을 레시피가 없다.
 *
 * 읽는 범위가 둘로 나뉜다. 쓴 사람은 자기 글만(`listMyFeedback`), 관리자는
 * 전부(`listAllFeedback`) 본다. 지인 테스트에서 남의 의견이 보이면 그쪽으로
 * 끌려가서, 두 번째 사람부터는 자기 생각이 아니라 "나도 그랬어"를 쓰게 된다.
 */
export async function listMyFeedback(
  userId: number,
  signal?: AbortSignal,
): Promise<FeedbackItem[]> {
  return apiFetch<FeedbackItem[]>('/feedback', { query: { user_id: userId }, signal })
}

/** 관리자만. 일반 계정이 부르면 서버가 403으로 막는다. */
export async function listAllFeedback(
  userId: number,
  signal?: AbortSignal,
): Promise<FeedbackItem[]> {
  return apiFetch<FeedbackItem[]>('/feedback/all', { query: { user_id: userId }, signal })
}

export async function createFeedback(userId: number, body: string): Promise<FeedbackItem> {
  return apiFetch<FeedbackItem>('/feedback', {
    method: 'POST',
    query: { user_id: userId },
    body: { body },
  })
}

export async function deleteFeedback(feedbackId: number, userId: number): Promise<void> {
  await apiFetch(`/feedback/${feedbackId}`, { method: 'DELETE', query: { user_id: userId } })
}
