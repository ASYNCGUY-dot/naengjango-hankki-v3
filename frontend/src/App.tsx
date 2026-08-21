import { Navigate, Route, Routes } from 'react-router-dom'

import AppLayout from './components/AppLayout'
import AdminPage from './routes/AdminPage'
import AuthPage from './routes/AuthPage'
import BragPage from './routes/BragPage'
import BragWritePage from './routes/BragWritePage'
import FeedbackPage from './routes/FeedbackPage'
import HomePage from './routes/HomePage'
import IngredientSubmissionPage from './routes/IngredientSubmissionPage'
import MyPage from './routes/MyPage'
import MyRecipesPage from './routes/MyRecipesPage'
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
 *
 * 인증 관문은 AppLayout 한 곳에 있다(2026-08-20). 로그인하지 않고 "/"에 오면 로그인
 * 화면이 뜨고, 레시피 상세만 예외로 열려 있다.
 */
export default function App() {
  return (
    <Routes>
      {/* 로그인·회원가입은 하단 탭바가 없는 화면이라 AppLayout 밖에 둔다.
          "/"가 이미 로그인 화면이지만, 로그아웃 후 이동이나 안내 문구의 링크가
          가리킬 고정된 주소가 따로 있어야 한다. */}
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
        {/* 냉장고는 탭에서 빠지고 마이 안으로 들어갔다. 주소는 그대로 둔다 -
            추천 화면의 "냉장고 채우러 가기" 같은 링크가 이미 여기를 가리킨다. */}
        <Route path="/pantry" element={<PantryPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/recipe/:recipeId" element={<RecipeDetailPage />} />
        {/* 자랑하기. 글쓰기는 주소를 나눠서, 쓰다 말고 뒤로가기를 눌러도 피드로
            돌아오게 한다. 레시피 상세에서 올 때는 ?recipe=67로 미리 골라 온다. */}
        <Route path="/brags" element={<BragPage />} />
        <Route path="/brags/new" element={<BragWritePage />} />
        <Route path="/my" element={<MyPage />} />
        {/* 초대 페이지의 "하고 싶은 말" 버튼이 여기를 가리킨다. 주소를 짧게 둔 이유다. */}
        <Route path="/feedback" element={<FeedbackPage />} />
        {/* 내가 올린 것들. 마이 안에 두는 게 아니라 주소를 나눈 이유는 목록이 길어질 수
            있고, 등록하다 만 상태에서 뒤로가기가 자연스러워야 하기 때문이다. */}
        <Route path="/my/recipes" element={<MyRecipesPage />} />
        <Route path="/my/ingredients" element={<IngredientSubmissionPage />} />
        {/* 권한은 서버가 확인한다. 관리자가 아니면 403이 오고 화면이 안내로 바뀐다. */}
        <Route path="/admin" element={<AdminPage />} />
        <Route path="/onboarding" element={<OnboardingPage />} />
      </Route>
      {/* 없는 주소는 홈으로. 지인 테스트에서 오타 링크를 받아도 빈 화면을 보지 않게 한다. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
