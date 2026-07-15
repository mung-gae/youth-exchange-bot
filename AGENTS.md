# 청춘거래소 작업 지침
- Node.js 22 이상, TypeScript, discord.js v14, better-sqlite3를 사용합니다.
- 운영 진입점은 `dist/index.js`이며 디스호스트 시작 명령어는 `npm start`입니다.
- Discord 토큰, `.env`, 실제 SQLite DB(`data/youth-exchange.db`)는 커밋하거나 ZIP에 포함하지 않습니다.
- 금액과 수량은 정수로 처리하고 부동소수점 계산을 피합니다.
- 슬래시 명령어는 `npm run deploy:commands`로 별도 등록합니다.
