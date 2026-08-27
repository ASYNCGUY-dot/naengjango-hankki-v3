"""고기류 알레르기 태그를 부위 이름까지 포함해 다시 매긴다 (2026-08-22).

왜 필요한가
--------
지인 테스트 첫 제보가 이것이었다.

    "돼지고기 알러지 체크했는데 돼지머리 어쩌구 왜 추천하냐?"

확인해보니 사실이었다. 그 사람은 알레르기에 `달걀,우유,돼지고기`를 넣었고, 추천에서
163번 `돼지머리수육맑은전골`을 열었다. 이 레시피의 재료는 "돼지머리 200g"인데
`recipe_tags`에는 대두와 밀만 붙어 있었다. **"돼지머리"에 "돼지고기"라는 글자가 없기
때문이다.**

008에서 고쳤던 것과 정확히 같은 종류의 구멍이다("치즈"에 "우유"가 없다). 그때는
우유·밀·대두·계란·게만 채웠고 고기류를 안 봤다. 부위 이름에는 축종 이름이 안 들어간다 -
삼겹살·목살·베이컨·햄·족발에 "돼지고기"가 없고, 차돌박이·사골육수·우둔살에 "소고기"가
없고, 닭가슴살·치킨스톡에 "닭고기"가 없다.

운영 DB에서 실측한 누락:

    돼지고기 59개 / 소고기 12개 / 닭고기 92개 / 새우 3개 / 오징어 1개 /
    토마토 8개 / 복숭아 1개

반대 방향(과잉 차단)도 같이 고친다. "땅콩호박"에는 "땅콩"이, "굴림만두"에는 "굴"이,
"코코넛밀크"에는 "밀"이 들어 있다. 다만 **"메밀"과 "오트밀"은 일부러 안 건드린다** -
시판 메밀면은 밀가루를 섞는 경우가 많아서, 이름만 보고 밀 태그를 떼면 보호가 진짜로
사라진다.

제거를 어떻게 다루나 (008과 달라진 점)
--------
008은 제거를 `LITERAL_MATCH_EXCLUDED`("게") 하나로만 허용했다. 복원한 재료 텍스트가
원본(RCP_PARTS_DTLS)보다 좁아서, "이제 안 걸린다"가 곧 "오탐이었다"를 뜻하지 않기
때문이다. 실제로 드라이런에서 "수삼매운닭찜 -닭고기"처럼 진짜 보호가 사라질 뻔했다.

이번 변경은 이름 매칭에도 예외를 걸어서 태그가 줄어들 수 있다. 그래서 제거 조건을
하나 더 두되 **근거를 요구한다**: 그 레시피의 재료 텍스트에 이번에 넣은 예외 단어가
실제로 들어 있어야 한다. 근거 없는 차이는 008과 똑같이 남긴다.

사용법
--------
    .venv/Scripts/python.exe migration/011_retag_meat_allergens.py --dry-run
    .venv/Scripts/python.exe migration/011_retag_meat_allergens.py

--dry-run이 기본이 아니다. 그래도 적용 전에 되돌릴 파일(백업)을 항상 먼저 쓴다.
008을 이미 적용한 DB 위에서 돌린다.
"""

import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from src.agents.tagging_agent import (  # noqa: E402
    DERIVED_EXCEPTIONS,
    LITERAL_MATCH_EXCLUDED,
    tag_allergy,
)

DRY_RUN = "--dry-run" in sys.argv


def load_recipe_texts(cur) -> dict[int, str]:
    """레시피별 재료 텍스트를 복원한다 (008과 같은 방식이라야 결과를 비교할 수 있다)."""
    texts: dict[int, list[str]] = {}
    cur.execute("SELECT recipe_id, name FROM recipe_ingredients")
    for recipe_id, name in cur.fetchall():
        texts.setdefault(recipe_id, []).append(name or "")
    cur.execute("SELECT recipe_id, tag_value FROM recipe_tags WHERE tag_type = 'ingredient'")
    for recipe_id, value in cur.fetchall():
        texts.setdefault(recipe_id, []).append(value or "")
    return {rid: " ".join(parts) for rid, parts in texts.items()}


def removal_reason(tag: str, text: str) -> str | None:
    """이 태그를 지워도 되는 이유가 있으면 그 이유를, 없으면 None을 준다."""
    if tag in LITERAL_MATCH_EXCLUDED:
        return "이름 매칭 자체가 오탐"
    for word in DERIVED_EXCEPTIONS.get(tag, ()):
        if word in text:
            return f"예외 단어 '{word}'"
    return None


def main() -> int:
    conn = psycopg2.connect(os.environ["POSTGRES_URL"])
    cur = conn.cursor()

    cur.execute("SELECT id, menu_name FROM recipes")
    recipes = dict(cur.fetchall())
    texts = load_recipe_texts(cur)

    cur.execute("SELECT recipe_id, tag_value FROM recipe_tags WHERE tag_type = 'allergy'")
    current: dict[int, set[str]] = {}
    for recipe_id, value in cur.fetchall():
        current.setdefault(recipe_id, set()).add(value)

    added: list[tuple[int, str]] = []
    removed: list[tuple[int, str, str]] = []
    kept: list[tuple[int, str]] = []
    for recipe_id in recipes:
        text = texts.get(recipe_id, "")
        before = current.get(recipe_id, set())
        after = set(tag_allergy(text))
        for tag in sorted(after - before):
            added.append((recipe_id, tag))
        for tag in sorted(before - after):
            reason = removal_reason(tag, text)
            if reason:
                removed.append((recipe_id, tag, reason))
            else:
                # 복원 텍스트가 원본보다 좁아서 생긴 차이다. 태깅을 고치러 와서 보호를
                # 걷어내면 안 되므로 설명되지 않는 차이는 손대지 않는다.
                kept.append((recipe_id, tag))

    print(f"레시피 {len(recipes)}개 검사")
    print(f"  추가할 태그 {len(added)}개")
    for tag, n in Counter(t for _, t in added).most_common():
        print(f"      +{tag} {n}건")
    print(f"  제거할 태그 {len(removed)}개 (근거가 확인된 것만)")
    for tag, n in Counter(t for _, t, _ in removed).most_common():
        print(f"      -{tag} {n}건")
    if kept:
        print(f"  차이가 있지만 남기는 태그 {len(kept)}개 (복원 텍스트가 원본보다 좁아서 생긴 차이)")
        for tag, n in Counter(t for _, t in kept).most_common():
            print(f"      ={tag} {n}건")

    # 제거는 보호를 걷어내는 방향이라 전부 눈으로 확인할 수 있게 찍는다.
    if removed:
        print("\n제거 대상 전체 (보호를 없애는 방향이라 전부 나열한다):")
        for recipe_id, tag, reason in removed:
            print(f"      {recipe_id:5} {recipes[recipe_id][:26]:28} -{tag:5} {reason}")

    if DRY_RUN:
        print("\n--dry-run 이므로 아무것도 바꾸지 않았다.")
        conn.close()
        return 0

    if not added and not removed:
        print("\n바뀔 것이 없다.")
        conn.close()
        return 0

    # 되돌릴 수 있게 지금 상태를 먼저 떠둔다. 무료 플랜에는 백업 기능이 없다(005 참고).
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup = ROOT / f"backup_allergy_tags_{stamp}.sql"
    with backup.open("w", encoding="utf-8") as f:
        f.write("-- 011 적용 직전의 allergy 태그 전체. 되돌리려면:\n")
        f.write("--   DELETE FROM recipe_tags WHERE tag_type = 'allergy';\n")
        f.write("--   그 다음 이 파일을 실행한다.\n")
        for recipe_id, tags in sorted(current.items()):
            for tag in sorted(tags):
                safe = tag.replace("'", "''")
                f.write(
                    "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) "
                    f"VALUES ({recipe_id}, 'allergy', '{safe}');\n"
                )
    print(f"\n백업: {backup.name}")

    for recipe_id, tag in added:
        cur.execute(
            "INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (%s, 'allergy', %s)",
            (recipe_id, tag),
        )
    for recipe_id, tag, _ in removed:
        cur.execute(
            "DELETE FROM recipe_tags WHERE recipe_id = %s AND tag_type = 'allergy' AND tag_value = %s",
            (recipe_id, tag),
        )
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM recipe_tags WHERE tag_type = 'allergy'")
    print(f"적용 완료. allergy 태그 총 {cur.fetchone()[0]}개")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
