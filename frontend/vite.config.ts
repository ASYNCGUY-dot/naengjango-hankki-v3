// vitest/config에서 가져온다(vite가 아니라) - test 키를 아는 쪽이 이쪽이다.
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // design/tokens.css는 저장소 루트에 있고 frontend/ 밖이다. 토큰을 프론트로 복사하면
    // 사본이 둘이 되어 한쪽이 낡으므로, 원본을 그대로 import하고 개발 서버가 그 경로만
    // 읽을 수 있게 허용한다. tests/test_design_tokens.py도 같은 원본을 검사한다.
    //
    // '..'(저장소 전체)로 열지 않는다. .env는 Vite 기본 deny 목록이 막아주지만
    // api/*.py나 문서까지 개발 서버로 읽히는 것은 넓힐 이유가 없다(실제로 확인했다).
    fs: { allow: ['./', '../design'] },
  },
  test: {
    // 테스트를 코드와 같은 속도로 쓴다는 게 V3의 규율이다(V2는 프론트 커버리지가 0%였다).
    // 그래서 스캐폴딩 단계에서 미리 붙여둔다.
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      // 화면 코드가 아직 없어서 문턱은 나중에 올린다. 지금은 측정만 켜둔다.
      exclude: ['src/api/schema.d.ts', 'src/main.tsx', '**/*.d.ts'],
    },
  },
})
