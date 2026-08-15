import { Link } from 'react-router-dom'

import { toHttps } from '../api/client'
import styles from './RecipeCard.module.css'

/**
 * 카드가 필요로 하는 최소한의 모양.
 *
 * 목록(RecipeSummary)과 추천(RecommendationItem)이 둘 다 이 필드를 갖고 있어서, 카드를
 * 하나로 쓴다. 추천 쪽에만 있는 정보(재료 활용 개수 등)는 badge로 받는다.
 */
export type CardRecipe = {
  id: number
  menu_name: string
  category: string | null
  calorie: number | null
  image_url: string | null
}

export type CardBadge = { text: string; tone: 'good' | 'weak' | 'poor' }

/**
 * 레시피 카드. 카드 전체가 상세로 가는 링크다.
 *
 * 1:1 정사각인 이유: 레시피 사진이 전부 320x320이다. 와이드로 늘리면 2배 화면에서
 * 흐려지고, 2열 격자의 정사각이면 화면 픽셀과 거의 1:1로 맞는다.
 */
export default function RecipeCard({
  recipe,
  badge,
}: {
  recipe: CardRecipe
  badge?: CardBadge
}) {
  // image_url은 string | null이다. 1,148개 중 2개가 실제로 비어 있어서, 개발 중에는
  // 거의 안 걸리고 실사용에서만 터진다. 타입이 여기서 처리를 강제한다.
  const imageUrl = toHttps(recipe.image_url)

  return (
    <Link className={styles.card} to={`/recipe/${recipe.id}`}>
      <div className={styles.media}>
        {imageUrl === null ? (
          <div className={styles.placeholder} aria-hidden="true">
            🍽️
          </div>
        ) : (
          <img src={imageUrl} alt="" loading="lazy" />
        )}
      </div>
      <div className={styles.body}>
        {badge && <span className={`${styles.badge} ${styles[badge.tone]}`}>{badge.text}</span>}
        <p className={styles.title}>{recipe.menu_name}</p>
        <p className={styles.meta}>{describeMeta(recipe)}</p>
      </div>
    </Link>
  )
}

function describeMeta(recipe: CardRecipe): string {
  const parts: string[] = []
  if (recipe.category) parts.push(recipe.category)
  // calorie도 null일 수 있다. 0을 "0 kcal"로 보여주면 잘못된 정보가 되므로 값이 있을 때만 쓴다.
  if (recipe.calorie !== null) parts.push(`${Math.round(recipe.calorie)} kcal`)
  return parts.join(' · ')
}
