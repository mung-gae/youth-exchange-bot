# 청춘거래소 Python 디스호스트 설치 안내

이 완성본은 Python 기반 디스호스트/Pterodactyl 환경에서 `python app.py`로 실행됩니다.

## 포함 파일

- `app.py`
- `youth_exchange.py`
- `requirements.txt`
- `.env.example`
- `README-DISHOST.md`
- `data/.gitkeep`

## 설치 순서

1. Python 3.11 이상 서버를 생성합니다.
2. GitHub Actions 아티팩트 `청춘거래소-파이썬-디스호스트`를 다운로드합니다.
3. 완성본 ZIP을 Files 메뉴에 업로드하고 압축 해제합니다.
4. `.env.example`을 참고해 `.env`를 작성합니다.
5. 라이브러리 설치 메뉴가 있다면 다음을 등록합니다.
   - `discord.py==2.4.0`
   - `python-dotenv==1.0.1`
6. 시작 명령을 `python app.py`로 지정합니다.
7. 서버를 시작합니다.

## 자동 처리

서버가 시작되면 청춘거래소는 다음 작업을 자동으로 수행합니다.

1. `data` 폴더 생성
2. SQLite 데이터베이스 연결
3. 데이터베이스 마이그레이션
4. 고정 아이템 등록
5. `/계절투자` 슬래시 명령어 자동 등록
6. Discord 봇 로그인

## 주의사항

- 실제 `.env`와 `data/youth-exchange.db`는 업로드 공유나 커밋 대상이 아닙니다.
- Node.js, npm, package.json, package-lock.json은 필요하지 않습니다.
