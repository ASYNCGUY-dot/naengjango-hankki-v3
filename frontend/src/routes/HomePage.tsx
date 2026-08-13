import { useCallback, useEffect, useRef, useState } from 'react'

import { ApiError, TimeoutError } from '../api/client'
import {
  ALL_CATEGORIES,
  PAGE_SIZE,
  listCategories,
  searchRecipes,
  type CategoryCount,
  type RecipeSummary,
} from '../api/recipes'
import RecipeCard from '../components/RecipeCard'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './HomePage.module.css'

/** 입력할 때마다 요청하면 콜드스타트가 있는 서버에 과하다. 잠깐 멈추면 그때 보낸다. */
const SEARCH_DEBOUNCE_MS = 400

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '레시피를 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
}

/**
 * 홈 = 레시피 둘러보기.
 *
 * 시안에는 "인기 레시피"였는데 바꿨다. 인기 순위는 좋아요를 기준으로 하는데 지금 DB에
 * 좋아요가 4개뿐이고 그마저 개발자 본인이 누른 것이라, 그 섹션은 카드 4장으로 끝난다.
 * 1,148개를 분류로 훑어보는 쪽이 지금 데이터로 성립한다. 좋아요가 쌓이면 그때 되살린다.
 */
export default function HomePage() {
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState(ALL_CATEGORIES)
  const [categories, setCategories] = useState<CategoryCount[]>([])
  const [recipes, setRecipes] = useState<RecipeSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const isSlow = useSlowRequestHint(isLoading)

  // 검색어를 바꾸는 동안 이전 요청이 늦게 도착해 새 결과를 덮어쓰는 것을 막는다.
  const requestRef = useRef(0)

  const load = useCallback(async (nextKeyword: string, nextCategory: string) => {
    const requestId = ++requestRef.current
    setIsLoading(true)
    setError(null)
    try {
      const items = await searchRecipes({ keyword: nextKeyword, category: nextCategory })
      if (requestRef.current !== requestId) return
      setRecipes(items)
      setHasMore(items.length === PAGE_SIZE)
    } catch (caught) {
      if (requestRef.current !== requestId) return
      setError(describe(caught))
      setRecipes([])
      setHasMore(false)
    } finally {
      if (requestRef.current === requestId) setIsLoading(false)
    }
  }, [])

  // 분류 칩은 한 번만 받아오면 된다.
  useEffect(() => {
    const controller = new AbortController()
    listCategories(controller.signal)
      .then(setCategories)
      // 칩을 못 받아도 목록은 볼 수 있어야 한다. 조용히 넘어간다.
      .catch(() => {})
    return () => controller.abort()
  }, [])

  useEffect(() => {
    const timer = setTimeout(() => void load(keyword, category), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [keyword, category, load])

  async function loadMore() {
    setIsLoadingMore(true)
    try {
      const items = await searchRecipes({ keyword, category, offset: recipes.length })
      setRecipes((prev) => [...prev, ...items])
      setHasMore(items.length === PAGE_SIZE)
    } catch (caught) {
      setError(describe(caught))
    } finally {
      setIsLoadingMore(false)
    }
  }

  return (
    <>
      <header className={styles.appbar}>
        <h1>오늘 뭐 먹지?</h1>
      </header>

      <div className={styles.search}>
        <span aria-hidden="true">🔍</span>
        <label className="sr-only" htmlFor="home-search">
          레시피 검색
        </label>
        <input
          id="home-search"
          type="search"
          placeholder="레시피 이름으로 찾기"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
        />
      </div>

      <ul className={styles.chips}>
        {[{ category: ALL_CATEGORIES, count: 0 }, ...categories].map((item) => (
          <li key={item.category}>
            <button
              type="button"
              className={
                item.category === category ? `${styles.chip} ${styles.chipSelected}` : styles.chip
              }
              aria-pressed={item.category === category}
              onClick={() => setCategory(item.category)}
            >
              {item.category}
            </button>
          </li>
        ))}
      </ul>

      {isSlow && (
        <p className={styles.notice} role="status">
          <span aria-hidden="true">☕</span>
          <span>
            서버를 깨우는 중이에요
            <small>무료 서버라 첫 요청은 30초쯤 걸려요. 조금만 기다려주세요.</small>
          </span>
        </p>
      )}

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <div className={styles.sectionHead}>
        <h2>레시피 둘러보기</h2>
        {!isLoading && recipes.length > 0 && <span>{recipes.length}개 보는 중</span>}
      </div>

      {isLoading ? (
        <ul className={styles.grid} aria-hidden="true">
          {Array.from({ length: 4 }, (_, index) => (
            <li key={index} className={styles.skeleton} />
          ))}
        </ul>
      ) : recipes.length === 0 && error === null ? (
        <p className={styles.empty}>
          조건에 맞는 레시피가 없어요.
          <br />
          검색어나 분류를 바꿔보세요.
        </p>
      ) : (
        <ul className={styles.grid}>
          {recipes.map((recipe) => (
            <li key={recipe.id}>
              <RecipeCard recipe={recipe} />
            </li>
          ))}
        </ul>
      )}

      {hasMore && !isLoading && (
        <button className={styles.more} type="button" onClick={loadMore} disabled={isLoadingMore}>
          {isLoadingMore ? '불러오는 중…' : '더 보기'}
        </button>
      )}
    </>
  )
}
