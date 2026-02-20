# CLAUDE.md

## 프로젝트 개요

등기부등본 PDF 파싱 서비스. PDF를 업로드하면 표제부, 갑구, 을구를 자동 분석하여 구조화된 데이터를 반환한다.

- 프론트엔드: Next.js 16 (React 19, TypeScript, Tailwind CSS 4, shadcn/ui)
- 백엔드: FastAPI (Python 3.12, SQLAlchemy async, SQLite)
- 결제: Toss Payments (현재 테스트 모드)
- 배포: All-in-one Docker 컨테이너 (Caddy + Next.js + FastAPI, supervisord)

## 프로젝트 구조

```
├── src/                        # Next.js 프론트엔드
│   ├── app/                    # App Router 페이지
│   │   ├── page.tsx            # 메인 페이지
│   │   ├── login/              # 로그인
│   │   ├── signup/             # 회원가입
│   │   ├── dashboard/          # 대시보드
│   │   ├── pricing/            # 요금제 페이지
│   │   ├── settings/           # 사용자 설정
│   │   └── payment/            # 결제 성공/실패
│   ├── components/ui/          # shadcn/ui 컴포넌트
│   ├── lib/                    # 유틸리티 (api.ts, auth.tsx, pdf-parser.ts)
│   └── types/                  # TypeScript 타입 정의
├── backend/                    # FastAPI 백엔드
│   ├── main.py                 # FastAPI 앱 엔트리포인트
│   ├── config.py               # 설정 (요금제, Toss 키, DB URL 등)
│   ├── database.py             # SQLAlchemy async 엔진/세션
│   ├── models.py               # ORM 모델 (User, ParseRecord, Payment 등)
│   ├── schemas.py              # Pydantic 스키마
│   ├── auth.py                 # JWT 인증, 비밀번호 해싱
│   ├── pdf_parser.py           # PDF 파싱 로직
│   ├── payment.py              # Toss Payments 연동
│   ├── webhook.py              # Webhook 발송
│   ├── admin.py                # 관리자 CLI 도구
│   └── requirements.txt        # Python 의존성
├── Dockerfile.allinone         # All-in-one 이미지 빌드
├── Caddyfile.allinone          # Caddy 리버스 프록시 설정
├── supervisord.allinone.conf   # 프로세스 매니저 설정
├── docker-compose.yml          # 로컬 멀티컨테이너 (개발용)
└── package.json                # Node.js 의존성 (pnpm)
```

## 개발 환경

### 프론트엔드
```bash
pnpm install
pnpm dev              # localhost:3009에서 개발 서버 시작
```

### 백엔드
```bash
cd backend
uv sync               # 의존성 설치
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 관리자 CLI
```bash
# 로컬
uv run python backend/admin.py stats
uv run python backend/admin.py users
uv run python backend/admin.py user <email>

# K8s (Windows Git Bash에서 MSYS_NO_PATHCONV 필수)
MSYS_NO_PATHCONV=1 kubectl -n app exec deploy/pdf-service-aio -- python /srv/backend/admin.py stats
```

## 빌드 및 배포

### Docker 이미지 빌드 (ARM64)
```bash
docker buildx build --platform linux/arm64 -f Dockerfile.allinone -t junsik/pdf-service-aio:<tag> --push .
```
- 파일 변경이 반영 안 될 경우 `--no-cache` 플래그 추가
- 이미지 태그 컨벤션: `YYYYMMDD` (예: `20260219`)

### K8s 배포
- 배포 파일: `C:\work\imprun-infra\apps\pdf-service-aio\deployment.yaml`
- 네임스페이스: `app`
- 호스트: `pdfdemo.app.imprun.dev`
- 인증: Envoy Gateway SecurityPolicy (Basic Auth)

```bash
MSYS_NO_PATHCONV=1 kubectl apply -f /c/work/imprun-infra/apps/pdf-service-aio/deployment.yaml
MSYS_NO_PATHCONV=1 kubectl -n app rollout restart deployment/pdf-service-aio
```

## 주요 설정

### 요금제 (backend/config.py)
| 플랜 | 가격 | 월 크레딧 | 일 한도 |
|------|------|-----------|---------|
| 무료 | 0원 | 100회 | 10회 |
| 베이직 | 9,900원 | 10회 | 30회 |
| 프로 | 29,900원 | 무제한 | 무제한 |

- 유료 플랜은 프론트엔드에서 "준비중"으로 표시 (pricing/page.tsx)

### DB
- 백엔드 SQLite: `backend/data/registry.db` (상대경로, 백엔드 디렉토리 기준)
- 프론트엔드 Prisma SQLite: `db/custom.db`

### 포트 (컨테이너 내부)
- 8080: Caddy (외부 진입점)
- 8000: FastAPI
- 3000: Next.js

## 주의사항

- Windows Git Bash(MSYS)에서 kubectl 사용 시 반드시 `MSYS_NO_PATHCONV=1` 환경변수 필요 (경로 자동 변환 방지)
- admin.py는 `os.chdir(Path(__file__).parent)`로 스크립트 위치로 이동 후 실행됨 (K8s에서 WORKDIR=/srv 문제 해결)
- Caddy bcrypt 해시는 `$2a` 형식 필요 (`docker run --rm caddy:2 caddy hash-password --plaintext <password>`)
- Docker buildx는 레이어 캐시가 강하므로 파일 변경 후 `--no-cache` 고려
