"""
popular_videos 캐시를 갱신하는 스크립트. src/agents/popular_recipe_agent.py의
refresh_popular_videos()를 그대로 쓰고, DB 접근만 운영 Postgres(psycopg2)로 바꿨다.
YouTube API 할당량을 쓰므로(카테고리당 약 100유닛) 며칠에 한 번만 실행하면 된다.
"""

import os
import sys
from urllib.parse import unquote

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "agents"))
from popular_recipe_agent import CATEGORY_QUERIES, refresh_popular_videos  # noqa: E402

load_dotenv()


def _connect():
    url = os.getenv("POSTGRES_URL")
    scheme_sep = url.find("://")
    rest = url[scheme_sep + 3:]
    at_idx = rest.rfind("@")
    userinfo = rest[:at_idx]
    hostpart = rest[at_idx + 1:]
    colon_idx = userinfo.find(":")
    user = userinfo[:colon_idx]
    password = unquote(userinfo[colon_idx + 1:])
    hostport, dbname = hostpart.split("/", 1)
    host, port = hostport.split(":")
    return psycopg2.connect(host=host, port=port, dbname=dbname, user=user, password=password)


class SqliteStyleCursor(psycopg2.extensions.cursor):
    def execute(self, query, vars=None):
        if isinstance(query, str) and "?" in query:
            query = query.replace("?", "%s")
        return super().execute(query, vars)


def main():
    conn = _connect()
    cur = conn.cursor(cursor_factory=SqliteStyleCursor)
    for category, query in CATEGORY_QUERIES.items():
        count = refresh_popular_videos(cur, category, query)
        conn.commit()
        print(f"[{category}] '{query}' 검색 -> {count}개 저장")
    cur.close()
    conn.close()
    print("완료.")


if __name__ == "__main__":
    main()
