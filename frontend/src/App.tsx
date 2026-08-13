import { Navigate, Route, Routes } from 'react-router-dom'

import AppLayout from './components/AppLayout'
import HomePage from './routes/HomePage'
import LoginPage from './routes/LoginPage'
import PantryPage from './routes/PantryPage'
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
      <Route path="/login" element={<LoginPage />} />
      <Route element={<AppLayout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/pantry" element={<PantryPage />} />
        <Route path="/recommend" element={<RecommendPage />} />
        <Route path="/recipe/:recipeId" element={<RecipeDetailPage />} />
      </Route>
      {/* 없는 주소는 홈으로. 지인 테스트에서 오타 링크를 받아도 빈 화면을 보지 않게 한다. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
