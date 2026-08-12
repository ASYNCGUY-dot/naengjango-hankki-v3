-- SQLite(data/app.db) 15개 테이블을 Postgres로 그대로 옮기기 위한 DDL.
-- 타입 변환 원칙:
--   INTEGER PRIMARY KEY AUTOINCREMENT -> SERIAL PRIMARY KEY
--   REAL                              -> DOUBLE PRECISION
--   TEXT(날짜/시간)                    -> 우선 TEXT 그대로 유지 (에이전트가 datetime.isoformat() 문자열로
--                                        저장하고 있어서, 타입까지 TIMESTAMP로 바꾸는 건 별도 작업으로 미룸)

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    gender TEXT,
    age_group TEXT,
    allergy TEXT,
    health_goal TEXT,
    purpose TEXT,
    cooking_level TEXT,
    supplements TEXT,
    household_size INTEGER,
    novelty_pref TEXT,
    username TEXT,
    password_hash TEXT,
    cooking_tools TEXT,
    is_admin INTEGER DEFAULT 0,
    medical_conditions TEXT
);

CREATE TABLE ingredients (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    name TEXT,
    source_type TEXT,
    expiry_date TEXT
);

CREATE TABLE ingredient_catalog (
    food_code TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    db_group TEXT,
    energy_kcal DOUBLE PRECISION,
    water_g DOUBLE PRECISION,
    protein_g DOUBLE PRECISION,
    fat_g DOUBLE PRECISION,
    ash_g DOUBLE PRECISION,
    carbs_g DOUBLE PRECISION,
    sugar_g DOUBLE PRECISION,
    fiber_g DOUBLE PRECISION,
    calcium_mg DOUBLE PRECISION,
    iron_mg DOUBLE PRECISION,
    potassium_mg DOUBLE PRECISION,
    sodium_mg DOUBLE PRECISION,
    vitamin_a_ug DOUBLE PRECISION,
    vitamin_b1_mg DOUBLE PRECISION,
    vitamin_b2_mg DOUBLE PRECISION,
    niacin_mg DOUBLE PRECISION,
    vitamin_c_mg DOUBLE PRECISION,
    vitamin_d_ug DOUBLE PRECISION,
    magnesium_mg DOUBLE PRECISION,
    zinc_mg DOUBLE PRECISION,
    updated_at TEXT
);

CREATE TABLE ingredient_favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    food_code TEXT REFERENCES ingredient_catalog(food_code),
    created_at TEXT
);

CREATE TABLE ingredient_submissions (
    id SERIAL PRIMARY KEY,
    ingredient_name TEXT,
    submitted_by INTEGER REFERENCES users(id),
    calorie DOUBLE PRECISION,
    carbs_g DOUBLE PRECISION,
    protein_g DOUBLE PRECISION,
    fat_g DOUBLE PRECISION,
    sodium_mg DOUBLE PRECISION,
    price_per_100g DOUBLE PRECISION,
    status TEXT DEFAULT 'pending',
    created_at TEXT,
    reviewed_at TEXT,
    reviewed_by INTEGER REFERENCES users(id)
);

CREATE TABLE recipes (
    id SERIAL PRIMARY KEY,
    menu_name TEXT,
    cook_method TEXT,
    category TEXT,
    calorie DOUBLE PRECISION,
    nutrients_json TEXT,
    image_url TEXT,
    youtube_url TEXT,
    source_api TEXT,
    steps_json TEXT,
    submitted_by INTEGER,
    status TEXT DEFAULT 'approved'
);

CREATE TABLE recipe_ingredients (
    id SERIAL PRIMARY KEY,
    recipe_id INTEGER REFERENCES recipes(id),
    name TEXT,
    amount DOUBLE PRECISION,
    unit TEXT,
    raw_text TEXT,
    base_servings INTEGER
);

CREATE TABLE recipe_tags (
    id SERIAL PRIMARY KEY,
    recipe_id INTEGER REFERENCES recipes(id),
    tag_type TEXT,
    tag_value TEXT
);

CREATE TABLE recipe_likes (
    id SERIAL PRIMARY KEY,
    recipe_id INTEGER REFERENCES recipes(id),
    user_id INTEGER REFERENCES users(id),
    created_at TEXT
);

CREATE TABLE favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    recipe_id INTEGER REFERENCES recipes(id),
    created_at TEXT
);

CREATE TABLE reviews (
    id SERIAL PRIMARY KEY,
    recipe_id INTEGER REFERENCES recipes(id),
    user_id INTEGER REFERENCES users(id),
    rating INTEGER,
    review_text TEXT,
    created_at TEXT
);

CREATE TABLE review_summaries (
    recipe_id INTEGER PRIMARY KEY REFERENCES recipes(id),
    summary_text TEXT,
    review_count INTEGER,
    updated_at TEXT
);

CREATE TABLE popular_videos (
    id SERIAL PRIMARY KEY,
    category TEXT,
    video_title TEXT,
    channel_title TEXT,
    video_id TEXT,
    thumbnail_url TEXT,
    video_url TEXT,
    view_count INTEGER,
    fetched_at TEXT
);

CREATE TABLE safety_notes (
    id SERIAL PRIMARY KEY,
    ingredient_name TEXT,
    notice_text TEXT,
    source_url TEXT,
    created_at TEXT
);

CREATE TABLE user_partner_keys (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    coupang_access_key_encrypted TEXT,
    coupang_secret_key_encrypted TEXT,
    updated_at TEXT
);
