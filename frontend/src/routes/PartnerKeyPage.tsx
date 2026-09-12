import { useEffect, useState } from 'react'

import { ApiError } from '../api/client'
import {
  deletePartnerKey,
  getPartnerKeyStatus,
  savePartnerKey,
  type PartnerKeyStatus,
} from '../api/shopping'
import { useAuth } from '../auth/context'
import styles from './PartnerKeyPage.module.css'

/**
 * 내가 올린 레시피의 재료 구매 수수료를 내가 받기 (#95).
 *
 * 내 레시피가 서버가 정한 추천 수를 넘으면, 그 레시피의 재료 구매 링크가 **내 쿠팡파트너스 키로**
 * 만들어진다. 그때부터 다른 사람이 그 링크로 사면 수수료가 나에게 온다. 돈이 쿠팡에서
 * 나에게 직접 가므로 이 앱은 정산에 끼어들지 않는다.
 *
 * 화면이 지켜야 할 것 둘.
 *
 * 저장한 키는 **다시 보여주지 않는다.** 서버가 아예 안 돌려주므로 여기서 채울 수도 없다.
 * 그래서 "등록됨"과 "갱신 시각"만 보여주고, 바꾸려면 다시 입력하게 한다.
 *
 * 그리고 **왜 아직 수수료가 안 들어오는지**를 숨기지 않는다. 쿠팡은 누적 판매가 일정
 * 금액을 넘어야 API를 열어주는데, 그전에는 키를 넣어도 변환이 안 된다. 그 사실을 안
 * 적으면 "등록했는데 왜 안 되지"로 남는다.
 */
export default function PartnerKeyPage() {
  const { userId } = useAuth()
  const [status, setStatus] = useState<PartnerKeyStatus | null>(null)
  const [accessKey, setAccessKey] = useState('')
  const [secretKey, setSecretKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [saved, setSaved] = useState(false)
  const [isBusy, setIsBusy] = useState(false)

  useEffect(() => {
    if (userId === null) return
    const controller = new AbortController()
    getPartnerKeyStatus(userId, controller.signal)
      .then(setStatus)
      .catch(() => {
        // 못 불러왔으면 기준 숫자를 모른다. 0으로 두고 화면에서 숫자 대신 "여러"로 적는다 -
        // 여기서 아무 숫자나 넣으면 그게 곧 화면이 서버 기준을 지어내는 것이 된다.
        if (!controller.signal.aborted) {
          setStatus({ registered: false, updated_at: null, revenue_min_likes: 0 })
        }
      })
    return () => controller.abort()
  }, [userId])

  if (userId === null) return null

  async function handleSave(event: React.FormEvent) {
    event.preventDefault()
    if (userId === null) return
    setError(null)
    setSaved(false)
    setIsBusy(true)
    try {
      setStatus(await savePartnerKey(userId, accessKey.trim(), secretKey.trim()))
      // 저장한 뒤에는 입력칸을 비운다. 화면에 키를 띄워둘 이유가 없다.
      setAccessKey('')
      setSecretKey('')
      setSaved(true)
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : '저장하지 못했어요. 잠시 후 다시 시도해주세요.')
    } finally {
      setIsBusy(false)
    }
  }

  async function handleDelete() {
    if (userId === null) return
    setError(null)
    setSaved(false)
    setIsBusy(true)
    try {
      setStatus(await deletePartnerKey(userId))
    } catch (caught: unknown) {
      setError(caught instanceof ApiError ? caught.message : '해제하지 못했어요.')
    } finally {
      setIsBusy(false)
    }
  }

  return (
    <section className={styles.page}>
      <h1>재료 구매 수수료 받기</h1>

      <p className={styles.lead}>
        {/* 기준 숫자는 서버가 내려준 값을 그대로 쓴다. 화면이 따로 들고 있으면 기준이
            바뀔 때 조용히 어긋나고, 어긋나도 아무 오류가 안 난다. */}
        내가 올린 레시피가 <strong>추천 {status?.revenue_min_likes || '여러'}회</strong>를
        넘으면, 그 레시피의 재료 구매 링크가 내 쿠팡파트너스 키로 만들어져요. 수수료는
        쿠팡에서 나에게 직접 들어오고 이 앱은 중간에 끼지 않아요.
      </p>

      <div className={styles.notice}>
        <h2>먼저 알아둘 것</h2>
        <ul>
          <li>쿠팡파트너스에 <strong>직접 가입</strong>하셔야 해요. 이 앱이 대신 못 해요.</li>
          <li>
            쿠팡은 <strong>누적 판매가 일정 금액을 넘어야</strong> 키(API)를 열어줘요.
            그전까지는 키를 넣어도 링크가 그대로라 수수료가 안 잡혀요.
          </li>
          <li>넣은 키는 암호화해서 보관하고, 저장한 뒤에는 화면에 다시 보여주지 않아요.</li>
        </ul>
      </div>

      {status?.registered ? (
        <p className={styles.registered} role="status">
          키가 등록돼 있어요.
          {status.updated_at && <small>마지막 갱신 {status.updated_at.slice(0, 10)}</small>}
        </p>
      ) : (
        <p className={styles.unregistered} role="status">아직 등록된 키가 없어요.</p>
      )}

      <form className={styles.form} onSubmit={handleSave}>
        <label>
          <span>Access Key</span>
          <input
            value={accessKey}
            onChange={(e) => setAccessKey(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            required
          />
        </label>
        <label>
          <span>Secret Key</span>
          {/* 어깨너머로 보이지 않게 가린다. 저장 뒤에는 어차피 비워진다. */}
          <input
            type="password"
            value={secretKey}
            onChange={(e) => setSecretKey(e.target.value)}
            autoComplete="off"
            spellCheck={false}
            required
          />
        </label>

        {error && <p className={styles.error} role="alert">{error}</p>}
        {saved && <p className={styles.saved} role="status">저장했어요.</p>}

        <button className={styles.primary} type="submit" disabled={isBusy}>
          {status?.registered ? '키 바꾸기' : '키 등록하기'}
        </button>
      </form>

      {status?.registered && (
        <button className={styles.danger} type="button" onClick={handleDelete} disabled={isBusy}>
          연동 해제하기
        </button>
      )}
    </section>
  )
}
