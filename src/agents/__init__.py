"""
V1 시절 이 폴더 안에서 스크립트를 직접 실행하던 습관 때문에, 일부 에이전트가
"from tagging_agent import ..."처럼 형제 모듈을 최상위 이름으로 임포트한다.
에이전트 파일 자체는 수정하지 않고, 이 폴더를 sys.path에 등록해서 그 임포트가
그대로 동작하게 한다.
"""

import os
import sys

_AGENTS_DIR = os.path.dirname(__file__)
if _AGENTS_DIR not in sys.path:
    sys.path.insert(0, _AGENTS_DIR)
