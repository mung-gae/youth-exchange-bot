# 청춘거래소 (youth-exchange-bot)

Discord 이벤트 봇 **청춘거래소**는 `/계절투자` 슬래시 명령어로 기본금 지급, 계절 아이템 구매, 라운드별 매입금 공개, 외부 계절 추첨 결과 입력, 판매 신청, 일괄 정산, 다음 라운드 및 이벤트 종료를 처리합니다. 봇 내부 랜덤 계절 추첨은 구현하지 않습니다.

## 주요 규칙
- Node.js 22 이상, TypeScript, discord.js v14, SQLite(`better-sqlite3`) 사용.
- 운영 진입점: `dist/index.js`.
- 디스호스트 시작 명령어: `npm start`.
- 모든 금액/수량은 정수이며 판매 단가는 `floor(매입금 / 총판매수량 / 1000) * 1000`으로 계산합니다.
- 한 서버에는 `ENDED`가 아닌 활성 이벤트를 하나만 둘 수 있습니다.
- 구매 취소, 환불, 유저 간 송금/교환/선물/개인 판매, 이벤트 종료 환급은 없습니다.

## 고정 아이템
| 계절 | 저가 3,000원 | 중가 6,000원 | 고가 10,000원 |
|---|---|---|---|
| 봄 | 마스크 | 화분 | 원피스 |
| 여름 | 선풍기 | 튜브 | 수영복 |
| 가을 | 책 | 머플러 | 트렌치 코트 |
| 겨울 | 핫팩 | 목도리 | 패딩 |

## 이벤트 상태
`SETTING → BUYING → BUYING_CLOSED → BUYOUT_SETTING → BUYOUT_PUBLISHED → SEASON_SELECTED → SELLING → SELLING_CLOSED → SETTLED → ENDED`

## 데이터베이스 구조
SQLite 스키마는 `src/database/schema.ts`에서 관리합니다.
- `guild_settings`: 서버별 관리자 역할, 이벤트 채널, 시간대
- `events`: 이벤트명, 상태, 라운드, 기본금, 참가 역할, 선택 계절, 판매 시간, 종료 시각
- `participants`: 참가자, 잔액, 기본금 지급 여부
- `items`: 고정 12개 아이템, 계절, 가격, 가격 등급, 공개 여부
- `inventories`: 참가자별 아이템 보유 수량
- `round_buyouts`: 라운드/아이템별 매입금과 공개 여부
- `sale_requests`: 라운드/유저/아이템별 판매 신청
- `settlements`: 라운드 정산 결과
- `transactions`: 기본금, 관리자 지급, 구매, 판매, 소멸 거래 내역
- `admin_audit_logs`: 관리자 감사 기록
- `schema_migrations`: 마이그레이션 추적용

## 환경 변수
`.env.example`을 `.env`로 복사해 작성합니다.
```env
DISCORD_TOKEN=
CLIENT_ID=
GUILD_ID=
DATABASE_PATH=./data/youth-exchange.db
ADMIN_ROLE_ID=
TZ=Asia/Seoul
NODE_ENV=production
```
`DISCORD_TOKEN`, `CLIENT_ID`가 없으면 봇은 누락 변수명을 한국어로 출력하고 안전하게 종료합니다. 토큰은 로그에 출력하지 않습니다.

## 설치 및 로컬 실행
```bash
npm install
npm run build
npm run deploy:commands
npm start
```
개발 중에는 `npm run dev`를 사용할 수 있습니다.

## 슬래시 명령어 등록
봇 시작 시 자동 등록하지 않습니다. 명령어를 변경했을 때만 다음을 실행하세요.
```bash
npm run deploy:commands
```
기본은 `GUILD_ID` 길드 전용 등록입니다.

## 관리자 명령어
관리자는 Discord Administrator 권한 또는 `ADMIN_ROLE_ID` 역할이 필요합니다.
- `/계절투자 이벤트생성`
- `/계절투자 기본금지급`
- `/계절투자 자금지급`
- `/계절투자 아이템공개`, `/계절투자 아이템비공개`
- `/계절투자 구매시작`, `/계절투자 구매종료`
- `/계절투자 매입금설정`, `/계절투자 등급매입금설정`, `/계절투자 매입금확인`, `/계절투자 매입금공개`
- `/계절투자 계절결과`
- `/계절투자 판매시작`, `/계절투자 판매종료`, `/계절투자 판매현황`
- `/계절투자 정산미리보기`, `/계절투자 정산`
- `/계절투자 다음라운드`, `/계절투자 이벤트종료`
- `/계절투자 유저조회`, `/계절투자 관리기록`

## 참가자 명령어
개인 정보가 포함된 응답은 ephemeral로 전송됩니다.
- `/계절투자 현황`
- `/계절투자 상점`
- `/계절투자 구매`
- `/계절투자 내정보`
- `/계절투자 판매신청`, `/계절투자 판매변경`, `/계절투자 판매취소`, `/계절투자 내판매`
- `/계절투자 내역`

## 운영 순서
1. `/계절투자 이벤트생성`
2. 참가자 등록 후 `/계절투자 기본금지급`
3. `/계절투자 아이템공개`로 아이템 순차 공개
4. `/계절투자 구매시작` → 참가자 구매 → `/계절투자 구매종료`
5. `/계절투자 매입금설정` 또는 `/계절투자 등급매입금설정`
6. `/계절투자 매입금공개`
7. 운영진이 봇 외부에서 계절 추첨
8. `/계절투자 계절결과`
9. `/계절투자 판매시작`
10. 참가자 판매 신청
11. 자동 또는 수동 `/계절투자 판매종료`
12. `/계절투자 정산미리보기` → `/계절투자 정산`
13. `/계절투자 다음라운드` 또는 `/계절투자 이벤트종료`

## 디스호스트 배포

### GitHub Actions 아티팩트 다운로드
1. GitHub 저장소의 `Actions` 탭으로 이동합니다.
2. `Build Dishost Package` 워크플로를 선택합니다.
3. 가장 최근의 성공한 실행을 선택합니다.
4. 화면 아래 `Artifacts`에서 `청춘거래소-디스호스트`를 다운로드합니다.
5. 다운로드된 아티팩트 압축을 풀면 `youth-exchange-bot-dishost.zip`이 나옵니다.
6. 해당 ZIP을 디스호스트 Files 메뉴에 업로드하고 압축 해제합니다.
7. 디스호스트에서 `.env.example`을 참고해 `.env`를 작성합니다.
8. 디스호스트 콘솔에서 `npm ci`, `npm run deploy:commands`, `npm start` 순서로 실행합니다.

### 직접 배포 순서
1. `.env` 작성
2. `npm ci`
3. `npm run build`
4. `npm run deploy:commands`
5. `npm start`

주의사항:
- Windows의 `node_modules`를 업로드하지 마세요.
- 서버에서 `npm ci` 또는 `npm install`을 실행하세요.
- `better-sqlite3` 설치 오류가 발생하면 기존 `node_modules`를 삭제한 뒤 서버에서 다시 설치하세요.
- Node.js 버전이 `>=22`인지 확인하세요.
- 설치 오류 발생 시 디스호스트 콘솔의 전체 로그를 확인하세요.
- `youth-exchange-bot-dishost.zip` 파일은 Git에 커밋하지 않고 GitHub Actions 아티팩트로만 제공합니다.

## SQLite 데이터 저장 및 백업
기본 DB 경로는 `./data/youth-exchange.db`입니다. `data` 폴더가 없으면 자동 생성되며 기존 DB는 초기화하지 않습니다.

백업 예시:
```bash
cp data/youth-exchange.db data/youth-exchange-$(date +%Y%m%d-%H%M%S).db
```
업데이트 전에는 반드시 DB 파일을 백업하세요. 새 버전을 배포한 뒤 `npm ci`, `npm run build`, 필요 시 `npm run deploy:commands`, `npm start` 순서로 진행합니다.

## 검증 명령어
```bash
npm run lint
npm run typecheck
npm test
npm run build
node dist/index.js
```
토큰이 없는 환경에서 `node dist/index.js`는 DB 연결/마이그레이션/판매 작업 복구 후 필수 환경 변수 누락을 출력하고 종료합니다.

## 업로드 ZIP
GitHub Actions의 `Build Dishost Package` 워크플로가 `youth-exchange-bot-dishost.zip`을 생성하고 `청춘거래소-디스호스트` 아티팩트로 업로드합니다.
ZIP 최상위 포함: `package.json`, `package-lock.json`, `dist/`, `src/`, `data/.gitkeep`, `README.md`, `AGENTS.md`, `.env.example`, `tsconfig.json`, 실행에 필요한 설정 파일.
ZIP 제외: `node_modules/`, `.git/`, `.github/`, `coverage/`, `logs/`, `*.log`, `.env`, `data/youth-exchange.db`, `tests/`.
압축 해제 시 불필요한 상위 폴더 없이 최상위에 바로 `package.json`과 `dist/`가 나타납니다.
