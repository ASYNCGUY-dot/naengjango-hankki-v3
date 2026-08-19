# CLAUDE.md — 냉장고 한끼 (V3)

이 파일은 이 프로젝트에서 작업할 때의 규칙입니다. 코드 작업 규칙은 기존 문서(`README.md`, `V3_PLAN.md`, `V3_HANDOFF.md`)를 따르고, 여기서는 업무 기억(위키) 연동만 다룹니다.

## AI 업무 위키 연동

- 위키 위치: `C:\Users\Donga\Desktop\AI-Agent-Wiki`
- 이 프로젝트 전용 기록 문서: `C:\Users\Donga\Desktop\AI-Agent-Wiki\AI-Sessions\wiki\projects\냉장고-한끼.md`
- **주의: 이 컴퓨터에는 "옵시디언"이라는 이름이 들어간 폴더가 두 개다** — `Desktop\옵시디언\JISOO.DOC`(개인 지식관리 볼트, 이 프로젝트와 무관)와 `Desktop\AI-Agent-Wiki`(이 프로젝트가 연동된 위키). "옵시디언에 저장해줘"라고만 하면 이름이 겹쳐서 잘못된 폴더로 갈 수 있다. **반드시 "위키에 저장해줘" 또는 "AI-Agent-Wiki에 저장해줘"라고 명시적으로 말한다.** ("옵시디언"이라는 단어가 나오면 잠깐 멈추고 어느 폴더인지 되묻는다.)
- 위 표현으로 요청이 오면, 위키 폴더의 `CLAUDE.md` 규칙(raw/wiki 분리, 저장 전 5가지 필터)을 그대로 적용해서 해당 경로에 기록하거나 참조한다. 이 프로젝트의 raw 폴더가 아니라 위키의 raw/wiki 구조를 따른다.
- 저장 대상 예시: 아키텍처 결정 → `decisions/`, 재발 방지할 버그/트러블슈팅 → `errors/`, 프로젝트 진행 상황 갱신 → `projects/냉장고-한끼.md`
- 저장/참조 후에는 반드시 `index.md`와 `log.md`도 같이 갱신한다 (빼먹으면 다음 lint에서 걸린다).

## 세션 시작 방법 (필수)

위키 폴더는 이 프로젝트 폴더 밖에 있어서, `--add-dir` 없이 `claude`만 실행하면 위키에 아예 접근할 수 없다 — 그 상태에서 "옵시디언에 저장해줘"라고 하면 이름만 보고 엉뚱한 폴더(JISOO.DOC)를 찾아가거나 실패한다. 아래처럼 실행하거나, 같은 폴더의 `wiki-세션.bat`를 더블클릭한다.

```bash
claude --add-dir "C:\Users\Donga\Desktop\AI-Agent-Wiki"
```
