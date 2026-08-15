import { NavLink, Outlet } from 'react-router-dom'

import styles from './AppLayout.module.css'

/** 시안(design/mockups/index.html)의 하단 탭바 4개와 같은 구성이다. */
const TABS = [
  { to: '/', label: '홈', icon: '🏠', end: true },
  { to: '/pantry', label: '냉장고', icon: '🧊', end: false },
  { to: '/recommend', label: '추천', icon: '✨', end: false },
  // 로그인 화면이 아니라 마이 화면을 가리킨다. 예전에는 /login이라, 이미 로그인한
  // 사람이 눌러도 로그인 화면이 떴다.
  { to: '/my', label: '마이', icon: '👤', end: false },
]

export default function AppLayout() {
  return (
    <div className={styles.shell}>
      <main className={styles.content}>
        <Outlet />
      </main>

      <nav className={styles.tabbar} aria-label="주요 메뉴">
        {TABS.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => (isActive ? `${styles.tab} ${styles.active}` : styles.tab)}
          >
            {/* 아이콘은 장식이므로 보조기기에서 읽지 않는다. 라벨이 이름을 담당한다. */}
            <span className={styles.icon} aria-hidden="true">
              {tab.icon}
            </span>
            {tab.label}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
