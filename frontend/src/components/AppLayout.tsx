import { NavLink, Outlet, useLocation } from 'react-router-dom'

import AuthPage from '../routes/AuthPage'
import { useAuth } from '../auth/context'
import styles from './AppLayout.module.css'

/**
 * 하단 탭 네 개.
 *
 * 라벨은 네 칸에 나눠 들어가므로 짧아야 한다. "나를 위한 레시피 추천"은 화면 제목으로
 * 쓰고 탭에는 "맞춤추천"으로 줄인다.
 */
const TABS = [
  { to: '/', label: '홈', icon: '🏠', end: true },
  { to: '/recommend', label: '맞춤추천', icon: '✨', end: false },
  { to: '/brags', label: '자랑하기', icon: '📸', end: false },
  // 냉장고는 탭에서 빼고 마이 안으로 넣었다. 매일 여는 화면이 아니라 가끔 정리하는
  // 화면이라, 네 칸 중 하나를 계속 차지할 자리가 아니라고 봤다.
  { to: '/my', label: '마이', icon: '👤', end: false },
]

/**
 * 로그인 없이도 열리는 경로.
 *
 * 레시피 상세를 링크로 공유할 수 있는 것이 V3 전환의 가장 큰 이득이었다. 링크를 받은
 * 사람은 대개 로그인돼 있지 않으므로, 여기까지 막으면 그 이득이 통째로 사라진다.
 * 나머지 화면은 로그인해야 보인다.
 */
const PUBLIC_PREFIXES = ['/recipe/']

/**
 * 앱 껍데기이자 인증 관문.
 *
 * 로그인하지 않았으면 탭바 없이 로그인 화면을 보여준다. 탭을 보여줘 봐야 눌러도
 * 전부 로그인하라는 안내로 끝나서, 갈 곳 없는 메뉴만 늘어놓는 셈이 된다.
 */
export default function AppLayout() {
  const { isAuthenticated } = useAuth()
  const { pathname } = useLocation()
  const isPublic = PUBLIC_PREFIXES.some((prefix) => pathname.startsWith(prefix))

  if (!isAuthenticated && !isPublic) {
    return <AuthPage mode="login" />
  }

  return (
    <div className={styles.shell}>
      <main className={styles.content}>
        <Outlet />
      </main>

      {/* 비로그인이 공유 링크로 들어온 경우에는 탭바를 감춘다. 갈 수 있는 곳이 없다. */}
      {isAuthenticated && (
        <nav className={styles.tabbar} aria-label="주요 메뉴">
          {TABS.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end={tab.end}
              className={({ isActive }) =>
                isActive ? `${styles.tab} ${styles.active}` : styles.tab
              }
            >
              {/* 아이콘은 장식이므로 보조기기에서 읽지 않는다. 라벨이 이름을 담당한다. */}
              <span className={styles.icon} aria-hidden="true">
                {tab.icon}
              </span>
              {tab.label}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  )
}
