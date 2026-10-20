import { describe, expect, it } from 'vitest'

import themeCss from './집밥테마.css?raw'

// 실제 프론트에서 마지막에 적용되는 테마를 읽는다. 루트 design 토큰만 검사하면
// 집밥테마가 덮어쓴 색상의 대비 오류를 발견할 수 없다.
function colors(selector: string): Record<string, string> {
  const start = themeCss.indexOf(selector)
  if (start < 0) throw new Error(`테마 선택자가 없습니다: ${selector}`)
  const body = themeCss.slice(themeCss.indexOf('{', start) + 1, themeCss.indexOf('}', start))
  return Object.fromEntries(
    [...body.matchAll(/(--[\w-]+)\s*:\s*(#[\da-fA-F]{6})\s*;/g)].map((match) => [match[1], match[2]]),
  )
}

// tests/test_design_tokens.py와 동일한 WCAG 상대 휘도 계산.
// sRGB 선형화 경계는 현재 공식의 0.04045를 사용한다.
function luminance(hex: string): number {
  if (!/^#[\da-fA-F]{6}$/.test(hex)) throw new Error(`색상 토큰을 확인해주세요: ${hex}`)
  const channels = [1, 3, 5].map((offset) => {
    const value = parseInt(hex.slice(offset, offset + 2), 16) / 255
    return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  })
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722
}

function contrast(foreground: string, background: string): number {
  const values = [luminance(foreground), luminance(background)]
  return (Math.max(...values) + 0.05) / (Math.min(...values) + 0.05)
}

const light = colors(':root {')
const darkOverrides = colors(":root[data-theme='dark']")
const dark = { ...light, ...darkOverrides }
const surfaces = ['base', 'raised', 'sunken', 'accent']

type Pair = { label: string; foreground: string; background: string; minimum: number }
const pairs: Pair[] = [
  // 본문·입력·카드뿐 아니라 안내 박스 안의 작은 보조 설명도 4.5:1이 필요하다.
  ...['primary', 'secondary'].flatMap((kind) => surfaces.map((surface) => ({
    label: `${kind === 'primary' ? '본문' : '보조 설명'} / ${surface} 배경`,
    foreground: `--color-text-${kind}`,
    background: `--color-surface-${surface}`,
    minimum: 4.5,
  }))),
  ...['accent', 'accent-strong'].map((fill) => ({
    label: `버튼 글자 / ${fill === 'accent' ? '기본' : '호버'} 상태`,
    foreground: '--color-text-on-accent',
    background: `--color-${fill}`,
    minimum: 4.5,
  })),
  ...['base', 'sunken', 'accent'].map((surface) => ({
    label: `강조 글자 / ${surface} 배경`,
    foreground: '--color-accent-text',
    background: `--color-surface-${surface}`,
    minimum: 4.5,
  })),
  ...surfaces.map((surface) => ({
    label: `키보드 초점 / ${surface} 배경`,
    foreground: '--color-focus-ring',
    background: `--color-surface-${surface}`,
    minimum: 3,
  })),
  // 흰 입력칸과 회색 입력칸(파트너 키 등) 양쪽 경계를 확인한다.
  ...['raised', 'sunken'].map((surface) => ({
    label: `입력 경계 / ${surface} 배경`,
    foreground: '--color-border-strong',
    background: `--color-surface-${surface}`,
    minimum: 3,
  })),
  { label: '선택 메뉴 아이콘 / 메뉴 배경', foreground: '--feed-coral', background: '--color-surface-raised', minimum: 3 },
]

describe.each([{ name: '밝은 테마', palette: light }, { name: '어두운 테마', palette: dark }])('$name 색상 대비', ({ palette }) => {
  it.each(pairs)('$label', ({ foreground, background, minimum }) => {
    const measured = contrast(palette[foreground], palette[background])
    expect(measured, `${foreground} ${palette[foreground]} / ${background} ${palette[background]}: ${measured.toFixed(3)}:1, 최소 ${minimum}:1`).toBeGreaterThanOrEqual(minimum)
  })
})

it('시스템 다크 모드와 명시적 다크 모드가 같은 팔레트를 사용한다', () => {
  expect(colors(":root:not([data-theme='light'])")).toEqual(darkOverrides)
})
