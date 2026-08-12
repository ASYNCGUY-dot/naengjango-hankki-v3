"""design/tokens.css의 색 조합이 WCAG 2.1 AA를 지키는지 검증한다 (Phase 2 종료 조건 5번).

왜 문서가 아니라 테스트인가
V2는 액센트 색을 바꾸면서 명암비를 한 번도 재지 않았다. 한 번 재고 문서에 적어두는 방식은
다음에 색을 조정하는 순간 다시 낡는다. 토큰 파일을 직접 읽어서 검사하면, 값을 바꾼 그
커밋에서 CI가 잡는다.

검사 기준(WCAG 2.1)
  1.4.3 일반 텍스트 4.5:1 (큰 텍스트는 3:1이지만 여기서는 보수적으로 4.5를 적용한다)
  1.4.11 UI 요소·의미를 가진 그래픽 3:1

채움색(--color-*-fill)은 "페이지 배경 대비"가 아니라 "그 위에 올라가는 글자 대비"로 본다.
글자가 들어간 뱃지는 의미를 글자가 전달하므로, 채움 자체가 배경과 3:1일 필요는 없고
안쪽 글자가 읽히면 된다. 반대로 글자 없이 단독으로 쓰는 아이콘·테두리는 3:1을 요구한다.
"""

import re
from pathlib import Path

import pytest

TOKENS_CSS = Path(__file__).resolve().parent.parent / "design" / "tokens.css"

LIGHT_SELECTOR = ":root {"
DARK_MEDIA_SELECTOR = ':root:not([data-theme="light"]) {'
DARK_EXPLICIT_SELECTOR = ':root[data-theme="dark"] {'


def _block_after(css: str, selector: str) -> str:
    """선택자 뒤의 선언 블록만 잘라낸다. 선언 안에는 중괄호가 없으므로 첫 '}'까지가 블록이다."""
    start = css.index(selector) + len(selector)
    end = css.index("}", start)
    return css[start:end]


def _parse_vars(block: str) -> dict[str, str]:
    return {
        name: value.strip()
        for name, value in re.findall(r"(--[\w-]+)\s*:\s*([^;]+);", block)
    }


@pytest.fixture(scope="module")
def css() -> str:
    return TOKENS_CSS.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def light(css) -> dict[str, str]:
    return _parse_vars(_block_after(css, LIGHT_SELECTOR))


@pytest.fixture(scope="module")
def dark(css) -> dict[str, str]:
    """다크 값은 라이트 위에 덮어쓰는 방식이라, 라이트를 바탕에 깔고 갱신한다."""
    merged = _parse_vars(_block_after(css, LIGHT_SELECTOR)).copy()
    merged.update(_parse_vars(_block_after(css, DARK_EXPLICIT_SELECTOR)))
    return merged


# ---------- 명암비 계산 ----------

def _linear(channel: int) -> float:
    c = channel / 255
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    h = hex_color.strip().lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast(fg: str, bg: str) -> float:
    a, b = luminance(fg), luminance(bg)
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


# ---------- 검사 대상 조합 ----------
# (전경 토큰, 배경 토큰, 요구 배율, 설명)
TEXT_PAIRS = [
    ("--color-text-primary", "--color-surface-base", 4.5, "본문/화면 바탕"),
    ("--color-text-primary", "--color-surface-raised", 4.5, "본문/카드"),
    ("--color-text-primary", "--color-surface-sunken", 4.5, "본문/입력 필드"),
    ("--color-text-secondary", "--color-surface-base", 4.5, "보조 텍스트/화면 바탕"),
    ("--color-text-secondary", "--color-surface-raised", 4.5, "보조 텍스트/카드"),
    ("--color-text-on-accent", "--color-accent", 4.5, "CTA 버튼 글자"),
    ("--color-text-on-accent", "--color-accent-strong", 4.5, "눌린 CTA 글자"),
    ("--color-accent-text", "--color-surface-base", 4.5, "링크/화면 바탕"),
    ("--color-accent-text", "--color-surface-accent", 4.5, "선택된 칩 글자"),
    ("--color-warning-text", "--color-surface-base", 4.5, "경고 문구"),
    ("--color-danger-text", "--color-surface-base", 4.5, "오류 문구"),
    ("--color-success-text", "--color-surface-base", 4.5, "성공 문구"),
    ("--color-text-on-fill", "--color-warning-fill", 4.5, "경고 뱃지 안 글자"),
    ("--color-text-on-fill", "--color-danger-fill", 4.5, "오류 뱃지 안 글자"),
    ("--color-text-on-fill", "--color-success-fill", 4.5, "성공 뱃지 안 글자"),
]

UI_PAIRS = [
    ("--color-accent", "--color-surface-base", 3.0, "액센트 면/화면 바탕"),
    ("--color-border-strong", "--color-surface-base", 3.0, "입력 필드 테두리"),
    ("--color-focus-ring", "--color-surface-base", 3.0, "키보드 포커스 링"),
    ("--color-danger-fill", "--color-surface-base", 3.0, "단독 삭제 아이콘"),
]

ALL_PAIRS = TEXT_PAIRS + UI_PAIRS


@pytest.mark.parametrize("fg,bg,need,label", ALL_PAIRS)
def test_light_theme_contrast(light, fg, bg, need, label):
    ratio = contrast(light[fg], light[bg])
    assert ratio >= need, (
        f"라이트 - {label}: {light[fg]} on {light[bg]} = {ratio:.2f}:1 (필요 {need}:1)"
    )


@pytest.mark.parametrize("fg,bg,need,label", ALL_PAIRS)
def test_dark_theme_contrast(dark, fg, bg, need, label):
    ratio = contrast(dark[fg], dark[bg])
    assert ratio >= need, (
        f"다크 - {label}: {dark[fg]} on {dark[bg]} = {ratio:.2f}:1 (필요 {need}:1)"
    )


# ---------- 구조 검증 ----------

def test_dark_blocks_are_identical(css):
    """다크 값을 두 곳(시스템 설정 따름 / 명시적 선택)에 적어두므로 어긋날 수 있다.
    한쪽만 고치면 토글했을 때 색이 달라지는데, 눈으로는 잘 안 보인다."""
    media = _parse_vars(_block_after(css, DARK_MEDIA_SELECTOR))
    explicit = _parse_vars(_block_after(css, DARK_EXPLICIT_SELECTOR))
    assert media == explicit, "다크 모드 두 블록의 값이 다르다"


def test_every_dark_override_exists_in_light(light, css):
    """다크에서만 튀어나온 토큰이 있으면 라이트에서 값이 없어 깨진다."""
    explicit = _parse_vars(_block_after(css, DARK_EXPLICIT_SELECTOR))
    missing = sorted(set(explicit) - set(light))
    assert not missing, f"라이트에 없는 토큰이 다크에만 있다: {missing}"


def test_touch_target_meets_44px(light):
    """V2에서 이미 적용한 기준이라 되돌아가지 않도록 못박는다 (rem 기준 16px 루트)."""
    value = light["--touch-target-min"]
    assert value.endswith("rem")
    assert float(value.removesuffix("rem")) * 16 >= 44


def test_body_line_height_is_generous_enough_for_korean(light):
    """한글은 네모꼴로 꽉 차서 라틴 기준 행간(1.4~1.5)이면 답답하게 읽힌다."""
    assert float(light["--line-height-base"]) >= 1.55


def test_spacing_scale_is_multiples_of_four(light):
    for name, value in light.items():
        if not name.startswith("--space-"):
            continue
        px = float(value.removesuffix("rem")) * 16
        assert px % 4 == 0, f"{name}={value} 는 4px 배수가 아니다"
