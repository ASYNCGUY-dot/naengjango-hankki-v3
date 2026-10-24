import type { DailyNutrition } from '../api/meals'

/** 오늘 날짜를 사용해 다른 화면의 테스트가 자정 타이머에 좌우되지 않게 한다. */
export function dailyNutrition(overrides: Partial<DailyNutrition> = {}): DailyNutrition {
  const now = new Date()
  const date = new Date(now.getTime() + 9 * 60 * 60 * 1000).toISOString().slice(0, 10)
  return {
    date,
    timezone: 'Asia/Seoul',
    server_now: now.toISOString(),
    next_reset_at: new Date(Date.parse(`${date}T00:00:00+09:00`) + 24 * 60 * 60 * 1000).toISOString(),
    meals: [],
    incomplete_nutrients: [],
    nutrition: {
      available: true, bracket_label: '테스트 기준', is_estimated: false,
      micro_is_partial: false, condition_notes: [],
      rows: [{ key: 'protein_g', label: '단백질', unit: 'g', target: 55, provided: 0, pct_of_daily: 0, already_supplemented: false }],
      sodium_row: { label: '나트륨', unit: 'mg', limit: 2300, provided: 0, pct_of_limit: 0, limit_adjusted: false },
    },
    ...overrides,
  }
}
