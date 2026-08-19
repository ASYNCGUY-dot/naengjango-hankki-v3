import { apiFetch } from './client'
import type { components } from './schema'

export type MySubmissionItem = components['schemas']['MySubmissionItem']
export type MySubmissionDetail = components['schemas']['MySubmissionDetail']
export type SubmissionRequest = components['schemas']['SubmissionRequest']
export type SubmissionResponse = components['schemas']['SubmissionResponse']

/**
 * 식품영양성분 DB(30만 건)에 없는 재료를 사용자가 직접 채워 넣는 기능.
 *
 * 공식 DB에 이미 있는 이름이거나 남이 먼저 등록한 이름이면 status가 pending이 된다 -
 * 공식 값을 사용자 입력이 조용히 덮으면 다른 사람의 영양 계산까지 같이 바뀐다.
 */
export async function listMySubmissions(
  userId: number,
  signal?: AbortSignal,
): Promise<MySubmissionItem[]> {
  return apiFetch<MySubmissionItem[]>('/ingredient-submissions', {
    query: { user_id: userId },
    signal,
  })
}

export async function getMySubmission(
  submissionId: number,
  userId: number,
  signal?: AbortSignal,
): Promise<MySubmissionDetail> {
  return apiFetch<MySubmissionDetail>(`/ingredient-submissions/${submissionId}`, {
    query: { user_id: userId },
    signal,
  })
}

export async function submitIngredient(
  userId: number,
  body: SubmissionRequest,
): Promise<SubmissionResponse> {
  return apiFetch<SubmissionResponse>('/ingredient-submissions', {
    method: 'POST',
    query: { user_id: userId },
    body,
  })
}

export async function updateSubmission(
  submissionId: number,
  userId: number,
  body: SubmissionRequest,
): Promise<SubmissionResponse> {
  return apiFetch<SubmissionResponse>(`/ingredient-submissions/${submissionId}`, {
    method: 'PUT',
    query: { user_id: userId },
    body,
  })
}
