# 청춘거래소 디스호스트 설치 안내

이 완성본은 콘솔 명령어를 직접 입력할 수 없는 디스호스트 환경을 기준으로 합니다.

## 포함 파일

- `dist/`
- `data/.gitkeep`
- `package.json`
- `package-lock.json`
- `.env.example`
- `README-DISHOST.md`

## 설치 순서

1. 디스호스트에서 Node.js 22 서버를 생성합니다.
2. GitHub Actions 아티팩트에서 받은 완성본 ZIP을 Files 메뉴에 업로드하고 압축 해제합니다.
3. `.env.example`을 참고해 `.env` 파일을 작성합니다.
4. 디스호스트의 라이브러리 추가 메뉴에서 다음 필수 패키지 3개를 등록합니다.
   - `discord.js@14.19.3`
   - `better-sqlite3@11.10.0`
   - `dotenv@16.5.0`
5. 시작 파일을 `dist/index.js`로 지정합니다.
6. 서버를 시작합니다.

## 환경 변수

```env
DISCORD_TOKEN=봇_토큰
CLIENT_ID=봇_애플리케이션_ID
GUILD_ID=명령어를_등록할_서버_ID
DATABASE_PATH=./data/youth-exchange.db
ADMIN_ROLE_ID=관리자_역할_ID_선택
TZ=Asia/Seoul
NODE_ENV=production
```

## 자동 처리되는 작업

서버가 시작되면 청춘거래소가 같은 프로세스에서 다음 작업을 순서대로 수행합니다.

1. `data` 폴더 생성
2. SQLite 데이터베이스 연결
3. 데이터베이스 마이그레이션
4. 고정 아이템 등록
5. `/계절투자` 슬래시 명령어 길드 자동 등록
6. Discord 봇 로그인
7. 판매 마감 작업 복구

슬래시 명령어는 Discord 길드 명령어 전체 교체 방식으로 등록되므로, 재시작할 때마다 등록해도 중복 생성되지 않습니다.

## 콘솔 명령어가 필요 없는 항목

디스호스트에서는 사용자가 다음 명령어를 직접 입력하지 않아도 됩니다.

- `npm install`
- `npm ci`
- `npm run build`
- `npm run deploy:commands`

## 주의사항

- 실제 `.env` 파일과 `data/youth-exchange.db`는 GitHub에 업로드하거나 공유하지 마세요.
- Windows에서 만든 `node_modules`를 업로드하지 마세요.
- 디스호스트 라이브러리 추가 메뉴에 필수 패키지 3개가 정확한 버전으로 등록되어 있어야 합니다.
