"""
data/app.db(SQLite)의 데이터를 Postgres로 옮기는 스크립트.

사용법:
  1) 001_schema.sql을 Postgres에 먼저 적용해서 빈 테이블을 만들어 둔다.
  2) .env에 POSTGRES_URL(연결 문자열)을 넣는다.
  3) python migration/002_migrate_data.py 실행.
"""

import os
import sqlite3
import sys

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv()

SQLITE_PATH = "data/app.db"
POSTGRES_URL = os.getenv("POSTGRES_URL")

# 외래키 의존성을 만족하는 순서 (001_schema.sql의 테이블 생성 순서와 동일해야 한다)
TABLES_IN_ORDER = [
    "users",
    "ingredients",
    "ingredient_catalog",
    "ingredient_favorites",
    "ingredient_submissions",
    "recipes",
    "recipe_ingredients",
    "recipe_tags",
    "recipe_likes",
    "favorites",
    "reviews",
    "review_summaries",
    "popular_videos",
    "safety_notes",
    "user_partner_keys",
]

# id를 SQLite 원본 값 그대로 넣는 테이블은, 이관 후 Postgres의 SERIAL 시퀀스를 현재
# 최대값으로 맞춰줘야 한다. 안 하면 다음 신규 INSERT가 시퀀스는 1부터 세다가 이미 있는
# id와 충돌해서 "duplicate key" 에러가 난다 (이관 직후 흔히 놓치는 부분).
SERIAL_PK_TABLES = {
    "users": "id",
    "ingredients": "id",
    "ingredient_favorites": "id",
    "ingredient_submissions": "id",
    "recipes": "id",
    "recipe_ingredients": "id",
    "recipe_tags": "id",
    "recipe_likes": "id",
    "favorites": "id",
    "reviews": "id",
    "popular_videos": "id",
    "safety_notes": "id",
}


def migrate_table(sqlite_cur, pg_cur, table: str, batch_size: int = 2000) -> int:
    sqlite_cur.execute(f"SELECT * FROM {table}")
    columns = [desc[0] for desc in sqlite_cur.description]
    col_list = ", ".join(columns)

    total = 0
    while True:
        rows = sqlite_cur.fetchmany(batch_size)
        if not rows:
            break
        psycopg2.extras.execute_values(
            pg_cur, f"INSERT INTO {table} ({col_list}) VALUES %s", rows
        )
        total += len(rows)
    return total


def main():
    if not POSTGRES_URL:
        print("POSTGRES_URL이 .env에 없습니다. 먼저 Postgres 연결 문자열을 설정하세요.")
        sys.exit(1)

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_cur = sqlite_conn.cursor()

    pg_conn = psycopg2.connect(POSTGRES_URL)
    pg_cur = pg_conn.cursor()

    try:
        for table in TABLES_IN_ORDER:
            count = migrate_table(sqlite_cur, pg_cur, table)
            print(f"{table}: {count}행 이관")

        for table, pk_col in SERIAL_PK_TABLES.items():
            pg_cur.execute(
                "SELECT setval(pg_get_serial_sequence(%s, %s), "
                f"COALESCE((SELECT MAX({pk_col}) FROM {table}), 1))",
                (table, pk_col),
            )

        pg_conn.commit()
        print("이관 완료.")
    except Exception:
        pg_conn.rollback()
        raise
    finally:
        pg_cur.close()
        pg_conn.close()
        sqlite_conn.close()


if __name__ == "__main__":
    main()
