-- pytest용 최소 시드 DB 스키마. data/app.db(로컬 전용, 68MB, gitignore됨)에서
-- CREATE TABLE 구문만 그대로 복사하고, 테스트에 필요한 최소한의 참고 데이터만 몇 줄
-- 손으로 채워 넣었다. 이 파일은 git에 커밋돼 있어서 로컬은 물론 CI(GitHub Actions)에서도
-- 똑같이 재현 가능하다 - data/app.db가 없는 환경에서도 tests/conftest.py가 이 파일로
-- DB를 새로 만들어 테스트를 돌린다.

CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gender TEXT,
    age_group TEXT,
    allergy TEXT,
    health_goal TEXT,
    purpose TEXT,
    cooking_level TEXT,
    supplements TEXT,
    household_size INTEGER,
    novelty_pref TEXT
, username TEXT, password_hash TEXT, cooking_tools TEXT, is_admin INTEGER DEFAULT 0, medical_conditions TEXT);

-- sqlite_sequence는 AUTOINCREMENT 컬럼이 있으면 sqlite가 알아서 만들어주는 내부
-- 테이블이라 여기서 직접 CREATE하면 안 된다(위 users 테이블의 AUTOINCREMENT가
-- 자동으로 만들어준다).

CREATE TABLE ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    source_type TEXT,
    expiry_date TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    menu_name TEXT,
    cook_method TEXT,
    category TEXT,
    calorie REAL,
    nutrients_json TEXT,
    image_url TEXT,
    youtube_url TEXT,
    source_api TEXT,
    steps_json TEXT
, submitted_by INTEGER, status TEXT DEFAULT 'approved');

CREATE TABLE recipe_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER,
    tag_type TEXT,
    tag_value TEXT,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id)
);

CREATE TABLE safety_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_name TEXT,
    notice_text TEXT,
    source_url TEXT,
    created_at TEXT
);

CREATE TABLE recipe_ingredients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER,
    name TEXT,
    amount REAL,
    unit TEXT,
    raw_text TEXT,
    base_servings INTEGER,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id)
);

CREATE TABLE reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER,
    user_id INTEGER,
    rating INTEGER,
    review_text TEXT,
    created_at TEXT,
    image_url TEXT,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE review_summaries (
    recipe_id INTEGER PRIMARY KEY,
    summary_text TEXT,
    review_count INTEGER,
    updated_at TEXT,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id)
);

CREATE TABLE favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    recipe_id INTEGER,
    created_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (recipe_id) REFERENCES recipes(id)
);

CREATE TABLE recipe_likes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER,
    user_id INTEGER,
    created_at TEXT,
    FOREIGN KEY (recipe_id) REFERENCES recipes(id),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE ingredient_submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ingredient_name TEXT,
    submitted_by INTEGER,
    calorie REAL,
    carbs_g REAL,
    protein_g REAL,
    fat_g REAL,
    sodium_mg REAL,
    price_per_100g REAL,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    reviewed_at TEXT,
    reviewed_by INTEGER,
    FOREIGN KEY (submitted_by) REFERENCES users(id),
    FOREIGN KEY (reviewed_by) REFERENCES users(id)
);

CREATE TABLE ingredient_catalog (
    food_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    db_group TEXT,
    energy_kcal REAL,
    water_g REAL,
    protein_g REAL,
    fat_g REAL,
    ash_g REAL,
    carbs_g REAL,
    sugar_g REAL,
    fiber_g REAL,
    calcium_mg REAL,
    iron_mg REAL,
    potassium_mg REAL,
    sodium_mg REAL,
    vitamin_a_ug REAL,
    vitamin_b1_mg REAL,
    vitamin_b2_mg REAL,
    niacin_mg REAL,
    vitamin_c_mg REAL,
    vitamin_d_ug REAL,
    magnesium_mg REAL,
    zinc_mg REAL,
    updated_at TEXT
);

CREATE TABLE ingredient_favorites (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    food_code TEXT,
    created_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id),
    FOREIGN KEY (food_code) REFERENCES ingredient_catalog(food_code)
);

CREATE TABLE popular_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT,
    video_title TEXT,
    channel_title TEXT,
    video_id TEXT,
    thumbnail_url TEXT,
    video_url TEXT,
    view_count INTEGER,
    fetched_at TEXT
);

CREATE TABLE user_partner_keys (
    user_id INTEGER PRIMARY KEY,
    coupang_access_key_encrypted TEXT,
    coupang_secret_key_encrypted TEXT,
    updated_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 토큰 기반 인가 (2026-07-19, api/auth_token.py). 토큰 원문이 아니라 sha256 해시만 저장한다.
CREATE TABLE auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER,
    created_at TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 최소 시드 데이터: recommendation/review/safety/price 라우터 테스트용 승인된 레시피 1개.
-- 두부/양파 두 재료만 써서 recommendation_agent의 자격(qualifies) 판단이 쉽게 재현되게
-- 했다 - 메뉴명에 "두부"가 그대로 들어있어 core_ingredients가 "두부"로 잡히므로, 보유
-- 재료에 두부가 있으면 자격을 얻는다(recommendation_agent.py 9차 개정 참고).
INSERT INTO recipes (id, menu_name, cook_method, category, calorie, nutrients_json, image_url, youtube_url, source_api, steps_json, status)
VALUES (
    1, '두부조림', '조림', '반찬', 120.0,
    '{"energy_kcal": 120, "protein_g": 10, "fat_g": 5, "carbs_g": 8}',
    NULL, NULL, 'public', '["두부를 썬다", "양파와 함께 졸인다"]', 'approved'
);

INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES
    (1, 'ingredient', '두부'),
    (1, 'ingredient', '양파'),
    (1, 'nutrition_group', '고단백');

INSERT INTO recipe_ingredients (recipe_id, name, amount, unit, raw_text, base_servings) VALUES
    (1, '두부', 200, 'g', '두부 200g', 2),
    (1, '양파', 50, 'g', '양파 50g', 2);

-- recipe_ingredients가 하나도 없는 승인된 레시피 - price/nutrition 라우터의
-- "재료 수량 정보 없음" 404 분기를 테스트하기 위한 용도.
INSERT INTO recipes (id, menu_name, cook_method, category, calorie, nutrients_json, image_url, youtube_url, source_api, steps_json, status)
VALUES (
    2, '재료수량정보없는레시피', '기타', '반찬', 100.0,
    '{"energy_kcal": 100, "protein_g": 5, "fat_g": 3, "carbs_g": 10}',
    NULL, NULL, 'public', '["단계 1"]', 'approved'
);

-- 2026-07-19 SUBSTITUTES 확장분(파프리카/피망 등) 검증용 - 재료 태그 1개짜리 최소 레시피.
INSERT INTO recipes (id, menu_name, cook_method, category, calorie, nutrients_json, image_url, youtube_url, source_api, steps_json, status)
VALUES (
    3, '파프리카볶음', '볶음', '반찬', 80.0,
    '{"energy_kcal": 80, "protein_g": 2, "fat_g": 4, "carbs_g": 6}',
    NULL, NULL, 'public', '["단계 1"]', 'approved'
);
INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES (3, 'ingredient', '파프리카');

-- "이 메뉴가 싫다면?"(대체 추천, 2026-07-21, #req6) 테스트용 - 레시피 1(두부조림, 고단백,
-- 120kcal)과 같은 영양군인 승인된 레시피 하나를 더 둔다. 재료는 완전히 무관하게(닭가슴살) 잡아서
-- "재료와 관계없이 영양군만 맞으면 대체 추천된다"는 것을 검증할 수 있게 했다.
INSERT INTO recipes (id, menu_name, cook_method, category, calorie, nutrients_json, image_url, youtube_url, source_api, steps_json, status)
VALUES (
    4, '닭가슴살구이', '구이', '일품', 130.0,
    '{"energy_kcal": 130, "protein_g": 25, "fat_g": 3, "carbs_g": 2}',
    NULL, NULL, 'public', '["닭가슴살을 굽는다"]', 'approved'
);
INSERT INTO recipe_tags (recipe_id, tag_type, tag_value) VALUES
    (4, 'ingredient', '닭가슴살'),
    (4, 'nutrition_group', '고단백');

-- 최소 시드 데이터: 재료 즐겨찾기/검색 테스트용 실제 식품영양성분DB 값 (두부, P106-000000100-0001)
INSERT INTO ingredient_catalog (
    food_code, name, db_group, energy_kcal, water_g, protein_g, fat_g, ash_g,
    carbs_g, sugar_g, fiber_g, calcium_mg, iron_mg, potassium_mg, sodium_mg,
    vitamin_a_ug, vitamin_b1_mg, vitamin_b2_mg, niacin_mg, vitamin_c_mg,
    vitamin_d_ug, magnesium_mg, zinc_mg
) VALUES (
    'P106-000000100-0001', '두부', '원재료성', 97.0, 81.2, 9.62, 4.63, 0.8,
    3.75, 0.0, 2.9, 64.0, 1.54, 132.0, 1.0,
    NULL, 0.03, 0.18, 0.16, 0.0,
    0.0, 80.0, 1.17
);

-- 검색 정렬 일반화 테스트용(2026-07-21, "3번 설정을 모든 재료에 적용해줘") - "고사리"는
-- COMMON_INGREDIENT_NAMES 큐레이션 목록에 없는 재료다. 가나다순으로는 "고사리_데친것"이
-- "고사리_생것"보다 앞에 오지만(ㄷ<ㅅ), 변형 우선순위 정렬이 큐레이션 목록 밖 재료에도
-- 적용되면 "고사리_생것"이 먼저 나와야 한다.
INSERT INTO ingredient_catalog (food_code, name, db_group) VALUES
    ('TEST-GOSARI-DRIED', '고사리_말린것', '원재료성'),
    ('TEST-GOSARI-BOILED', '고사리_데친것', '원재료성'),
    ('TEST-GOSARI-RAW', '고사리_생것', '원재료성');
