import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import { ApiError, TimeoutError, toHttps } from '../api/client'
import {
  describeAmount,
  getRecipe,
  groupIngredients,
  parseNutrients,
  parseSteps,
  type RecipeDetail,
} from '../api/recipeDetail'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './RecipeDetailPage.module.css'

/**
 * 레시피 상세.
 *
 * V2에서는 이 화면이 URL을 갖지 못해 링크로 공유할 수 없었다. 그래서 인가 없이도
 * 온전히 보이는 것이 중요하다 - 링크를 받은 사람은 대개 로그인돼 있지 않다.
 * 재료 목록도 그래서 이 응답에 함께 담게 했다(api/routers/recommendation.py 참고).
 */
export default function RecipeDetailPage() {
  const { recipeId } = useParams<{ recipeId: string }>()
  const navigate = useNavigate()

  const [recipe, setRecipe] = useState<RecipeDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const isSlow = useSlowRequestHint(isLoading)

  const parsedId = Number(recipeId)

  useEffect(() => {
    if (!Number.isInteger(parsedId)) {
      setNotFound(true)
      setIsLoading(false)
      return
    }

    const controller = new AbortController()
    setIsLoading(true)
    setError(null)
    setNotFound(false)

    getRecipe(parsedId, controller.signal)
      .then(setRecipe)
      .catch((caught: unknown) => {
        if (controller.signal.aborted) return
        if (caught instanceof ApiError && caught.status === 404) {
          setNotFound(true)
        } else if (caught instanceof ApiError || caught instanceof TimeoutError) {
          setError(caught.message)
        } else {
          setError('레시피를 불러오지 못했어요. 잠시 후 다시 시도해주세요.')
        }
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false)
      })

    return () => controller.abort()
  }, [parsedId])

  if (notFound) {
    return (
      <div className={styles.missing}>
        <h1>레시피를 찾을 수 없어요</h1>
        <p>주소가 잘못됐거나 삭제된 레시피예요.</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <>
        <div className={styles.skeletonHero} aria-hidden="true" />
        <div className={styles.skeletonLine} aria-hidden="true" />
        <div className={styles.skeletonLine} aria-hidden="true" />
        {isSlow && (
          <p className={styles.notice} role="status">
            <span aria-hidden="true">☕</span>
            <span>
              서버를 깨우는 중이에요
              <small>무료 서버라 첫 요청은 30초쯤 걸려요.</small>
            </span>
          </p>
        )}
      </>
    )
  }

  if (error !== null || recipe === null) {
    return (
      <p className={styles.error} role="alert">
        {error ?? '레시피를 불러오지 못했어요.'}
      </p>
    )
  }

  const imageUrl = toHttps(recipe.image_url)
  const nutrients = parseNutrients(recipe.nutrients_json)
  const steps = parseSteps(recipe.steps_json)
  const groups = groupIngredients(recipe.ingredients ?? [])
  const youtubeUrl = toHttps(recipe.youtube_url)

  return (
    <>
      <div className={styles.hero}>
        {imageUrl === null ? (
          <div className={styles.placeholder} aria-hidden="true">
            🍽️
          </div>
        ) : (
          <img src={imageUrl} alt={`${recipe.menu_name} 완성 사진`} />
        )}
        <button className={styles.back} type="button" aria-label="뒤로" onClick={() => navigate(-1)}>
          ←
        </button>
      </div>

      <div className={styles.head}>
        <h1>{recipe.menu_name}</h1>
        <div className={styles.badges}>
          {recipe.category && <span className={styles.badge}>{recipe.category}</span>}
          {recipe.cook_method && <span className={styles.badge}>{recipe.cook_method}</span>}
          {recipe.nutrition_group && <span className={styles.badge}>{recipe.nutrition_group}</span>}
        </div>
      </div>

      {/* 이름을 주면 화면 낭독기가 "영양 정보 목록"으로 읽어준다. 화면에는 제목이
          없어서 이 목록이 무엇인지 소리로는 알 수 없다. */}
      <ul className={styles.nutrients} aria-label="영양 정보">
        <NutrientTile label="열량" value={nutrients.energy_kcal ?? recipe.calorie} unit="kcal" />
        <NutrientTile label="탄수화물" value={nutrients.carbs_g} unit="g" />
        <NutrientTile label="단백질" value={nutrients.protein_g} unit="g" />
        <NutrientTile label="나트륨" value={nutrients.sodium_mg} unit="mg" />
      </ul>

      <div className={styles.sectionHead}>
        <h2>재료</h2>
        {recipe.base_servings ? <span>{recipe.base_servings}인분 기준</span> : null}
      </div>

      {groups.length === 0 ? (
        <p className={styles.group}>등록된 재료 정보가 없어요.</p>
      ) : (
        groups.map((group, index) => (
          <div className={styles.group} key={group.title ?? index}>
            {/* 원본 데이터에 "주재료"·"장식" 같은 구획 제목이 재료처럼 섞여 있다.
                그대로 나열하면 "주재료 —"가 재료 하나로 보인다. */}
            {group.title && <h3>{group.title}</h3>}
            <ul className={styles.ingredients}>
              {group.items.map((item, itemIndex) => (
                <li key={`${item.name}-${itemIndex}`}>
                  <span>{item.name}</span>
                  <span className={styles.amount}>{describeAmount(item)}</span>
                </li>
              ))}
            </ul>
          </div>
        ))
      )}

      <div className={styles.sectionHead}>
        <h2>조리 순서</h2>
        {steps.length > 0 && <span>{steps.length}단계</span>}
      </div>

      {steps.length === 0 ? (
        <p className={styles.group}>등록된 조리 순서가 없어요.</p>
      ) : (
        <ol className={styles.steps}>
          {steps.map((step, index) => (
            <li key={index}>
              <span className={styles.stepNumber}>{index + 1}</span>
              <div className={styles.stepBody}>
                {/* 원본 텍스트에 이미 번호가 붙어 있어서 parseSteps가 떼어냈다.
                    안 떼면 "1. 1. …"이 된다. */}
                <p>{step.text}</p>
                {step.image && <img src={toHttps(step.image) ?? ''} alt="" loading="lazy" />}
              </div>
            </li>
          ))}
        </ol>
      )}

      {youtubeUrl && (
        <div className={styles.actions}>
          <a
            className={styles.linkButton}
            href={youtubeUrl}
            target="_blank"
            rel="noreferrer noopener"
          >
            <span aria-hidden="true">▶</span> 유튜브에서 영상 보기
          </a>
        </div>
      )}
    </>
  )
}

function NutrientTile({
  label,
  value,
  unit,
}: {
  label: string
  value: number | null
  unit: string
}) {
  return (
    <li>
      <dl>
        {/* 단위는 라벨에 둔다. 타일이 좁아서 값 옆에 붙이면 두 줄로 넘어간다. */}
        <dt>
          {label} ({unit})
        </dt>
        {/* 값이 없으면 0이 아니라 "-"다. 0으로 보여주면 잘못된 정보가 된다. */}
        <dd>{value === null ? '-' : Math.round(value * 10) / 10}</dd>
      </dl>
    </li>
  )
}
