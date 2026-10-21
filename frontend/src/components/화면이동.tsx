import { useEffect, useLayoutEffect, useRef, type ReactNode } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'
import { useAuth } from '../auth/context'

const TITLES: Record<string, string> = {
  '/': '홈', '/login': '로그인', '/signup': '회원가입', '/pantry': '내 냉장고',
  '/recommend': '맞춤추천', '/brags': '집밥 자랑', '/brags/new': '집밥 올리기',
  '/my': '마이', '/onboarding': '식단 정보 수정', '/my/recipes': '내 레시피',
  '/my/ingredients': '재료 정보 등록', '/my/partner-key': '재료 구매 수수료',
  '/feedback': '하고 싶은 말', '/admin': '승인 대기 목록',
  '/forgot-password': '비밀번호 초기화', '/reset-password': '새 비밀번호 설정',
  '/terms': '이용약관', '/privacy': '개인정보 처리방침',
}
const PUBLIC = ['/login', '/signup', '/forgot-password', '/reset-password', '/terms', '/privacy']

/** 화면 이동의 제목·초점·스크롤을 한 곳에서 관리한다. */
export default function RouteExperience({ children }: { children: ReactNode }) {
  const location = useLocation()
  const navigationType = useNavigationType()
  const { isAuthenticated } = useAuth()
  const content = useRef<HTMLDivElement>(null)
  const positions = useRef(new Map<string, number>())
  const previous = useRef<string | null>(null)

  useEffect(() => {
    const old = window.history.scrollRestoration
    window.history.scrollRestoration = 'manual'
    return () => { window.history.scrollRestoration = old }
  }, [])

  // 화면이 짧아지며 발생하는 scroll 이벤트보다 먼저 이전 화면의 저장 리스너를 해제한다.
  // passive effect까지 기다리면 브라우저가 제한한 0이 이전 화면의 위치를 덮어쓴다.
  useLayoutEffect(() => {
    const region = content.current
    if (!region) return
    const identity = `${location.key}:${isAuthenticated}`
    const moved = previous.current !== null && previous.current !== identity
    previous.current = identity
    const protectedLogin = !isAuthenticated && !PUBLIC.includes(location.pathname)
      && !location.pathname.startsWith('/recipe/')
    const title = protectedLogin ? '로그인' : TITLES[location.pathname] ?? '레시피'
    const savedY = navigationType === 'POP' ? positions.current.get(location.key) ?? 0 : 0
    let restoring = moved && navigationType === 'POP' && savedY > 0
    let awaitingHeading = false

    const update = () => {
      const heading = region.querySelector<HTMLElement>('h1')
      const headingText = heading?.textContent?.trim()
      const recipeScreen = location.pathname.startsWith('/recipe/') || location.pathname.startsWith('/themes/')
      document.title = `${recipeScreen && headingText ? headingText : title} | 냉장고 한끼`
      if (heading) {
        heading.tabIndex = -1
        if (awaitingHeading && document.activeElement === region) heading.focus({ preventScroll: true })
        awaitingHeading = false
      }
      // 비동기 목록이 다시 채워진 뒤에도 뒤로가기 위치를 복구한다.
      if (restoring) {
        window.scrollTo({ top: savedY, behavior: 'instant' })
        if (document.documentElement.scrollHeight - window.innerHeight >= savedY) restoring = false
      }
    }
    update()
    if (moved) {
      const heading = region.querySelector<HTMLElement>('h1')
      ;(heading ?? region).focus({ preventScroll: true })
      awaitingHeading = heading === null
      if (!restoring) window.scrollTo({ top: savedY, behavior: 'instant' })
    }
    const observer = new MutationObserver(update)
    observer.observe(region, { childList: true, subtree: true, characterData: true })
    const save = () => { if (!restoring) positions.current.set(location.key, window.scrollY) }
    const stopRestoring = () => { restoring = false }
    window.addEventListener('scroll', save, { passive: true })
    window.addEventListener('wheel', stopRestoring, { passive: true })
    window.addEventListener('touchstart', stopRestoring, { passive: true })
    window.addEventListener('keydown', stopRestoring)
    return () => {
      observer.disconnect()
      window.removeEventListener('scroll', save)
      window.removeEventListener('wheel', stopRestoring)
      window.removeEventListener('touchstart', stopRestoring)
      window.removeEventListener('keydown', stopRestoring)
    }
  }, [location.key, location.pathname, isAuthenticated, navigationType])

  return <>
    <a className="skip-link" href="#page-content" onClick={(event) => {
      event.preventDefault()
      const heading = content.current?.querySelector<HTMLElement>('h1')
      ;(heading ?? content.current)?.focus()
    }}>본문 바로가기</a>
    <div id="page-content" ref={content} tabIndex={-1}>{children}</div>
  </>
}
