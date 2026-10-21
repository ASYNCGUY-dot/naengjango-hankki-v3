import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'

import { getThemeRecipes, PAGE_SIZE, type RecipeTheme, type ThemeKey } from '../api/recipes'
import RecipeCard from '../components/RecipeCard'
import Icon from '../components/아이콘'
import { useDeferredFocus } from '../hooks/비동기초점'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './테마목록.module.css'

const THEME_KEYS = ['seasonal', 'simple', 'light', 'hearty'] as const satisfies readonly ThemeKey[]
const previousLists = new Map<string, { data: RecipeTheme; savedAt: number }>()
const CACHE_LIFETIME = 5 * 60 * 1000

function readPreviousList(key: string) {
  const saved = previousLists.get(key)
  return saved && Date.now() - saved.savedAt < CACHE_LIFETIME ? saved.data : null
}

function rememberList(key: string, data: RecipeTheme) {
  previousLists.delete(key)
  previousLists.set(key, { data, savedAt: Date.now() })
  // 뒤로가기용 메모리만 사용한다. 새 방문에 오래된 결과를 영구 저장하지 않는다.
  while (previousLists.size > 12) previousLists.delete(previousLists.keys().next().value!)
}

function isThemeKey(value: string | undefined): value is ThemeKey {
  return THEME_KEYS.some((key) => key === value)
}

function HomeLink() {
  return <Link className={styles.back} to="/"><Icon name="arrow-left" size={20} />홈으로</Link>
}

export default function ThemeRecipesPage() {
  const { themeKey } = useParams()
  const [params] = useSearchParams()
  const [entryMonth] = useState(() => new Date().getMonth() + 1)
  const monthText = params.get('month')
  const month = monthText === null ? entryMonth : Number(monthText)
  const location = useLocation()

  if (!isThemeKey(themeKey) || !Number.isInteger(month) || month < 1 || month > 12) {
    return <div className={styles.page}>
      <HomeLink />
      <h1 className={styles.title}>테마를 찾을 수 없어요</h1>
      <p className={styles.empty}>홈에서 보고 싶은 테마를 다시 선택해주세요.</p>
    </div>
  }

  const cacheKey = `${location.key}:${themeKey}:${month}`
  return <ThemeList key={cacheKey} theme={themeKey} month={month} cacheKey={cacheKey} />
}

function ThemeList({ theme, month, cacheKey }: { theme: ThemeKey; month: number; cacheKey: string }) {
  const [data, setData] = useState(() => readPreviousList(cacheKey))
  const [pending, setPending] = useState(() => !readPreviousList(cacheKey))
  const [error, setError] = useState<string | null>(null)
  const [retried, setRetried] = useState(false)
  const dataRef = useRef(data)
  const busy = useRef(false)
  const request = useRef(0)
  const controller = useRef<AbortController | null>(null)
  const heading = useRef<HTMLHeadingElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const moreButton = useRef<HTMLButtonElement>(null)
  const pendingFocus = useRef<{ index: number; allowed: () => boolean } | null>(null)
  const { capture } = useDeferredFocus()
  const isSlow = useSlowRequestHint(pending)

  const load = useCallback(async (interactive = false) => {
    if (busy.current) return
    busy.current = true
    const requestId = ++request.current
    const currentController = new AbortController()
    controller.current = currentController
    const previous = dataRef.current
    const offset = previous?.recipes.length ?? 0
    const restoreFocus = interactive && document.activeElement === moreButton.current ? capture() : null
    if (interactive) setRetried(true)
    setPending(true)
    setError(null)
    try {
      const next = await getThemeRecipes({ theme, month, offset, signal: currentController.signal })
      if (currentController.signal.aborted || request.current !== requestId) return
      const existingIds = new Set(previous?.recipes.map((recipe) => recipe.id))
      if (next.recipes.some((recipe) => existingIds.has(recipe.id)) || next.total < offset) {
        throw new Error('다음 레시피를 확인할 수 없어요. 잠시 후 다시 불러와주세요.')
      }
      const combined = { ...next, recipes: [...previous?.recipes ?? [], ...next.recipes] }
      dataRef.current = combined
      rememberList(cacheKey, combined)
      if (restoreFocus) pendingFocus.current = { index: previous ? offset : -1, allowed: restoreFocus }
      setData(combined)
    } catch (caught) {
      if (currentController.signal.aborted || request.current !== requestId) return
      setError(caught instanceof Error && !(caught instanceof TypeError)
        ? caught.message : '레시피를 불러오지 못했어요. 다시 시도해주세요.')
    } finally {
      if (!currentController.signal.aborted && request.current === requestId) {
        busy.current = false
        setPending(false)
      }
    }
  }, [theme, month, cacheKey, capture])

  useEffect(() => {
    if (!dataRef.current) void load()
    return () => {
      controller.current?.abort()
      request.current += 1
      busy.current = false
    }
  }, [load])

  useLayoutEffect(() => {
    const target = pendingFocus.current
    pendingFocus.current = null
    if (!target?.allowed()) return
    const firstNewRecipe = target.index >= 0
      ? list.current?.children[target.index]?.querySelector<HTMLAnchorElement>('a')
      : null
    ;(firstNewRecipe ?? heading.current)?.focus({ preventScroll: true })
  }, [data])

  const shown = data?.recipes.length ?? 0
  const remaining = data ? Math.max(0, data.total - shown) : 0
  const hasMore = remaining > 0
  const showAction = hasMore || (!data && (error !== null || retried))

  return <div className={styles.page}>
    <HomeLink />
    <header className={styles.header}>
      <p className={styles.eyebrow}>테마별 레시피</p>
      <h1 ref={heading} tabIndex={-1} className={styles.title}>{data?.title ?? '테마 레시피'}</h1>
      {data?.subtitle && <p className={styles.subtitle}>{data.subtitle}</p>}
      {data && <p className={styles.count}>전체 {data.total}개 중 {shown}개</p>}
    </header>

    <p className={pending ? styles.status : 'sr-only'} role="status" aria-atomic="true">
      {pending
        ? isSlow ? '서버를 깨우는 중이에요. 잠시만 기다려주세요.' : '레시피를 불러오는 중이에요.'
        : data ? `${shown}개의 레시피를 표시했어요.` : ''}
    </p>

    {data && shown > 0 && <ul ref={list} className={styles.grid} aria-label="레시피 목록" aria-busy={pending}>
      {data.recipes.map((recipe) => <li key={recipe.id}><RecipeCard recipe={recipe} /></li>)}
    </ul>}
    {data && data.total === 0 && <p className={styles.empty}>이 테마에 해당하는 레시피가 아직 없어요.</p>}

    <div className={styles.footer}>
      {error && <p className={styles.error} role="alert">{error}</p>}
      {showAction && <button ref={moreButton} type="button" className={styles.more}
        aria-disabled={pending} onClick={() => { if (!busy.current) void load(true) }}>
        {pending ? '불러오는 중…' : error ? '다시 불러오기' : `${Math.min(PAGE_SIZE, remaining)}개 더 보기`}
      </button>}
      {data && shown > 0 && !hasMore && <p className={styles.end}>모든 레시피를 확인했어요.</p>}
    </div>
  </div>
}
