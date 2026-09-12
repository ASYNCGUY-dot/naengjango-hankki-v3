import { apiFetch } from './client'
import type { components } from './schema'

export type ShoppingLinks = components['schemas']['ShoppingLinksResponse']
export type PartnerKeyStatus = components['schemas']['PartnerKeyStatus']

/**
 * 냉장고에 없는 재료를 살 수 있는 링크.
 *
 * 서버가 부족한 재료를 골라 네이버·쿠팡 검색 링크를 만들어 준다. 재료 목록을 화면이
 * 따로 만들지 않는 이유는, 그러면 "지금 만들 수 있나요?" 카드가 세는 개수와 어긋나기
 * 때문이다 - 같은 판정을 두 곳에서 하면 반드시 갈라진다.
 *
 * 응답의 `earner`가 누가 수수료를 받는지 알려준다. 이건 화면이 판단할 수 없다 -
 * 레시피 작성자가 제휴 키를 등록했는지, 추천이 기준을 넘었는지는 서버만 안다.
 */
export async function getShoppingLinks(
  recipeId: number,
  userId: number,
  signal?: AbortSignal,
): Promise<ShoppingLinks> {
  return apiFetch<ShoppingLinks>(`/recommendation/recipes/${recipeId}/shopping-links`, {
    query: { user_id: userId },
    signal,
  })
}

/** 제휴 키를 등록해뒀는지. 저장된 키 자체는 서버가 절대 돌려주지 않는다. */
export async function getPartnerKeyStatus(
  userId: number,
  signal?: AbortSignal,
): Promise<PartnerKeyStatus> {
  return apiFetch<PartnerKeyStatus>(`/partner-keys/${userId}`, { signal })
}

export async function savePartnerKey(
  userId: number,
  accessKey: string,
  secretKey: string,
): Promise<PartnerKeyStatus> {
  return apiFetch<PartnerKeyStatus>(`/partner-keys/${userId}`, {
    method: 'PUT',
    body: { access_key: accessKey, secret_key: secretKey },
  })
}

export async function deletePartnerKey(userId: number): Promise<PartnerKeyStatus> {
  return apiFetch<PartnerKeyStatus>(`/partner-keys/${userId}`, { method: 'DELETE' })
}
