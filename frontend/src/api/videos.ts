import { apiFetch } from './client'
import type { components } from './schema'

export type PopularVideo = components['schemas']['PopularVideo']

/**
 * 유튜브 인기 요리 영상.
 *
 * `popular_videos` 테이블에 미리 수집해둔 것을 읽는다 - 화면이 유튜브 API를 직접
 * 부르지 않는다. 무료 할당량이 하루 단위라, 사람이 홈을 열 때마다 부르면 금방 막힌다.
 *
 * 그래서 목록이 오래돼 있을 수 있다(수집 시각은 fetched_at에 남는다). 홈 최상단에
 * 두는 이유는 "오늘 뭐 먹지"에 가장 빨리 답하는 것이 남이 이미 검증한 인기 영상이기
 * 때문이지, 최신성 때문이 아니다.
 */
export async function listVideoCategories(signal?: AbortSignal): Promise<string[]> {
  return apiFetch<string[]>('/popular-videos/categories', { signal })
}

export async function listPopularVideos(
  category: string,
  limit = 10,
  signal?: AbortSignal,
): Promise<PopularVideo[]> {
  return apiFetch<PopularVideo[]>(`/popular-videos/${encodeURIComponent(category)}`, {
    query: { limit },
    signal,
  })
}
