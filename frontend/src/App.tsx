import { Navigate, Route, Routes } from 'react-router-dom'

import AppLayout from './components/AppLayout'
import AuthPage from './routes/AuthPage'
import HomePage from './routes/HomePage'
import MyPage from './routes/MyPage'
import OnboardingPage from './routes/OnboardingPage'
import PantryPage from './routes/PantryPage'
import { ForgotPasswordPage, ResetPasswordPage } from './routes/PasswordResetPage'
import { PrivacyPage, TermsPage } from './routes/PolicyPage'
import RecipeDetailPage from './routes/RecipeDetailPage'
import RecommendPage from './routes/RecommendPage'

/**
 * V2는 화면이 전부 하나의 라우트(/demo)였고 탭 전환을 State로만 처리했다. 그래서 레시피
 * 상세를 링크로 공유할 수 없었고 뒤로가기도 동작하지 않았다. V3에서 진짜 URL로 쪼갠다.
 *
 * 레시피 상세만 /recipe/:recipeId로 파라미터를 받는다 - 공유 가능한 주소가 되는 게
 * 이번 전환에서 가장 실질적인 이득이다.
 */
export default function App() {
  return (
    <Routes>
      {/* 로그인·회원가입은 하단 탭바가 없는 화면이라 AppLayout 밖에 둔다.
          주소를 나눈 이유: 회원가입 링크를 그대로 공유할 수 있고 뒤로가기가 자연스럽다. */}
      <Route path="/login" element={<AuthPage mode="login" />} />
      <Route path="/signup" element={<AuthPage mode="signup" />} />
      {/* 비밀번호 "찾기"는 없다 - 단방향 해시라 서버도 모른다. 초기화만 가능하다.
          /reset-password는 메일의 링크로 들어오는 자리라 주소에 token을 달고 온다. */}
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      {/* 가입 화면의 동의 체크박스가 여기로 연결된다. 문서 없이 동의만 받으면
          그 동의는 기록으로서 의미가 없다. */}
      <Route path="/terms" element={<TermsPage />} />
      <Route path="/privacy" element={<PrivacyPage />} />
      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/pantry" element={<PantryPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/recipe/:recipeId" element={<RecipeDetailPage />} />
        <Route path="/my" element={<MyPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>
      {/* 없는 주소는 홈으로. 지인 테스트에서 오타 링크를 받아도 빈 화면을 보지 않게 한다. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
