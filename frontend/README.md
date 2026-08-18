# frontend

냉장고 한끼의 React 앱. 프로젝트 전체 설명은 [저장소 최상단 README](../README.md)에 있다.

## 명령

```bash
npm ci && npm run dev
```

| 명령 | 하는 일 |
|---|---|
| `npm run dev` | 개발 서버 |
| `npm run build` | `tsc -b && vite build` |
| `npm test` | Vitest |
| `npm run lint` | oxlint |
| `npm run gen:api` | `openapi.json`에서 API 타입 재생성 |

## API 타입은 손으로 쓰지 않는다

`src/api/schema.d.ts`는 생성물이다. 백엔드 응답 모양이 바뀌면 이 순서로 갱신한다.

```bash
cd .. && ./.venv/Scripts/python.exe scripts/dump_openapi.py
```

```bash
npm run gen:api
```

명세를 배포된 서버가 아니라 **저장소 코드에서** 뽑는 이유가 있다. 처음에는 배포된 V2
백엔드에서 받았는데, 그 명세에는 V3에서 이미 지운 엔드포인트가 남아 있었다. 타입으로
불일치를 잡겠다면서 정작 지금 코드가 아닌 것을 기준으로 삼은 셈이었다. CI가 이 어긋남을
검사한다.

`openapi-typescript`는 TypeScript ^5만 받는데 이 프로젝트는 6을 쓴다. 그래서 의존성으로
넣지 않고 `npx`로 격리 실행한다.

## API 주소

`.env`의 `VITE_API_BASE`로 정한다. 로컬 개발은 이 저장소의 백엔드(`:8001`)를 본다 —
배포된 쪽에는 V3에서 바꾼 인증·엔드포인트가 없을 수 있고, CORS 설정도 다르다.

## 화면

`src/routes/`에 한 화면당 한 파일이다. 각 파일 상단 주석에 **그 화면이 왜 그렇게
생겼는지**를 적어뒀다 — 실제 데이터를 보고 시안에서 바꾼 것들이라 코드만 봐서는 알 수
없다. 예를 들어 홈의 "인기 레시피"는 운영 DB의 좋아요가 4개뿐이라 "레시피 둘러보기"로
바뀌었다.
