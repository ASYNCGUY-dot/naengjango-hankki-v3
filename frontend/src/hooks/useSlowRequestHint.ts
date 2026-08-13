import { useEffect, useState } from 'react'

import { SLOW_RESPONSE_HINT_MS } from '../api/client'

/**
 * 요청이 오래 걸릴 때 "서버를 깨우는 중" 안내를 띄울지 알려준다.
 *
 * Render 무료 티어는 15분 유휴 후 중단되고 첫 요청에 30~60초가 걸린다(실측 34.6초).
 * 그동안 아무 신호가 없으면 사용자는 앱이 멈춘 줄 안다. 로그인이 대개 사용자가 보내는
 * 첫 요청이라, 이 안내가 가장 먼저 필요한 자리도 로그인이다.
 *
 * 처음부터 띄우지는 않는다. 서버가 깨어 있으면 1초 안에 끝나는데, 그때 "깨우는 중"이
 * 깜빡이면 오히려 느려 보인다.
 */
export function useSlowRequestHint(isPending: boolean): boolean {
  const [isSlow, setIsSlow] = useState(false)

  useEffect(() => {
    if (!isPending) {
      setIsSlow(false)
      return
    }
    const timer = setTimeout(() => setIsSlow(true), SLOW_RESPONSE_HINT_MS)
    return () => clearTimeout(timer)
  }, [isPending])

  return isSlow
}
