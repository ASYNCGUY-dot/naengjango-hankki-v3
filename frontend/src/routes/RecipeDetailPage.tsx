import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import { ApiError, TimeoutError, toHttps } from '../api/client'
import FavoriteButton from '../components/FavoriteButton'
import MissingIngredientsCard from '../components/MissingIngredientsCard'
import NutritionFitCard from '../components/NutritionFitCard'
import RecipeCostCard from '../components/RecipeCostCard'
import RecommendButton from '../components/RecommendButton'
import ReviewSection from '../components/ReviewSection'
import { useAuth } from '../auth/context'
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
  const { isAuthenticated } = useAuth()

  const [recipe, setRecipe] = useState<RecipeDetail | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const restoreRetryFocus = useRef(false)
  const headingRef = useRef<HTMLHeadingElement>(null)
  const retryButtonRef = useRef<HTMLButtonElement>(null)
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
  }, [parsedId, attempt])

  useEffect(() => {
    // 재시도 버튼이 로딩 화면으로 바뀌어 사라진 경우에만 초점을 복구한다.
    // 기다리는 동안 사용자가 다른 곳으로 이동하면 그 선택을 유지한다.
    const cancel = () => { restoreRetryFocus.current = false }
    const cancelOnFocus = (event: FocusEvent) => {
      if (event.target !== document.body) cancel()
    }
    document.addEventListener('focusin', cancelOnFocus)
    document.addEventListener('pointerdown', cancel)
    document.addEventListener('keydown', cancel)
    document.addEventListener('wheel', cancel, { passive: true })
    return () => {
      document.removeEventListener('focusin', cancelOnFocus)
      document.removeEventListener('pointerdown', cancel)
      document.removeEventListener('keydown', cancel)
      document.removeEventListener('wheel', cancel)
    }
  }, [])

  useEffect(() => {
    if (isLoading || !restoreRetryFocus.current) return
    restoreRetryFocus.current = false
    const target = headingRef.current ?? retryButtonRef.current
    target?.focus({ preventScroll: true })
  }, [isLoading, recipe, error, notFound])

  if (notFound) {
    return (
      <div className={styles.missing}>
        <h1 ref={headingRef} tabIndex={-1}>레시피를 찾을 수 없어요</h1>
        <p>주소가 잘못됐거나 삭제된 레시피예요.</p>
      </div>
    )
  }

  if (isLoading) {
    return (
      <>
        <p className="sr-only" role="status">레시피를 불러오는 중이에요.</p>
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
      <div className={styles.error} role="alert">
        <p>{error ?? '레시피를 불러오지 못했어요.'}</p>
        <button ref={retryButtonRef} type="button" className={styles.linkButton} onClick={() => {
          restoreRetryFocus.current = true
          setAttempt((value) => value + 1)
        }}>다시 불러오기</button>
      </div>
    )
  }

  const imageUrl = toHttps(recipe.image_url)
  const nutrients = parseNutrients(recipe.nutrients_json)
  const steps = parseSteps(recipe.steps_json)
  const groups = groupIngredients(recipe.ingredients ?? [])
  const youtubeUrl = toHttps(recipe.youtube_url)

  return (
    <article className={styles.page}>
      <div className={styles.summary}>
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

      <div className={styles.overview}>
      <div className={styles.head}>
        <h1 ref={headingRef} tabIndex={-1}>{recipe.menu_name}</h1>
        <div className={styles.badges}>
          {recipe.category && <span className={styles.badge}>{recipe.category}</span>}
          {recipe.cook_method && <span className={styles.badge}>{recipe.cook_method}</span>}
          {recipe.nutrition_group && <span className={styles.badge}>{recipe.nutrition_group}</span>}
        </div>
      </div>

      {/* 공모전에서 시세 활용을 바로 확인할 수 있도록 메뉴 소개에 재료비를 붙인다. */}
      <RecipeCostCard recipeId={recipe.id} />

      {/* 메뉴 소개와 재료비를 확인한 뒤 추천하거나 즐겨찾기에 담을 수 있다.
          둘을 나란히 놓는 이유는 서로 다른 행동이기 때문이다 - 추천은 남에게 보이는
          공개 지표이고, 즐겨찾기는 내가 다시 보려고 담는 것이다. 하나만 두면 사용자는
          자기가 무엇을 한 건지 모른다. */}
      <div className={styles.reactions}>
        <RecommendButton recipeId={recipe.id} />
        <FavoriteButton recipeId={recipe.id} />
      </div>
      <nav className={styles.jumpLinks} aria-label="레시피 바로가기">
        {[['cost', '재료비'], ['ingredients', '재료'], ['steps', '조리 순서'], ['nutrition', '영양'], ['reviews', '후기']].map(([id, label]) => (
          <a key={id} href={`#recipe-${id}`} onClick={(event) => {
            event.preventDefault()
            const target = document.getElementById(`recipe-${id}`)
            target?.focus({ preventScroll: true })
            target?.scrollIntoView({ block: 'start', behavior: 'instant' })
          }}>{label}</a>
        ))}
      </nav>
      <a className={styles.startCooking} href="#recipe-steps" onClick={(event) => {
        event.preventDefault()
        const target = document.getElementById('recipe-steps')
        target?.focus({ preventScroll: true })
        target?.scrollIntoView({ block: 'start', behavior: 'instant' })
      }}>조리 시작하기 <span aria-hidden="true">↓</span></a>
      </div>
      </div>

      {/* 이름을 주면 화면 낭독기가 "영양 정보 목록"으로 읽어준다. 화면에는 제목이
          없어서 이 목록이 무엇인지 소리로는 알 수 없다. */}
      <h2 className={styles.nutritionHeading} id="recipe-nutrition" tabIndex={-1}>영양 정보</h2>
      <ul className={styles.nutrients} aria-label="영양 정보">
        <NutrientTile label="열량" value={nutrients.energy_kcal ?? recipe.calorie} unit="kcal" />
        <NutrientTile label="탄수화물" value={nutrients.carbs_g} unit="g" />
        <NutrientTile label="단백질" value={nutrients.protein_g} unit="g" />
        <NutrientTile label="나트륨" value={nutrients.sodium_mg} unit="mg" />
      </ul>

      {/* 온보딩에서 받은 성별·연령·병력·영양제가 실제로 쓰이는 자리다. 영양 정보 타일
          바로 아래에 둔다 - 같은 주제를 두 번에 나눠 보여주는 셈이라 붙어 있어야 한다. */}
      <NutritionFitCard recipeId={recipe.id} />

      {/* 재료 목록 바로 위에 둔다. "무엇이 필요한가" 다음에 오는 질문이 "그중 뭐가
          없는가"이므로 목록을 보기 전에 답을 주는 편이 낫다. */}
      <MissingIngredientsCard recipeId={recipe.id} />

      <div className={styles.sectionHead}>
        <h2 id="recipe-ingredients" tabIndex={-1}>재료</h2>
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
        <h2 id="recipe-steps" tabIndex={-1}>조리 순서</h2>
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

      {/* 조리 순서를 다 본 직후가 "만들었다"에 가장 가까운 자리다. 자랑하기 탭에서
          레시피를 다시 검색해 고르는 것보다, 지금 보고 있는 이 화면에서 바로 올리는
          쪽이 실제 흐름이다. */}
      {isAuthenticated && (
        <div className={styles.actions}>
          <Link className={styles.linkButton} to={`/brags/new?recipe=${recipe.id}`}>
            <span aria-hidden="true">📸</span> 이거 만들었어요
          </Link>
        </div>
      )}

      {/* 조리 순서 다음에 둔다. "만들었다"가 후기의 전제라 순서를 다 본 뒤가 자연스럽고,
          아직 안 만든 사람에게는 다른 사람이 해본 결과가 마지막 판단 재료가 된다. */}
      <div id="recipe-reviews" tabIndex={-1} role="region" aria-label="후기"><ReviewSection recipeId={recipe.id} /></div>

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
    </article>
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
