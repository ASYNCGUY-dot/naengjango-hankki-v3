"""알레르기 태그를 파생 재료까지 포함해 다시 매긴다 (2026-08-19).

왜 필요한가
--------
`tagging_agent.tag_allergy()`는 원래 알레르겐 이름이 재료 텍스트에 **그대로** 들어
있어야만 태그를 붙였다. 그런데 "치즈"에는 "우유"라는 글자가 없고 "두부"에는 "대두"가
없다. 운영 DB에서 실제 추천 경로로 재니 이랬다.

    대두 알레르기 선택 -> 두부가 든 레시피 153개 중 153개가 그대로 추천됨
    우유 -> 치즈가 든 101개 중 71개
    밀   -> 소면이 든 4개 중 4개
    계란 -> 마요네즈가 든 47개 중 31개

이 앱은 알레르기가 있는 재료를 빼주겠다고 사용자에게 약속한다. 태깅이 새면 뒤의
필터가 아무리 정확해도 소용이 없다. `ALLERGEN_DERIVED`를 tagging_agent에 넣었고,
이 스크립트가 기존 레시피에 그 기준을 소급 적용한다.

반대 방향도 함께 고친다. "게"를 문자열 포함으로 찾으면 스파게티·바게트·얇게·굵게가
전부 걸린다. 실제로 42개 레시피에 게 태그가 붙어 있었는데 전부 이런 오탐이었다.
게 알레르기가 있는 사람이 이유 없이 파스타를 못 보게 된다.

무엇을 근거로 다시 매기나
--------
`recipes`는 원본 재료 텍스트(RCP_PARTS_DTLS)를 보관하지 않는다. 그래서 지금 DB에
남아 있는 것으로 텍스트를 복원한다 - `recipe_ingredients.name`과 `recipe_tags`의
ingredient 태그를 합친다. 재료명이 근거이므로 원본보다 좁지만, 태깅이 보는 정보도
결국 재료명이라 실질적인 차이는 거의 없다.

사용법
--------
    .venv/Scripts/python.exe migration/008_retag_allergens.py --dry-run   # 무엇이 바뀌는지만
    .venv/Scripts/python.exe migration/008_retag_allergens.py             # 실제 적용

--dry-run이 기본이 아니다. 그래도 적용 전에 되돌릴 파일(백업)을 항상 먼저 쓴다.
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

from src.agents.tagging_agent import LITERAL_MATCH_EXCLUDED, tag_allergy  # noqa: E402

DRY_RUN = "--dry-run" in sys.argv


def load_recipe_texts(cur) -> dict[int, str]:
    """레시피별 재료 텍스트를 복원한다. 태깅이 보는 것과 같은 재료명이 근거다."""
    texts: dict[int, list[str]] = {}
    cur.execute("SELECT recipe_id, name FROM recipe_ingredients")
    for recipe_id, name in cur.fetchall():
        texts.setdefault(recipe_id, []).append(name or "")
    cur.execute("SELECT recipe_id, tag_value FROM recipe_tags WHERE tag_type = 'ingredient'")
    for recipe_id, value in cur.fetchall():
        texts.setdefault(recipe_id, []).append(value or "")
    return {rid: " ".join(parts) for rid, parts in texts.items()}


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
    removed: list[tuple[int, str]] = []
    kept: list[tuple[int, str]] = []
    for recipe_id in recipes:
        before = current.get(recipe_id, set())
        after = set(tag_allergy(texts.get(recipe_id, "")))
        for tag in sorted(after - before):
            added.append((recipe_id, tag))
        for tag in sorted(before - after):
            # 제거는 딱 한 가지 이유로만 한다: "게"를 문자열 포함으로 찾던 오탐.
            #
            # 나머지 차이는 이 스크립트가 원본 재료 텍스트(RCP_PARTS_DTLS)를 복원한
            # 결과가 원본보다 좁아서 생긴다. 드라이런에서 "수삼매운닭찜 -닭고기"처럼
            # 진짜 보호가 사라지는 경우가 실제로 나왔다. 태깅을 고치러 와서 보호를
            # 걷어내면 안 되므로, 설명되지 않는 차이는 손대지 않고 남긴다.
            if tag in LITERAL_MATCH_EXCLUDED:
                removed.append((recipe_id, tag))
            else:
                kept.append((recipe_id, tag))

    print(f"레시피 {len(recipes)}개 검사")
    print(f"  추가할 태그 {len(added)}개")
    for tag, n in Counter(t for _, t in added).most_common():
        print(f"      +{tag} {n}건")
    print(f"  제거할 태그 {len(removed)}개 (오탐이 확인된 것만)")
    for tag, n in Counter(t for _, t in removed).most_common():
        print(f"      -{tag} {n}건")
    if kept:
        print(f"  차이가 있지만 남기는 태그 {len(kept)}개 (복원 텍스트가 원본보다 좁아서 생긴 차이)")
        for tag, n in Counter(t for _, t in kept).most_common():
            print(f"      ={tag} {n}건")

    # 제거는 보호를 걷어내는 방향이라 전부 눈으로 확인할 수 있게 찍는다.
    if removed:
        print("\n제거 대상 전체 (보호를 없애는 방향이라 전부 나열한다):")
        for recipe_id, tag in removed:
            print(f"      {recipe_id:5} {recipes[recipe_id][:30]:32} -{tag}")

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
        f.write("-- 008 적용 직전의 allergy 태그 전체. 되돌리려면:\n")
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
    for recipe_id, tag in removed:
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
