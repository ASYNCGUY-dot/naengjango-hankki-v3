import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { getSubstitution, type Substitution } from '../api/recipes'
import { getShoppingLinks, type ShoppingLinks } from '../api/shopping'
import { useAuth } from '../auth/context'
import styles from './MissingIngredientsCard.module.css'

/**
 * 제휴 링크에는 대가성 고지가 붙어야 한다. 주체가 사이트일 때와 레시피 작성자일 때가
 * 다르므로 서버가 내려준 `earner`로 고른다 - 화면이 판단하면 서버와 어긋난다.
 */
function disclosure(links: ShoppingLinks | null): string | null {
  if (!links) return null
  if (links.earner === 'author') {
    const who = links.author_name ?? '작성자'
    return `구매 링크는 이 레시피를 올린 ${who}님의 제휴 링크예요. 구매하시면 그분에게 수수료가 갑니다.`
  }
  if (links.earner === 'site') {
    return '구매 링크에는 제휴 링크가 포함될 수 있어요. 구매하시면 운영자에게 일정 수수료가 갑니다.'
  }
  // 'none' - 아무 키도 안 붙은 일반 검색 링크라 고지할 것이 없다.
  return null
}

/**
 * "이거 지금 만들 수 있나".
 *
 * 서버는 부족한 재료와 대체 제안을 원래부터 계산하고 있었는데(substitution_agent) 화면이
 * 부르지 않아 아무도 못 봤다(2026-08-18까지). 추천 카드의 "2개만 더 있으면 돼요"가
 * 여기서 "무엇이" 부족한지로 이어진다.
 *
 * 대체 제안은 세 종류다. 바꿔 쓸 수 있는 것(substitute), 소량이라 빼도 되는 것(omit),
 * 그리고 알 수 없는 것(unknown). 마지막을 "사야 한다"고 단정하지 않는다 - 대체재 정보가
 * 없다는 뜻이지 반드시 사야 한다는 뜻이 아니다.
 *
 * 냉장고에 저장된 재료가 기준이다. 추천 화면에서 그때그때 고친 재료는 반영되지 않으므로
 * 그 사실을 화면에 적는다 - 안 적으면 "아까 뺐는데 왜 아직 있지"가 된다.
 */
export default function MissingIngredientsCard({ recipeId }: { recipeId: number }) {
  const { userId, isAuthenticated } = useAuth()
  const [data, setData] = useState<Substitution | null>(null)
  const [failed, setFailed] = useState(false)
  const [links, setLinks] = useState<ShoppingLinks | null>(null)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    getSubstitution(recipeId, userId, controller.signal)
      .then(setData)
      .catch(() => {
        // 레시피 본문은 이미 보인다. 이 카드 하나 때문에 화면을 망치지 않는다.
        if (!controller.signal.aborted) setFailed(true)
      })
    // 구매 링크는 따로 받는다. 이쪽이 실패해도 부족한 재료 목록은 그대로 보여야 한다 -
    // 무료 티어에서 쿠팡 변환이 느리거나 실패하는 일이 정상 범위에 있다.
    getShoppingLinks(recipeId, userId, controller.signal)
      .then(setLinks)
      .catch(() => {})
    return () => controller.abort()
  }, [recipeId, userId])

  if (!isAuthenticated) {
    return (
      <section className={styles.card} aria-labelledby="missing-heading">
        <h2 id="missing-heading">지금 만들 수 있나요?</h2>
        <p className={styles.guide}>
          로그인하고 냉장고에 재료를 넣으면 무엇이 부족한지 알려드려요.
        </p>
      </section>
    )
  }

  if (failed || data === null) return null

  const { coverage, missing_ingredients: missing } = data

  return (
    <section className={styles.card} aria-labelledby="missing-heading">
      <div className={styles.head}>
        <h2 id="missing-heading">지금 만들 수 있나요?</h2>
        {coverage.coverage_pct !== null && (
          <span className={styles.pct}>재료 {coverage.coverage_pct}% 보유</span>
        )}
      </div>

      {missing.length === 0 ? (
        <p className={styles.ready}>
          <span aria-hidden="true">✅</span> 필요한 재료가 냉장고에 다 있어요.
        </p>
      ) : (
        <>
          <p className={styles.summary}>
            {coverage.total}개 중 <strong>{missing.length}개</strong>가 없어요.
          </p>
          <ul className={styles.list}>
            {missing.map((item) => {
              // links.links를 그냥 믿지 않는다. 응답 모양이 예상과 다르면 부족한 재료
              // 목록 전체가 안 보이게 되는데, 구매 버튼 하나 때문에 그러면 안 된다.
              // (홈 화면이 영상 분류 때문에 통째로 빈 화면이 됐던 것과 같은 종류다.)
              const buy = Array.isArray(links?.links)
                ? links.links.find((l) => l?.ingredient === item.ingredient)
                : undefined
              return (
                <li key={item.ingredient} className={styles[item.type] ?? styles.unknown}>
                  <span className={styles.name}>{item.ingredient}</span>
                  <span className={styles.suggestion}>{item.suggestion}</span>
                  {buy && (
                    <span className={styles.buy}>
                      {/* 외부 사이트로 나간다. noreferrer까지 붙이는 이유는 어느 화면에서
                          왔는지를 상대 사이트에 넘기지 않기 위해서다. */}
                      <a href={buy.coupang} target="_blank" rel="noopener noreferrer">
                        쿠팡<span className="sr-only">에서 {item.ingredient} 검색</span>
                      </a>
                      <a href={buy.naver} target="_blank" rel="noopener noreferrer">
                        네이버<span className="sr-only">에서 {item.ingredient} 검색</span>
                      </a>
                    </span>
                  )}
                </li>
              )
            })}
          </ul>
          {disclosure(links) && <p className={styles.disclosure}>{disclosure(links)}</p>}
        </>
      )}

      {/* 안 적으면 "추천 화면에서 뺐는데 왜 아직 있지"가 된다. */}
      <p className={styles.basis}>
        냉장고에 저장된 재료 기준이에요. <Link to="/pantry">냉장고 고치기</Link>
      </p>
    </section>
  )
}
