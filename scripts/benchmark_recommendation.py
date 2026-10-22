"""로컬 공개 레시피로 이전 커밋과 점수·순서 및 실행 시간을 비교한다. DB는 읽기 전용.

실행: .venv/Scripts/python.exe scripts/benchmark_recommendation.py --database data/app.db
운영 HTTP 시간과는 별개인 로컬 측정이며 개인별 프로필·냉장고는 읽지 않는다.
"""

import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import time
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agents import recommendation_agent as current  # noqa: E402

INPUTS = [
    ["두부", "양파", "달걀"],
    ["고등어", "갈치", "참치", "전지", "양배추", "깻잎"],
    ["닭가슴살", "양파", "당근", "감자"],
    ["소고기", "돼지고기", "새우", "오징어"],
    ["소금", "간장", "다진마늘"], [],
    ["주재료", "[주재료]닭가슴살", "1인분기준<br>"],
]


def clear_caches(module):
    for value in vars(module).values():
        if hasattr(value, "cache_clear"):
            value.cache_clear()


def fingerprint(value):
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--baseline", default="95353f9")
    parser.add_argument("--runs", type=int, default=9)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.runs < 3:
        parser.error("--runs는 3 이상이어야 한다")
    source = subprocess.run(
        ["git", "show", f"{args.baseline}:src/agents/recommendation_agent.py"],
        cwd=ROOT, check=True, capture_output=True, encoding="utf-8",
    ).stdout
    before = types.ModuleType("recommendation_before_cache")
    exec(compile(source, "recommendation_before_cache.py", "exec"), before.__dict__)
    with sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True) as conn:
        conn.execute("PRAGMA query_only = ON")
        candidates = current.get_candidate_recipes(conn.cursor(), {})
        ids = [c["id"] for c in candidates]
        if not ids:
            raise RuntimeError("비교할 승인 레시피가 없다")
        markers = ",".join("?" for _ in ids)
        tags = conn.execute(
            f"SELECT recipe_id, tag_type, tag_value FROM recipe_tags WHERE recipe_id IN ({markers}) "
            "ORDER BY recipe_id, tag_type, tag_value", ids,
        ).fetchall()
        rows = conn.execute(
            f"SELECT recipe_id, name, amount, unit FROM recipe_ingredients WHERE recipe_id IN ({markers}) "
            "ORDER BY recipe_id, name, amount, unit", ids,
        ).fetchall()
        comparison = []
        for names in INPUTS:
            clear_caches(before)
            clear_caches(current)
            expected = before.score_by_ingredients(conn.cursor(), deepcopy(candidates), names)
            actual = current.score_by_ingredients(conn.cursor(), deepcopy(candidates), names)
            warm = current.score_by_ingredients(conn.cursor(), deepcopy(candidates), names)
            if expected != actual or expected != warm:
                raise AssertionError(f"추천 결과 불일치: {names}")
            comparison.append({"ingredients": names, "result_sha256": fingerprint(actual), "identical": True})
        timings = {}
        names = INPUTS[1]
        for label, module in (("before", before), ("after", current)):
            samples = {"cold": [], "warm": []}
            for _ in range(args.runs):
                clear_caches(module)
                for phase in ("cold", "warm"):
                    start = time.perf_counter()
                    module.score_by_ingredients(conn.cursor(), deepcopy(candidates), names)
                    samples[phase].append(time.perf_counter() - start)
            timings[label] = {phase: {"median_seconds": statistics.median(values), "samples_seconds": values}
                              for phase, values in samples.items()}
    result = {
        "measured_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "baseline": args.baseline, "environment": "local SQLite read-only; scoring incl. two SQL reads",
        "python": sys.version.split()[0], "recipes": len(candidates), "ingredient_rows": len(rows),
        "dataset_sha256": fingerprint([candidates, tags, rows]), "runs": args.runs,
        "comparison": comparison, "timings": timings,
        "limitation": "운영 HTTP·Render CPU·네트워크 측정이 아님",
    }
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
