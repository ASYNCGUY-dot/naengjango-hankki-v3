"""
recipes.youtube_url이 비어있는 레시피에 유튜브 영상 링크를 채우는 배치 스크립트.
src/agents/youtube_agent.py의 search_youtube_video()를 그대로 쓰고, DB 접근만
운영 Postgres(psycopg2)로 바꿨다(원본은 SQLite 기준으로 짜여 있어서).

주의: YouTube Data API 무료 할당량은 하루 10,000유닛, 검색 1회에 100유닛이라
하루 최대 100회 정도만 안전하게 처리할 수 있다. 이 스크립트는 인자로 준 개수만큼만
처리하고 멈춘다 - 여러 날에 나눠 실행해야 전체(1,148개)를 채울 수 있다.
"""

import os
import sys
from urllib.parse import unquote

import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "agents"))
from youtube_agent import search_youtube_video, YouTubeQuotaExceededError  # noqa: E402

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


def main(limit: int = 50):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, menu_name FROM recipes WHERE youtube_url IS NULL AND status = 'approved' LIMIT %s",
        (limit,),
    )
    rows = cur.fetchall()
    print(f"이번 실행에서 처리할 레시피 {len(rows)}개")

    filled = 0
    tried = 0
    quota_exceeded = False
    for recipe_id, menu_name in rows:
        tried += 1
        try:
            url = search_youtube_video(f"{menu_name} 레시피")
        except YouTubeQuotaExceededError:
            # 할당량이 소진되면 남은 레시피를 순회해도 계속 실패만 하니 즉시 중단한다.
            quota_exceeded = True
            break

        # 검색 결과가 없어도 NULL을 그대로 두면 WHERE youtube_url IS NULL 조건에 계속 걸려서
        # 다음 실행마다 같은 레시피를 영원히 재시도하게 된다. 빈 문자열을 저장해 "시도했지만
        # 못 찾음"을 표시하고 다음 실행 대상에서 제외한다. UI(rx.cond)는 빈 문자열도 NULL과
        # 동일하게 "영상 없음"으로 처리하므로 안전하다.
        cur.execute("UPDATE recipes SET youtube_url = %s WHERE id = %s", (url or "", recipe_id))
        conn.commit()
        status = url or "(검색 결과 없음)"
        print(f"[{recipe_id}] {menu_name} -> {status}")
        if url:
            filled += 1

    cur.close()
    conn.close()
    if quota_exceeded:
        print(f"할당량 초과로 중단: {len(rows)}개 중 {tried}개만 시도했다")
    print(f"완료: {filled}/{len(rows)}개 채움")


if __name__ == "__main__":
    limit_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    main(limit_arg)
