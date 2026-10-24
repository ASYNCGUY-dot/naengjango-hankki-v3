import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

// 디자인 토큰은 저장소 루트의 design/tokens.css가 원본이다. 프론트로 복사하지 않고
// 그대로 import한다 - 사본이 둘이면 한쪽이 낡는다. vite.config.ts의 server.fs.allow 참고.
import '../../design/tokens.css'
import './index.css'
import './styles/집밥테마.css'
import App from './App'
import { AuthProvider } from './auth/AuthContext'
import { FavoritesProvider } from './favorites/FavoritesProvider'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <FavoritesProvider><App /></FavoritesProvider>
      </AuthProvider>
    </BrowserRouter>
  </StrictMode>,
)
