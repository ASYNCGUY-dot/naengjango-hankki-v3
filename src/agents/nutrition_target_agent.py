"""
Nutrition Target Agent [확장] - 개인 맞춤 영양 기준 비교
- 역할: 유저 프로필(성별·연령대)의 공식 권장섭취량과, 복용 중인 영양제가 이미 채워주고
        있을 영양소를 참고해서, 추천된 레시피가 그 사람에게 어떤 영양소를 채워주는지
        (혹은 이미 충분한지) 계산한다.
- 데이터 출처: "2025 한국인 영양소 섭취기준" (보건복지부·한국영양학회, 2020년판 개정본).
  이 프로젝트가 이미 DB에 저장 중인 영양소(칼슘, 철, 칼륨, 비타민A, 비타민C, 아연,
  단백질, 나트륨) 중, 위 자료에서 연령대·성별별 권장섭취량(RNI)을 안정적으로 읽어낼 수
  있는 항목만 담았다. 칼륨은 공식 자료의 표 구조가 복잡해(다른 무기질과 셀이 겹쳐 보여)
  숫자를 확신할 수 없어 이번 버전에서는 제외했다 - 추측으로 숫자를 채우지 않는다는
  프로젝트 원칙(지침 "정확성 최우선, 추측 금지")을 따른 것이다. 대신 칼륨은 기존처럼
  100g당 참고치만 계속 보여준다.
- 연령대 매핑: 이 프로젝트의 프로필은 "10대/20대/30대/40대/50대 이상" 5단계인데,
  공식 자료는 "12-14/15-18/19-29/30-49/50-64/65-74/75+"세로 더 잘게 나뉜다. 완전히
  일치하지 않으니 아래처럼 대표 구간으로 근사한다 (완벽한 매핑이 목표가 아님 - 지침
  8번 원칙과 동일하게, 대표값으로 충분히 유용하다고 판단):
    10대      -> 15-18세 구간 값 사용 (10-14세와는 다를 수 있음)
    20대      -> 19-29세 구간
    30대,40대 -> 30-49세 구간 (공식 자료가 이 둘을 한 구간으로 묶어서 제공함)
    50대 이상 -> 50-64세 구간 값 사용 (65세 이상은 다를 수 있음)
- 나트륨은 "권장섭취량"이 아니라 "만성질환위험감소섭취량"(이 이하로 먹는 게 좋다는 상한
  성격의 기준, 2,300mg/일, 성별·연령 무관 공통값)이라서, 다른 영양소와 달리 "부족하니
  채우세요"가 아니라 "이미 이만큼 들어있으니 다른 끼니에서는 줄이는 게 좋다"는 식으로
  해석해야 한다. 이 차이를 화면에도 그대로 드러낸다.

- 병력정보(지병) 반영 원칙 (#67): 프로필에 체크한 지병에 따라 기준을 조정하되, 출처가
  확실한 것만 숫자를 바꾸고 나머지는 "주의 문구"로만 안내한다(추측 금지).
    · 고혈압 -> 나트륨 상한을 2,300mg에서 2,000mg으로 더 엄격하게 조정.
      출처: WHO 나트륨 섭취 권고(1일 2,000mg 미만), 2024 대한고혈압학회 가이드라인.
    · 골다공증 -> 칼슘 목표를 뼈 건강 기준으로 상향(50세 미만 1,000mg, 50세 이상 1,200mg).
      출처: 대한골대사학회 칼슘 섭취 권고안(자료마다 800~1,200mg으로 다소 차이가 있어,
      이 범위 안에서 가장 자주 인용되는 값을 썼다는 점을 화면에도 캡션으로 밝힌다).
    · 당뇨/신장질환/빈혈 -> 이 앱이 정확히 계산할 수 있는 근거(탄수화물의 공식 목표치,
      신장질환 단계별 제한, 빈혈 치료 목적의 철분 섭취량)가 없어서 숫자는 바꾸지 않고,
      "이 부분은 의료진과 상담하세요/이 항목을 더 챙겨보세요" 정도의 주의 문구만 붙인다.
      (신장질환은 특히 단계에 따라 단백질·나트륨·칼륨 제한이 크게 달라져서, 잘못된 숫자를
      보여주면 실제로 해로울 수 있다 - 절대 임의로 만들지 않는다.)
"""

# 연령대 매핑: 앱의 age_group 문자열 -> 공식 자료의 연령 구간 라벨(표시용)
AGE_GROUP_TO_BRACKET_LABEL = {
    "10대": "15-18세 기준",
    "20대": "19-29세 기준",
    "30대": "30-49세 기준",
    "40대": "30-49세 기준",
    "50대 이상": "50-64세 기준",
}

# 성별+연령대 -> 권장섭취량(RNI) / 나트륨은 만성질환위험감소섭취량(공통)
# 출처: 2025 한국인 영양소 섭취기준 요약본 (보건복지부·한국영양학회)
RDA_TABLE = {
    ("여성", "10대"): {"protein_g": 55, "calcium_mg": 700, "iron_mg": 12, "zinc_mg": 9, "vitamin_a_ug": 650, "vitamin_c_mg": 100},
    ("여성", "20대"): {"protein_g": 55, "calcium_mg": 650, "iron_mg": 12, "zinc_mg": 8, "vitamin_a_ug": 650, "vitamin_c_mg": 100},
    ("여성", "30대"): {"protein_g": 50, "calcium_mg": 650, "iron_mg": 12, "zinc_mg": 8, "vitamin_a_ug": 650, "vitamin_c_mg": 100},
    ("여성", "40대"): {"protein_g": 50, "calcium_mg": 650, "iron_mg": 12, "zinc_mg": 8, "vitamin_a_ug": 650, "vitamin_c_mg": 100},
    ("여성", "50대 이상"): {"protein_g": 50, "calcium_mg": 750, "iron_mg": 7, "zinc_mg": 8, "vitamin_a_ug": 600, "vitamin_c_mg": 100},
    ("남성", "10대"): {"protein_g": 65, "calcium_mg": 800, "iron_mg": 11, "zinc_mg": 10, "vitamin_a_ug": 850, "vitamin_c_mg": 100},
    ("남성", "20대"): {"protein_g": 65, "calcium_mg": 800, "iron_mg": 8, "zinc_mg": 10, "vitamin_a_ug": 800, "vitamin_c_mg": 100},
    ("남성", "30대"): {"protein_g": 65, "calcium_mg": 800, "iron_mg": 8, "zinc_mg": 10, "vitamin_a_ug": 800, "vitamin_c_mg": 100},
    ("남성", "40대"): {"protein_g": 65, "calcium_mg": 800, "iron_mg": 8, "zinc_mg": 10, "vitamin_a_ug": 800, "vitamin_c_mg": 100},
    ("남성", "50대 이상"): {"protein_g": 60, "calcium_mg": 800, "iron_mg": 8, "zinc_mg": 10, "vitamin_a_ug": 750, "vitamin_c_mg": 100},
}

SODIUM_LIMIT_MG = 2300  # 만성질환위험감소섭취량, 성별·연령(10대 이상) 공통

# 프로필 "병력정보" 체크박스에 쓸 옵션 (자주 겪는 것만, 지침 8번 원칙과 동일하게 완벽한
# 목록이 아니어도 됨). "없음"은 이 목록에 없어도 되고, 아무것도 안 고르면 그게 "없음"이다.
MEDICAL_CONDITION_OPTIONS = ["고혈압", "당뇨", "신장질환", "빈혈", "골다공증"]

# 고혈압: 나트륨 상한을 더 엄격하게. 출처: WHO 나트륨 섭취 권고(1일 2,000mg 미만),
# 2024 대한고혈압학회 가이드라인 - 검색으로 교차 확인함(2026-07-14 확인).
HYPERTENSION_SODIUM_LIMIT_MG = 2000

# 골다공증: 칼슘 목표를 뼈 건강 기준으로 상향. 출처: 대한골대사학회 칼슘 섭취 권고안
# (자료마다 800~1,200mg으로 다소 차이가 있음 - 아래 값은 그 중 가장 자주 인용되는
# "50세 미만 1,000mg / 50세 이상 1,200mg" 기준을 썼다).
OSTEOPOROSIS_CALCIUM_MG = {"under_50": 1000, "50_plus": 1200}
_OSTEOPOROSIS_50_PLUS_AGE_GROUPS = {"50대 이상"}

# 로그인은 했지만 프로필에 연령대/성별이 아직 없는 경우를 위한 대체값.
# "일반 성인 평균"은 20대~50대 이상 x 남/여 8개 구간의 RDA_TABLE 값을 그대로 평균낸 것으로,
# 새로운 공식 수치가 아니라 우리가 이미 갖고 있는 정확한 데이터를 요약한 값이다(추측 아님).
# 10대는 성장기라 값이 달라 평균에서 제외했다.
_ADULT_AGE_GROUPS = ["20대", "30대", "40대", "50대 이상"]
_ADULT_ENTRIES = [RDA_TABLE[(g, a)] for g in ("여성", "남성") for a in _ADULT_AGE_GROUPS]


def _average_targets(entries: list[dict]) -> dict:
    keys = entries[0].keys()
    return {k: round(sum(e[k] for e in entries) / len(entries), 1) for k in keys}


ADULT_AVERAGE_TARGETS = _average_targets(_ADULT_ENTRIES)

NUTRIENT_LABELS = {
    "protein_g": ("단백질", "g"),
    "calcium_mg": ("칼슘", "mg"),
    "iron_mg": ("철", "mg"),
    "zinc_mg": ("아연", "mg"),
    "vitamin_a_ug": ("비타민A", "μg RAE"),
    "vitamin_c_mg": ("비타민C", "mg"),
}

# 영양제 이름(자주 쓰는 것만 수동 매핑, 지침 8번 원칙) -> 이 영양제가 채워주는 것으로
# 볼 수 있는 영양소 키. 완벽한 성분표가 아니라 "대략 이 영양소는 챙기고 있다"는 참고용.
SUPPLEMENT_NUTRIENT_MAP = {
    "종합비타민": {"vitamin_a_ug", "vitamin_c_mg"},
    "멀티비타민": {"vitamin_a_ug", "vitamin_c_mg"},
    "비타민c": {"vitamin_c_mg"},
    "비타민 c": {"vitamin_c_mg"},
    "비타민a": {"vitamin_a_ug"},
    "비타민 a": {"vitamin_a_ug"},
    "칼슘": {"calcium_mg"},
    "철분": {"iron_mg"},
    "아연": {"zinc_mg"},
    "단백질보충제": {"protein_g"},
    "프로틴": {"protein_g"},
}


def get_targets(age_group: str, gender: str) -> dict | None:
    """
    프로필의 연령대·성별에 맞는 권장섭취량(RNI) 딕셔너리를 반환한다.
    매핑이 없는 값(예: 잘못된 입력)이면 None을 반환한다 - 이 경우 화면에서는
    "정보가 부족하다"고 밝히고 임의의 값으로 대체하지 않는다.
    """
    return RDA_TABLE.get((gender, age_group))


def get_bracket_label(age_group: str) -> str:
    return AGE_GROUP_TO_BRACKET_LABEL.get(age_group, "성인 기준(근사)")


def resolve_targets(age_group: str | None, gender: str | None) -> tuple[dict, str, bool]:
    """
    연령대·성별이 둘 다 있으면 정확한 RDA_TABLE 값을, 하나라도 없으면(예: 프로필에 아직
    입력 안 함) ADULT_AVERAGE_TARGETS로 대체한다.
    반환: (targets, bracket_label, is_estimated) - is_estimated=True면 "평균 추정치"라는
    뜻이므로 화면에서 그 사실을 반드시 함께 보여줘야 한다(정확한 값처럼 보이면 안 됨).
    """
    if age_group and gender:
        targets = get_targets(age_group, gender)
        if targets is not None:
            return targets, get_bracket_label(age_group), False

    return (
        ADULT_AVERAGE_TARGETS,
        "성인 평균 참고치(연령대·성별 정보 없음 - 프로필을 입력하면 더 정확해져요)",
        True,
    )


def get_supplement_coverage(supplements_text: str) -> set[str]:
    """
    "종합비타민, 오메가3" 같은 자유 입력 텍스트에서, 우리가 추적하는 영양소 중
    이미 보충제로 챙기고 있는 것으로 볼 수 있는 항목의 키 집합을 돌려준다.
    매핑에 없는 영양제(오메가3, 유산균 등)는 조용히 무시한다(추측하지 않음).
    """
    if not supplements_text or supplements_text.strip() in ("없음", "-", ""):
        return set()

    text = supplements_text.lower()
    covered = set()
    for keyword, nutrients in SUPPLEMENT_NUTRIENT_MAP.items():
        if keyword in text:
            covered |= nutrients
    return covered


def parse_conditions(medical_conditions_text: str) -> set[str]:
    """
    프로필의 병력정보 문자열("고혈압,당뇨" 처럼 콤마 구분)을 집합으로 바꾼다.
    MEDICAL_CONDITION_OPTIONS에 없는 값이 섞여 있어도(과거 데이터 등) 조용히 무시한다.
    """
    if not medical_conditions_text or not medical_conditions_text.strip():
        return set()
    return {c.strip() for c in medical_conditions_text.split(",") if c.strip() in MEDICAL_CONDITION_OPTIONS}


def apply_condition_adjustments(
    targets: dict, sodium_limit: int, conditions: set[str], age_group: str | None,
) -> tuple[dict, int, list[str]]:
    """
    병력정보에 따라 숫자를 조정할 수 있는 항목(나트륨 상한, 칼슘)만 조정하고, 나머지는
    조정 없이 주의 문구만 만든다. 원본 targets/sodium_limit는 건드리지 않고 복사본을 돌려준다.
    반환: (adjusted_targets, adjusted_sodium_limit, notes)
    """
    adjusted_targets = dict(targets)
    adjusted_sodium_limit = sodium_limit
    notes = []

    if "고혈압" in conditions:
        adjusted_sodium_limit = HYPERTENSION_SODIUM_LIMIT_MG
        notes.append(
            f"🩺 고혈압: 나트륨 상한을 하루 {HYPERTENSION_SODIUM_LIMIT_MG}mg으로 더 엄격하게 적용했습니다 "
            "(출처: WHO 권고, 2024 대한고혈압학회 가이드라인)."
        )

    if "골다공증" in conditions and "calcium_mg" in adjusted_targets:
        bucket = "50_plus" if age_group in _OSTEOPOROSIS_50_PLUS_AGE_GROUPS else "under_50"
        calcium_target = OSTEOPOROSIS_CALCIUM_MG[bucket]
        adjusted_targets["calcium_mg"] = calcium_target
        notes.append(
            f"🩺 골다공증: 칼슘 목표를 뼈 건강 기준 {calcium_target}mg으로 조정했습니다 "
            "(출처: 대한골대사학회 권고안, 자료마다 800~1,200mg으로 다소 차이가 있어요)."
        )

    if "빈혈" in conditions:
        notes.append("🩺 빈혈: 별도로 목표치를 올리지는 않았지만, 아래 철 항목을 특히 더 챙겨보세요.")

    if "당뇨" in conditions:
        notes.append(
            "🩺 당뇨: 이 앱은 아직 탄수화물·당류의 공식 목표치를 계산하지 못합니다. "
            "전체 탄수화물 섭취량과 혈당 관리는 별도로 신경써주세요."
        )

    if "신장질환" in conditions:
        notes.append(
            "🩺 신장질환: 신장질환은 단계에 따라 단백질·나트륨·칼륨 제한이 크게 달라져서, "
            "이 앱의 일반 기준과 다를 수 있습니다. 반드시 담당 의료진과 상담해서 관리하세요."
        )

    return adjusted_targets, adjusted_sodium_limit, notes


def build_nutrition_fit(
    age_group: str,
    gender: str,
    supplements_text: str,
    recipe_macro: dict,
    recipe_micro: dict,
    micro_is_partial: bool = False,
    medical_conditions_text: str = "",
) -> dict:
    """
    프로필+영양제 정보와, 이 레시피가 1인분 기준으로 제공하는 영양소량을 비교해서
    화면에 보여줄 행(row) 목록을 만든다.

    recipe_macro: {"protein_g": ..., "sodium_mg": ...} (레시피 nutrients_json에서 그대로, 1인분 기준)
    recipe_micro: {"calcium_mg": ..., "iron_mg": ..., "vitamin_a_ug": ..., "vitamin_c_mg": ..., "zinc_mg": ...}
                  (재료별 100g당 값 x 실제 사용량을 더해 1인분으로 환산한 값 - 일부 재료만
                  단위 환산이 가능해 부분 합계일 수 있다, micro_is_partial로 표시)

    medical_conditions_text: "고혈압,골다공증"처럼 콤마로 구분된 병력정보 문자열(프로필의
        medical_conditions 필드). 없으면 조정 없이 일반 기준 그대로 쓴다.

    반환: {"available": bool, "bracket_label": str, "is_estimated": bool, "rows": [...],
           "sodium_row": {...} or None, "condition_notes": [...]}
    is_estimated=True면 연령대·성별 정보가 없어서 성인 평균치로 계산했다는 뜻 - 화면에서
    반드시 그 사실을 함께 보여준다(정확한 개인 기준인 것처럼 보이면 안 됨).
    condition_notes는 병력정보에 따른 조정/주의 문구 목록(없으면 빈 리스트).
    """
    targets, bracket_label, is_estimated = resolve_targets(age_group, gender)

    conditions = parse_conditions(medical_conditions_text)
    targets, sodium_limit, condition_notes = apply_condition_adjustments(
        targets, SODIUM_LIMIT_MG, conditions, age_group
    )

    covered_by_supplement = get_supplement_coverage(supplements_text)
    combined = {**recipe_macro, **recipe_micro}

    rows = []
    for key, target_value in targets.items():
        label, unit = NUTRIENT_LABELS[key]
        provided = combined.get(key)
        if not isinstance(provided, (int, float)):
            continue  # 값이 없거나(None) 숫자가 아니면(예: 빈 문자열) 표시하지 않음(추측 금지)

        pct = round(provided / target_value * 100) if target_value else None
        already_supplemented = key in covered_by_supplement

        rows.append({
            "key": key,
            "label": label,
            "unit": unit,
            "target": target_value,
            "provided": round(provided, 1),
            "pct_of_daily": pct,
            "already_supplemented": already_supplemented,
        })

    sodium_provided = recipe_macro.get("sodium_mg")
    sodium_row = None
    if isinstance(sodium_provided, (int, float)):
        sodium_row = {
            "label": "나트륨",
            "unit": "mg",
            "limit": sodium_limit,
            "provided": round(sodium_provided, 1),
            "pct_of_limit": round(sodium_provided / sodium_limit * 100),
            "limit_adjusted": sodium_limit != SODIUM_LIMIT_MG,
        }

    return {
        "available": True,
        "bracket_label": bracket_label,
        "is_estimated": is_estimated,
        "rows": rows,
        "sodium_row": sodium_row,
        "micro_is_partial": micro_is_partial,
        "condition_notes": condition_notes,
    }
