"""KAMIS 재료비가 레시피 재료에 얼마나 붙는지를 같은 레시피·같은 시세로 다시 잰다 (2026-10-18).

왜 필요한가
--------
공모전 초안과 PROJECT_REPORT_V3.md의 전후 비교 수치는 임시 폴더의 일회용 스크립트로 쟀다. 외부
검토 인계서(2026-10-15, 작업 E)가 짚은 대로, 원자료·재현 조건 없이 남은 숫자는 남이 다시 낼 수
없다. 그리고 이 측정은 세 번 틀렸다(§4.5 "이 표는 세 번 틀렸다") - 입력을 옛 코드가 실제로
받던 대로 주지 않았고, 분모가 달랐고, 옛 코드가 쓰던 부품(조미료 판정)을 지금 것으로 돌렸다.
그 조건을 이 스크립트가 고정한다.

무엇을 재나
--------
- 분모: 승인된 레시피의 재료 행 중 재료(구획 제목·안내 문구 제외)이고 조미료가 아닌 행.
  모든 버전에 **같은 분모**를 쓴다(조미료 판정은 지금 코드 기준)
- 시세가 붙는 행: 매칭되고, 다른 부위·상태(other_cut·other_state)로 빠지지 않은 행
- 재료비에 재료가 3개 이상 / 1개 이상 들어가는 레시피의 비율(1인분 기준)
- 매칭 근거별 행 수와 다른 부위·상태로 뺀 재료

**범위이지 정확도가 아니다.** 정확도는 --sample로 뽑은 표본을 사람이 판정해서 따로 낸다.

같은 조건으로 비교하는 법
--------
시세 한 벌(스냅샷)을 저장하고 그것으로 여러 코드 버전을 돌린다. --ref로 준 버전은 지금 작업
트리와 같은 스냅샷·같은 입력(이름 정리, 구획 제목 제외)을 받는다 - 2026-10-08(d677f2c) 이후
코드에 맞는 입력이다.

9월 개편 전 코드(--legacy-ref)는 도매가·4부류라 같은 스냅샷을 쓸 수 없어서 자기 시세를 직접
받는다. 결과에 "시세 조건이 다름"으로 따로 적는다. 그 코드는 당시 라우터가 넘기던 원래 이름을
받고, 당시 추천 쪽 조미료 판정(부분 문자열)을 쓴다. 그리고 일요일을 조회 날짜로 주면 멈추므로
(§4.5 일요일 장애) --legacy-date로 평일 날짜를 준다.

운영 DB는 읽기 전용으로만 연다. KAMIS 인증값은 어디에도 저장하지 않는다. 시세 스냅샷은 KAMIS
자료의 공개 재배포 조건을 확인하지 못해 저장소에 올리지 않는다(data/kamis_snapshots/는
gitignore). 결과에는 스냅샷의 sha256을 남겨 같은 스냅샷인지 대조할 수 있게 한다.

사용법
--------
    # 오늘 시세를 받아 저장하고, 10월 8일 코드·9월 개편 전 코드와 비교한다
    .venv/Scripts/python.exe scripts/measure_kamis_coverage.py \\
        --save-snapshot data/kamis_snapshots/2026-10-18.json \\
        --ref fe1c6e6 --legacy-ref 6b6cd3a~1 --legacy-date 2026-10-16 \\
        --sample 20 --out docs/evidence/2026-10-18_kamis_coverage

    # 저장해 둔 같은 시세로 다시 잰다
    .venv/Scripts/python.exe scripts/measure_kamis_coverage.py \\
        --snapshot data/kamis_snapshots/2026-10-18.json --ref fe1c6e6
"""

import argparse
import csv
import datetime as dt
import hashlib
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src" / "agents"))

import psycopg2  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import portion_agent  # noqa: E402
import price_agent as current  # noqa: E402
from recommendation_agent import STAPLE_SEASONINGS  # noqa: E402

# 추천 쪽 조미료 판정을 "끝나는 말"로 바꾼 커밋. 이보다 앞선 코드는 부분 문자열 판정을 썼다.
STAPLE_RULE_CHANGED_AT = "23b84c4"
SUBSTITUTES = ("other_cut", "other_state")
SAMPLE_SEED = 20261018


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=True).stdout


def load_price_agent_at(ref: str):
    """git의 ref 시점 price_agent.py를 모듈로 불러온다. 지금 작업 트리의 다른 모듈을 함께 쓴다."""
    source = git("show", f"{ref}:src/agents/price_agent.py")
    tmp = Path(tempfile.mkdtemp()) / "price_agent_at_ref.py"
    tmp.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(f"price_agent_{ref.replace('~', '_')}", tmp)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def is_before(ref: str, commit: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", ref, f"{commit}~1"], cwd=ROOT).returncode == 0


def fixed_date(day: str):
    year, month, date = (int(x) for x in day.split("-"))

    class FixedDate(dt.date):
        @classmethod
        def today(cls):
            return cls(year, month, date)

    return FixedDate


def load_dataset() -> dict:
    """승인된 레시피의 재료 행을 읽기 전용으로 읽는다."""
    conn = psycopg2.connect(os.environ["POSTGRES_URL"])
    conn.set_session(readonly=True)
    cur = conn.cursor()
    cur.execute(
        "SELECT ri.recipe_id, ri.name, ri.amount, ri.unit, ri.raw_text, ri.base_servings "
        "FROM recipe_ingredients ri JOIN recipes r ON r.id = ri.recipe_id WHERE r.status = 'approved' "
        "ORDER BY ri.recipe_id, ri.id"
    )
    rows = cur.fetchall()
    conn.close()
    by_recipe = defaultdict(list)
    for rid, name, amount, unit, raw_text, base in rows:
        by_recipe[rid].append({"name": name, "amount": amount, "unit": unit, "raw_text": raw_text, "base": base})
    # 같은 데이터셋인지 대조할 지문. 레시피 번호·재료 이름·양·단위만 쓴다.
    lines = sorted(f"{rid}|{name}|{amount}|{unit}" for rid, name, amount, unit, _, _ in rows)
    fingerprint = hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()
    return {"by_recipe": by_recipe, "rows": len(rows), "fingerprint": fingerprint}


def cleaned(rows: list[dict]) -> list[dict]:
    """2026-10-08 이후 라우터가 넘기는 입력: 이름을 정리하고 구획 제목·안내 문구를 뺀다."""
    out = [{**r, "name": portion_agent.display_name(r["name"])} for r in rows]
    return [r for r in out if portion_agent.classify_ingredient_row(r["name"], r["amount"]) == "ingredient"]


def denominator(by_recipe: dict) -> list[tuple[str, str]]:
    """(원래 이름, 정리한 이름). 모든 버전에 같은 분모를 쓴다."""
    out = []
    for rows in by_recipe.values():
        for r in rows:
            shown = portion_agent.display_name(r["name"])
            if portion_agent.classify_ingredient_row(shown, r["amount"]) != "ingredient":
                continue
            if current.is_price_staple(shown):
                continue
            out.append((r["name"], shown))
    return out


def measure(module, items: list[dict], by_recipe: dict, denom: list, raw_input: bool) -> dict:
    def priced(name: str) -> bool:
        m = module.match_ingredient_price(name, items)
        return m is not None and m.get("match_basis") not in SUBSTITUTES

    hit = sum(1 for raw, shown in denom if priced(raw if raw_input else shown))
    three = one = 0
    bases, substitutes = Counter(), Counter()
    for rows in by_recipe.values():
        given = rows if raw_input else cleaned(rows)
        if not given:
            continue
        scaled = portion_agent.scale_ingredients(given, given[0]["base"] or 1, 1)
        result = module.estimate_recipe_total_cost(scaled, items)
        included = result["included"]
        three += len(included) >= 3
        one += len(included) >= 1
        bases.update(i.get("match_basis", "(구분 없음)") for i in included)
        substitutes.update(e["ingredient"] for e in result["excluded"] if e.get("reason_code") in SUBSTITUTES)
    recipes = len(by_recipe)
    return {
        "priced_rows": hit,
        # 비율은 반올림하지 않고 둔다. 먼저 반올림한 뒤 다시 %로 반올림하면 48.25%가 48.2%로 나온다.
        "priced_rows_rate": hit / len(denom),
        "recipes_with_3plus": three,
        "recipes_with_3plus_rate": three / recipes,
        "recipes_with_1plus": one,
        "recipes_with_1plus_rate": one / recipes,
        "included_rows_by_basis": dict(bases),
        "substitute_rows": sum(substitutes.values()),
        "substitutes_top": substitutes.most_common(30),
    }


def sample_matches(items: list[dict], by_recipe: dict, per_class: int) -> list[dict]:
    """위험 유형별로 서로 다른 (재료, 적용 품목) 쌍을 뽑는다. 판정은 사람이 채운다."""
    pairs = defaultdict(Counter)
    detail = {}
    for rows in by_recipe.values():
        scaled = portion_agent.scale_ingredients(cleaned(rows), (rows[0]["base"] or 1) if rows else 1, 1)
        result = current.estimate_recipe_total_cost(scaled, items)
        for i in result["included"]:
            if i["is_estimated"]:
                group = "개수→무게 추정"
            elif i["match_basis"] == "representative":
                group = "대표값(부위·품종 미지정)"
            elif i["matched_name"].startswith(current._NOT_FRESH_PREFIXES):
                group = "말린 품목"
            elif any(it["item_name"] == i["matched_name"] and it["category_code"] == "500" for it in items):
                group = "축산물"
            else:
                group = "그 밖의 정확 매칭"
            key = (i["ingredient"], i["matched_name"], i.get("matched_kind"))
            pairs[group][key] += 1
            detail[key] = {"unit": i.get("unit"), "unit_price": i.get("unit_price"), "match_basis": i.get("match_basis")}
        for e in result["excluded"]:
            if e.get("reason_code") in SUBSTITUTES:
                key = (e["ingredient"], e["reason"], None)
                pairs["다른 부위·상태로 뺀 것"][key] += 1
                detail[key] = {"unit": None, "unit_price": None, "match_basis": e["reason_code"]}
    rng = random.Random(SAMPLE_SEED)
    out = []
    for group in sorted(pairs):
        keys = sorted(pairs[group])
        for key in sorted(rng.sample(keys, min(per_class, len(keys)))):
            name, matched, kind = key
            out.append({
                "분류": group, "재료명": name, "적용 품목(또는 뺀 이유)": matched, "적용 품종": kind or "",
                "단위": detail[key]["unit"] or "", "단가(원)": detail[key]["unit_price"] or "",
                "근거": detail[key]["match_basis"], "등장 횟수": pairs[group][key],
                "판정(1차)": "", "판정 이유": "", "판정(사람)": "",
            })
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--snapshot", help="저장해 둔 KAMIS 시세 스냅샷(JSON)으로 잰다")
    parser.add_argument("--save-snapshot", help="오늘 시세를 받아 이 경로에 저장하고 그것으로 잰다")
    parser.add_argument("--ref", action="append", default=[], help="같은 스냅샷으로 비교할 git ref(여러 번 줄 수 있다)")
    parser.add_argument("--legacy-ref", help="도매·4부류였던 9월 개편 전 코드의 git ref(자기 시세를 직접 받는다)")
    parser.add_argument("--legacy-date", help="9월 개편 전 코드에 줄 조회 날짜(YYYY-MM-DD, 평일)")
    parser.add_argument("--sample", type=int, default=0, help="위험 유형별 표본 수(0이면 뽑지 않는다)")
    parser.add_argument("--out", help="결과를 쓸 폴더(results.json, sample.csv)")
    args = parser.parse_args()

    if not os.getenv("POSTGRES_URL"):
        print("POSTGRES_URL이 비어 있습니다. .env를 확인하세요.")
        return 1
    if args.snapshot and args.save_snapshot:
        print("--snapshot과 --save-snapshot은 함께 쓸 수 없습니다.")
        return 1

    if args.snapshot:
        snapshot_bytes = Path(args.snapshot).read_bytes()
        items = json.loads(snapshot_bytes)
    else:
        items = current.get_all_prices()
        snapshot_bytes = json.dumps(items, ensure_ascii=False, sort_keys=True, indent=1).encode("utf-8")
        if args.save_snapshot:
            Path(args.save_snapshot).parent.mkdir(parents=True, exist_ok=True)
            Path(args.save_snapshot).write_bytes(snapshot_bytes)
    snapshot_sha = hashlib.sha256(snapshot_bytes).hexdigest()

    data = load_dataset()
    denom = denominator(data["by_recipe"])
    head = git("rev-parse", "HEAD").strip()
    dirty = bool(git("status", "--porcelain", "--", "src", "api"))

    results = {
        "measured_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "kamis": {
            "action": "dailyPriceByCategoryList", "region": "서울(1101)", "distribution": "소매(01)",
            "categories": list(current.CATEGORY_CODES.values()), "kg_convert": "Y(무게 단위는 1kg당으로 맞춤)",
            "items": len(items), "price_days": Counter(i.get("price_day") for i in items).most_common(),
            "snapshot_sha256": snapshot_sha, "snapshot_file": args.snapshot or args.save_snapshot,
        },
        "dataset": {
            "recipes": len(data["by_recipe"]), "ingredient_rows": data["rows"], "denominator_rows": len(denom),
            "fingerprint_sha256": data["fingerprint"],
        },
        "versions": [],
    }

    def add(label: str, ref: str, sha: str, module, version_items, raw_input: bool, same_snapshot: bool):
        metrics = measure(module, version_items, data["by_recipe"], denom, raw_input)
        results["versions"].append({
            "label": label, "ref": ref, "sha": sha, "input": "원래 이름" if raw_input else "이름 정리·구획 제목 제외",
            "same_snapshot": same_snapshot, **metrics,
        })
        print(f"[{label}] 시세 붙는 행 {metrics['priced_rows']}/{len(denom)} = {metrics['priced_rows_rate']:.1%} | "
              f"재료비 3개+ {metrics['recipes_with_3plus_rate']:.1%} | 1개+ {metrics['recipes_with_1plus_rate']:.1%}")

    if args.legacy_ref:
        legacy = load_price_agent_at(args.legacy_ref)
        if is_before(args.legacy_ref, STAPLE_RULE_CHANGED_AT):
            legacy.is_staple = lambda name: any(s in (name or "") for s in STAPLE_SEASONINGS)
        if args.legacy_date:
            legacy.date = fixed_date(args.legacy_date)
        legacy_items = legacy.get_all_prices()
        add("9월 개편 전(도매·4부류, 시세 조건이 다름)", args.legacy_ref, git("rev-parse", args.legacy_ref).strip(),
            legacy, legacy_items, raw_input=True, same_snapshot=False)
    for ref in args.ref:
        add(f"코드 {ref}", ref, git("rev-parse", ref).strip(), load_price_agent_at(ref), items, raw_input=False, same_snapshot=True)
    add("지금 작업 트리" + (" (커밋 안 된 변경 있음)" if dirty else ""), "HEAD", head, current, items,
        raw_input=False, same_snapshot=True)

    print(f"데이터셋: 레시피 {results['dataset']['recipes']}개, 분모 {len(denom)}행, 지문 {data['fingerprint'][:12]}")
    print(f"시세: {len(items)}개, 스냅샷 {snapshot_sha[:12]}")

    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print("저장:", out / "results.json")
        if args.sample:
            sample = sample_matches(items, data["by_recipe"], args.sample)
            with (out / "sample.csv").open("w", encoding="utf-8-sig", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=list(sample[0].keys()))
                writer.writeheader()
                writer.writerows(sample)
            print("저장:", out / "sample.csv", f"({len(sample)}행)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
