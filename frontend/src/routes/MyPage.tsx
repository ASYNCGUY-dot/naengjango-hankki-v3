import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, TimeoutError } from '../api/client'
import { listFavorites, type FavoriteItem } from '../api/favorites'
import { getProfile, type Profile } from '../api/profile'
import RecipeCard from '../components/RecipeCard'
import { useAuth } from '../auth/context'
import styles from './MyPage.module.css'

function describe(caught: unknown): string {
  if (caught instanceof ApiError || caught instanceof TimeoutError) return caught.message
  return '내 정보를 불러오지 못했어요.'
}

/**
 * 마이 화면.
 *
 * 이 화면이 없어서 두 가지가 막혀 있었다. 로그인한 사용자가 로그아웃할 방법이 없었고
 * (logout()은 있는데 부르는 곳이 없었다), 하단 탭의 "마이"가 로그인 화면을 가리켜서
 * 이미 로그인한 사람이 눌러도 로그인 화면이 떴다.
 */
export default function MyPage() {
  const { userId, isAuthenticated, logout } = useAuth()
  const navigate = useNavigate()

  const [profile, setProfile] = useState<Profile | null>(null)
  // 저장해둔 레시피. 이게 없던 동안에는 마음에 든 것을 다시 찾을 방법이 검색뿐이었다.
  const [favorites, setFavorites] = useState<FavoriteItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [isLoggingOut, setIsLoggingOut] = useState(false)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    listFavorites(userId, controller.signal)
      .then(setFavorites)
      // 저장 목록을 못 받아도 계정 정보와 로그아웃은 보여야 한다.
      .catch(() => {})

    getProfile(userId, controller.signal)
      .then(setProfile)
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) setError(describe(caught))
      })
    return () => controller.abort()
  }, [userId])

  async function handleLogout() {
    if (isLoggingOut) return
    setIsLoggingOut(true)
    try {
      await logout()
    } catch {
      // 서버 호출이 실패해도 이 기기에서는 이미 로그아웃됐다(AuthContext 참고).
      // 사용자를 붙잡아둘 이유가 없으므로 그대로 홈으로 보낸다.
    } finally {
      setIsLoggingOut(false)
      navigate('/', { replace: true })
    }
  }

  if (!isAuthenticated) {
    return (
      <div className={styles.guest}>
        <h1>마이</h1>
        <p>
          로그인하면 냉장고 재료를 저장하고 추천을 받을 수 있어요.
          <br />
          로그인 없이도 레시피는 둘러볼 수 있어요.
        </p>
        <Link className={styles.primary} to="/login">
          로그인하러 가기
        </Link>
      </div>
    )
  }

  return (
    <div className={styles.page}>
      <h1>마이</h1>

      {error !== null && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      <div className={styles.card}>
        <p className={styles.who}>{profile?.name ?? '내 계정'}</p>
        {profile?.username && <p className={styles.account}>@{profile.username}</p>}
      </div>

      {profile !== null &&
        (profile.has_profile ? (
          // 수정하러 가는 길은 아래 메뉴에 있다. 여기서는 반영되고 있다는 사실만 알린다.
          <p className={styles.done}>
            식단 정보를 입력해두셨어요. 알레르기와 건강목표가 추천에 반영됩니다.
          </p>
        ) : (
          // 온보딩을 안 하면 users.allergy가 NULL이라 알레르기 제외가 아예 돌지 않는다.
          // 알레르기가 있는 사람에게는 위험할 수 있어 그냥 안내가 아니라 눈에 띄게 알린다.
          <>
            <p className={styles.todo} role="status">
              <span aria-hidden="true">⚠️</span>
              <span>
                식단 정보를 아직 입력하지 않으셨어요
                <small>알레르기를 입력해야 그 재료가 든 레시피를 추천에서 빼드릴 수 있어요.</small>
              </span>
            </p>
            <Link className={styles.primary} to="/onboarding">
              식단 정보 입력하기
            </Link>
          </>
        ))}

      <section className={styles.saved} aria-labelledby="saved-heading">
        <div className={styles.savedHead}>
          <h2 id="saved-heading">즐겨찾기</h2>
          {favorites.length > 0 && <span>{favorites.length}개</span>}
        </div>
        {favorites.length === 0 ? (
          <p className={styles.savedEmpty}>
            레시피 화면에서 <strong>즐겨찾기</strong>를 누르면 여기에 모여요.
          </p>
        ) : (
          <ul className={styles.savedGrid}>
            {favorites.map((item) => (
              <li key={item.id}>
                <RecipeCard recipe={item} />
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* 냉장고는 하단 탭에서 빼고 여기로 넣었다(2026-08-20). 매일 여는 화면이 아니라
          가끔 정리하는 화면이라, 네 칸 중 하나를 계속 차지할 자리가 아니라고 봤다. */}
      <nav className={styles.links} aria-label="내 정보와 등록한 것">
        <Link className={styles.link} to="/pantry">
          <span>내 냉장고 재료</span>
          <small>지금 있는 재료를 넣고 유통기한을 관리해요</small>
        </Link>
        <Link className={styles.link} to="/onboarding">
          <span>식단 정보 수정</span>
          <small>알레르기·건강목표·조리도구를 고쳐요</small>
        </Link>
        <Link className={styles.link} to="/my/recipes">
          <span>내 레시피</span>
          <small>직접 만든 레시피를 올리고 상태를 확인해요</small>
        </Link>
        <Link className={styles.link} to="/my/ingredients">
          <span>재료 정보 등록</span>
          <small>공식 DB에 없는 재료의 영양 정보를 알려주세요</small>
        </Link>
        {profile?.is_admin && (
          <Link className={styles.link} to="/admin">
            <span>승인 대기 목록</span>
            <small>다른 사람이 올린 레시피와 재료를 검토해요</small>
          </Link>
        )}
      </nav>

      <button
        className={styles.button}
        type="button"
        onClick={() => void handleLogout()}
        disabled={isLoggingOut}
      >
        {isLoggingOut ? '로그아웃 중…' : '로그아웃'}
      </button>
    </div>
  )
}
