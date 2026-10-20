import { useCallback, useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { Link } from 'react-router-dom'

import { ApiError, TimeoutError, toHttps } from '../api/client'
import { listPopularRecipes, type PopularRecipeItem } from '../api/likes'
import { listPopularVideos, listVideoCategories, type PopularVideo } from '../api/videos'
import {
  ALL_CATEGORIES, PAGE_SIZE, listCategories, listThemes, searchRecipes,
  type CategoryCount, type RecipeSummary, type RecipeTheme,
} from '../api/recipes'
import RecipeCard from '../components/RecipeCard'
import Icon from '../components/아이콘'
import HomeFeed from '../components/집밥피드'
import { useSlowRequestHint } from '../hooks/useSlowRequestHint'
import styles from './HomePage.module.css'

const SEARCH_DEBOUNCE_MS = 400
const VIEWS = [
  { id: 'recipes', label: '추천' },
  { id: 'videos', label: '요리 영상' },
  { id: 'brags', label: '한 끼 자랑' },
] as const
type View = typeof VIEWS[number]['id']

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '레시피를 불러오지 못했어요. 잠시 후 다시 시도해주세요.'
}

/** 기존 검색·추천·영상·자랑 API를 탭으로 나눠 보여주는 집밥 피드. */
export default function HomePage() {
  const [view, setView] = useState<View>('recipes')
  const [keyword, setKeyword] = useState('')
  const [category, setCategory] = useState(ALL_CATEGORIES)
  const [categories, setCategories] = useState<CategoryCount[]>([])
  const [themes, setThemes] = useState<RecipeTheme[]>([])
  // 월이 바뀌어도 홈에서 본 제철과 전체보기의 조회 조건을 같게 유지한다.
  const [themeMonth] = useState(() => new Date().getMonth() + 1)
  const [popular, setPopular] = useState<PopularRecipeItem[]>([])
  const [videos, setVideos] = useState<PopularVideo[]>([])
  const [videoCategory, setVideoCategory] = useState<string | null>(null)
  const [videoCategories, setVideoCategories] = useState<string[]>([])
  const [videoLoading, setVideoLoading] = useState(true)
  const [videoError, setVideoError] = useState<string | null>(null)
  const [recipes, setRecipes] = useState<RecipeSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingMore, setIsLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryAttempt, setRetryAttempt] = useState(0)
  const isSlow = useSlowRequestHint(view === 'videos' ? videoLoading : isLoading)
  const requestRef = useRef(0)
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([])

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

  useEffect(() => {
    const controller = new AbortController()
    listCategories(controller.signal).then(setCategories).catch(() => {})
    listThemes(controller.signal, themeMonth)
      .then((rows) => setThemes(rows.filter((row) => Array.isArray(row?.recipes))))
      .catch(() => {})
    listPopularRecipes(10, controller.signal).then(setPopular).catch(() => {})
    listVideoCategories(controller.signal)
      .then((rows) => {
        if (controller.signal.aborted) return
        const names = Array.isArray(rows) ? rows.filter((row) => typeof row === 'string') : []
        setVideoCategories(names)
        if (names.length > 0) {
          setVideoCategory((current) => current !== null && names.includes(current) ? current : names[0])
        }
        else setVideoLoading(false)
      })
      .catch(() => {
        if (controller.signal.aborted) return
        setVideoError('요리 영상을 불러오지 못했어요. 잠시 후 다시 방문해주세요.')
        setVideoLoading(false)
      })
    return () => controller.abort()
  }, [retryAttempt, themeMonth])

  useEffect(() => {
    if (videoCategory === null) return
    const controller = new AbortController()
    setVideoLoading(true)
    setVideoError(null)
    setVideos([])
    listPopularVideos(videoCategory, 10, controller.signal)
      .then((rows) => {
        if (!controller.signal.aborted) {
          setVideos(Array.isArray(rows) ? rows.filter((row) => typeof row?.video_id === 'string') : [])
        }
      })
      .catch(() => {
        if (!controller.signal.aborted) setVideoError('요리 영상을 불러오지 못했어요. 다른 분류를 선택해주세요.')
      })
      .finally(() => { if (!controller.signal.aborted) setVideoLoading(false) })
    return () => controller.abort()
  }, [videoCategory, retryAttempt])

  useEffect(() => {
    const timer = setTimeout(() => void load(keyword, category), SEARCH_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [keyword, category, load])

  async function loadMore() {
    const requestId = requestRef.current
    setIsLoadingMore(true)
    try {
      const items = await searchRecipes({ keyword, category, offset: recipes.length })
      if (requestId !== requestRef.current) return
      setRecipes((prev) => [...prev, ...items])
      setHasMore(items.length === PAGE_SIZE)
    } catch (caught) {
      if (requestId === requestRef.current) setError(describe(caught))
    } finally {
      setIsLoadingMore(false)
    }
  }

  function changeKeyword(value: string) {
    ++requestRef.current
    setKeyword(value)
    setView('recipes')
  }

  function navigateTabs(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = event.key === 'ArrowRight' ? (index + 1) % VIEWS.length
      : event.key === 'ArrowLeft' ? (index + VIEWS.length - 1) % VIEWS.length
      : event.key === 'Home' ? 0 : event.key === 'End' ? VIEWS.length - 1 : null
    if (next === null) return
    event.preventDefault()
    setView(VIEWS[next].id)
    tabRefs.current[next]?.focus()
  }

  const isBrowsing = keyword.trim() === '' && category === ALL_CATEGORIES

  return (
    <div className={styles.page}>
      <header className={styles.appbar}>
        <h1>냉장고 한끼<span className={styles.brandDot} aria-hidden="true">.</span></h1>
        <div className={styles.headerActions}>
          <Link to="/brags/new" className={styles.iconButton} aria-label="집밥 올리기"><Icon name="plus" /></Link>
        </div>
      </header>

      <div className={styles.search}>
        <Icon name="search" size={21} />
        <label className="sr-only" htmlFor="home-search">레시피 검색</label>
        <input id="home-search" type="search" placeholder="오늘은 어떤 요리를 찾으세요?" value={keyword} onChange={(event) => changeKeyword(event.target.value)} />
      </div>

      <div className={styles.tabs} role="tablist" aria-label="둘러보기">
        {VIEWS.map((item, index) => (
          <button key={item.id} type="button" role="tab" id={`home-tab-${item.id}`} aria-controls={`home-panel-${item.id}`} aria-selected={view === item.id} tabIndex={view === item.id ? 0 : -1} ref={(node) => { tabRefs.current[index] = node }} className={view === item.id ? styles.selectedTab : styles.tab} onClick={() => setView(item.id)} onKeyDown={(event) => navigateTabs(event, index)}>{item.label}</button>
        ))}
      </div>

      {view === 'brags' && <section role="tabpanel" id="home-panel-brags" aria-labelledby="home-tab-brags" className={styles.feedPanel}><HomeFeed /></section>}

      {view === 'videos' && (
        <section role="tabpanel" id="home-panel-videos" aria-labelledby="home-tab-videos" className={styles.panel}>
          <div className={styles.sectionHead}><div><p className={styles.eyebrow}>보고 따라 만드는 한 끼</p><h2>인기 요리 영상</h2></div><Icon name="play" size={24} /></div>
          <ul className={styles.chips}>
            {videoCategories.map((item) => <li key={item}><button type="button" className={videoCategory === item ? `${styles.chip} ${styles.chipSelected}` : styles.chip} aria-pressed={videoCategory === item} onClick={() => setVideoCategory(item)}>{item}</button></li>)}
          </ul>
          {videoError && <div className={styles.error} role="alert"><p>{videoError}</p><button className={styles.retry} type="button" onClick={() => setRetryAttempt((value) => value + 1)}>다시 불러오기</button></div>}
          {isSlow && <p className={styles.notice} role="status">서버를 깨우는 중이에요. 첫 요청은 30초쯤 걸릴 수 있어요.</p>}
          {videoLoading ? <p className={styles.empty} role="status">요리 영상을 불러오고 있어요.</p>
            : videos.length === 0 && !videoError ? <p className={styles.empty}>아직 준비된 영상이 없어요.<br />추천 탭에서 오늘의 메뉴를 찾아보세요.</p>
            : <ul className={styles.videoGrid}>{videos.map((video) => (
              <li key={video.video_id}><a className={styles.video} href={toHttps(video.video_url) ?? video.video_url} target="_blank" rel="noreferrer noopener"><img src={toHttps(video.thumbnail_url) ?? ''} alt="" loading="lazy" /><p className={styles.videoTitle}>{video.video_title}</p><p className={styles.videoMeta}>{video.channel_title}</p></a></li>
            ))}</ul>}
        </section>
      )}

      {view === 'recipes' && (
        <section role="tabpanel" id="home-panel-recipes" aria-labelledby="home-tab-recipes" className={styles.panel}>
          <ul className={styles.chips}>
            {[{ category: ALL_CATEGORIES, count: 0 }, ...categories].map((item) => <li key={item.category}><button type="button" className={item.category === category ? `${styles.chip} ${styles.chipSelected}` : styles.chip} aria-pressed={item.category === category} onClick={() => { if (item.category !== category) { ++requestRef.current; setCategory(item.category) } }}>{item.category}</button></li>)}
          </ul>
          <div className={styles.sectionHead}>
            <div className={styles.sectionTitle}>
              <h2>{keyword.trim() ? `'${keyword.trim()}' 검색 결과` : '오늘 뭐 먹지?'}</h2>
              <p className={styles.resultCount}>{!isLoading && recipes.length > 0 ? `${recipes.length}개 보는 중` : '레시피 둘러보기'}</p>
            </div>
            <Link to="/recommend" className={styles.pantryLink} aria-label="내 재료로 만들 수 있는 요리">
              <Icon name="fridge" size={20} /><span>내 재료로 찾기</span><Icon name="chevron-right" size={16} />
            </Link>
          </div>
          {isSlow && <p className={styles.notice} role="status">서버를 깨우는 중이에요<small>무료 서버라 첫 요청은 30초쯤 걸려요. 조금만 기다려주세요.</small></p>}
          <p role="status" className="sr-only">{isLoading ? '레시피를 검색하고 있어요.' : !error ? `레시피 ${recipes.length}개를 불러왔어요.` : ''}</p>
          {error && <div className={styles.error} role="alert"><p>{error}</p><button className={styles.retry} type="button" onClick={() => void load(keyword, category)}>다시 불러오기</button></div>}
          {isLoading ? <ul className={styles.grid} aria-hidden="true">{Array.from({ length: 6 }, (_, index) => <li key={index} className={styles.skeleton} />)}</ul>
            : recipes.length === 0 && !error ? <p className={styles.empty}>조건에 맞는 레시피가 없어요.<br />검색어나 분류를 바꿔보세요.</p>
            : <ul className={styles.grid}>{recipes.map((recipe) => <li key={recipe.id}><RecipeCard recipe={recipe} /></li>)}</ul>}
          {hasMore && !isLoading && <button className={styles.more} type="button" onClick={() => void loadMore()} disabled={isLoadingMore}>{isLoadingMore ? '불러오는 중…' : '더 보기'}<Icon name="plus" size={16} /></button>}

          {isBrowsing && popular.length > 0 && <section className={styles.theme} aria-labelledby="theme-popular"><div className={styles.themeHead}><h2 id="theme-popular">많이 추천한 메뉴</h2><span>{popular.length}개</span></div><p className={styles.themeSubtitle}>다른 사람들이 추천한 레시피예요</p><ul className={styles.themeRow}>{popular.map((recipe) => <li key={recipe.id}><RecipeCard recipe={recipe} note={`${recipe.like_count}명이 추천`} /></li>)}</ul></section>}
          {isBrowsing && themes.map((theme) => (
            <section className={styles.theme} key={theme.key} aria-labelledby={`theme-${theme.key}`}>
              <div className={styles.themeHead}>
                <h2 id={`theme-${theme.key}`}>{theme.title}</h2>
                <div className={styles.themeActions}>
                  <span>{theme.total}개</span>
                  <Link className={styles.themeAll} to={`/themes/${theme.key}?month=${themeMonth}`} aria-label={`${theme.title} 레시피 전체보기`}>
                    전체보기<Icon name="chevron-right" size={16} />
                  </Link>
                </div>
              </div>
              {theme.subtitle && <p className={styles.themeSubtitle}>{theme.subtitle}</p>}
              <ul className={styles.themeRow}>{theme.recipes.map((recipe) => <li key={recipe.id}><RecipeCard recipe={recipe} /></li>)}</ul>
            </section>
          ))}
        </section>
      )}
    </div>
  )
}
