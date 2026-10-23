import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react'
import styles from './ExpiryDatePicker.module.css'

type DateParts = { year: number; month: number; day: number }
type Props = { id?: string; value: string; onChange: (value: string) => void }
const ROW_HEIGHT = 44

function daysInMonth(year: number, month: number) {
  return new Date(year, month, 0).getDate()
}

function initialDate(value: string): DateParts {
  if (value) {
    const [year, month, day] = value.split('-').map(Number)
    if (year >= 100 && month >= 1 && month <= 12 && day >= 1 && day <= daysInMonth(year, month)) {
      return { year, month, day }
    }
  }
  const today = new Date()
  return { year: today.getFullYear(), month: today.getMonth() + 1, day: today.getDate() }
}

function toDateString({ year, month, day }: DateParts) {
  return `${String(year).padStart(4, '0')}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}

function DateWheel({ label, suffix, value, min, max, onChange }: {
  label: string; suffix: string; value: number; min: number; max: number; onChange: (value: number) => void
}) {
  const scroller = useRef<HTMLDivElement>(null)
  const labelId = useId()

  useLayoutEffect(() => {
    const element = scroller.current
    if (element && Math.round(element.scrollTop / ROW_HEIGHT) !== value - min) {
      element.scrollTop = (value - min) * ROW_HEIGHT
    }
  }, [value, min, max])

  function handleKey(event: KeyboardEvent<HTMLDivElement>) {
    const next = event.key === 'ArrowUp' ? value + 1
      : event.key === 'ArrowDown' ? value - 1
      : event.key === 'Home' ? min
      : event.key === 'End' ? max
      : null
    if (next === null) return
    event.preventDefault()
    onChange(Math.max(min, Math.min(max, next)))
  }

  return (
    <div className={styles.column}>
      <span className={styles.label} id={labelId}>{label}</span>
      <div
        ref={scroller}
        className={styles.wheel}
        role="spinbutton"
        tabIndex={0}
        aria-labelledby={labelId}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={`${value}${suffix}`}
        onKeyDown={handleKey}
        onScroll={(event) => {
          const next = Math.max(min, Math.min(max, min + Math.round(event.currentTarget.scrollTop / ROW_HEIGHT)))
          if (next !== value) onChange(next)
        }}
      >
        {Array.from({ length: max - min + 1 }, (_, index) => min + index).map((option) => (
          <button
            key={option}
            type="button"
            tabIndex={-1}
            className={styles.option}
            aria-pressed={option === value}
            onClick={() => onChange(option)}
          >
            {option}{suffix}
          </button>
        ))}
      </div>
    </div>
  )
}

function PickerDialog({ value, onSelect, onDismiss }: {
  value: string; onSelect: (value: string) => void; onDismiss: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const hintId = useId()
  const [ready, setReady] = useState(false)
  const [draft, setDraft] = useState(() => initialDate(value))
  const [yearRange] = useState(() => ({ min: Math.min(1900, draft.year), max: Math.max(2199, draft.year) }))

  useEffect(() => {
    const element = dialog.current
    element?.showModal()
    // 닫힌 dialog에서는 scrollTop이 0으로 고정된다. 열린 뒤 휠을 배치해야
    // 현재 날짜가 처음부터 가운데에 놓인다.
    setReady(true)
    return () => element?.close()
  }, [])

  function update(part: keyof DateParts, next: number) {
    setDraft((previous) => {
      if (previous[part] === next) return previous
      const updated = { ...previous, [part]: next }
      updated.day = Math.min(updated.day, daysInMonth(updated.year, updated.month))
      return updated
    })
  }

  function dismiss() {
    dialog.current?.close()
    onDismiss()
  }

  function select(next: string) {
    dialog.current?.close()
    onSelect(next)
  }

  return (
    <dialog
      ref={dialog}
      className={styles.dialog}
      aria-labelledby={titleId}
      aria-describedby={hintId}
      onCancel={(event) => { event.preventDefault(); dismiss() }}
    >
      <div className={styles.heading}>
        <h2 id={titleId}>소비기한 선택</h2>
        <button type="button" className={styles.cancel} onClick={dismiss}>취소</button>
      </div>
      <p id={hintId} className={styles.hint}>위아래로 넘기거나 날짜를 눌러 선택하세요.</p>
      <div className={styles.wheels}>
        {ready && <>
          <DateWheel label="연도" suffix="년" min={yearRange.min} max={yearRange.max} value={draft.year} onChange={(year) => update('year', year)} />
          <DateWheel label="월" suffix="월" min={1} max={12} value={draft.month} onChange={(month) => update('month', month)} />
          <DateWheel label="일" suffix="일" min={1} max={daysInMonth(draft.year, draft.month)} value={draft.day} onChange={(day) => update('day', day)} />
        </>}
      </div>
      <div className={styles.result}>
        <span>선택한 날짜</span>
        <output aria-live="polite">{toDateString(draft)}</output>
      </div>
      <button type="button" className={styles.confirm} onClick={() => select(toDateString(draft))}>선택 완료</button>
      {value && <button type="button" className={styles.clear} onClick={() => select('')}>날짜 지우기</button>}
    </dialog>
  )
}

/** 선택 중에는 임시 날짜만 바꾸고, 완료를 누를 때 입력값에 반영한다. */
export default function ExpiryDatePicker({ id, value, onChange }: Props) {
  const [open, setOpen] = useState(false)
  const trigger = useRef<HTMLButtonElement>(null)

  function dismiss() {
    setOpen(false)
    trigger.current?.focus()
  }

  return (
    <>
      <button
        ref={trigger}
        id={id}
        type="button"
        className={styles.trigger}
        aria-label="소비기한"
        aria-description={value ? `선택한 날짜 ${value}` : '날짜를 선택하세요.'}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <span>{value || '소비기한'}</span>
        <span aria-hidden="true">⌄</span>
      </button>
      {open && <PickerDialog value={value} onDismiss={dismiss} onSelect={(next) => { onChange(next); dismiss() }} />}
    </>
  )
}
