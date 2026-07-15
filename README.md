# 청춘거래소 Python 디스호스트 완성본

청춘거래소는 Discord 서버에서 `/계절투자` 슬래시 명령어로 진행하는 계절 아이템 투자 이벤트 봇입니다. 이번 구현은 **Python 3.11+**, **discord.py**, **SQLite** 기반이며 시작 파일은 `app.py` 하나입니다.

## 특징

- Node.js, TypeScript, discord.js, npm, package.json, package-lock.json을 사용하지 않습니다.
- 실행 명령은 `python app.py`입니다.
- 봇 실행 시 `/계절투자` 슬래시 명령어를 지정 길드에 자동 등록합니다.
- 별도 명령어 등록 스크립트가 필요하지 않습니다.
- SQLite DB와 `data/` 폴더를 자동 생성합니다.
- 고정 계절 아이템 12개를 자동 등록합니다.
- 기본금 지급, 관리자 자금 지급, 아이템 공개, 구매, 매입금 설정/공개, 외부 계절 결과 입력, 판매 신청, 정산 흐름을 제공합니다.
- 모든 라운드는 구매 단계를 포함하며, 다음 라운드는 `SETTING` 준비 상태로 돌아가 기존 잔액 및 보유 아이템 유지 → 기존 공개 아이템 유지 → 필요한 아이템 추가 공개 → 구매 시작 → 참가자 추가 구매 → 구매 종료 → 매입금 설정 순서로 반복합니다.
- 다음 라운드가 시작되어도 참가자의 잔액과 보유 아이템은 유지되며, 이전 라운드에서 판매하지 않은 아이템도 그대로 보유할 수 있습니다.
- 기존에 공개된 아이템은 다음 라운드에도 계속 공개되며, 운영진은 아직 공개되지 않은 아이템을 추가 공개할 수 있습니다. 남은 아이템은 이벤트를 최종 종료할 때만 환급 없이 소멸합니다.

## 필요 환경 변수

`.env.example`을 `.env`로 복사해 작성합니다.

```env
DISCORD_TOKEN=
GUILD_ID=
DATABASE_PATH=./data/youth-exchange.db
ADMIN_ROLE_ID=
TZ=Asia/Seoul
```

## 로컬 실행

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Windows PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```


## 라운드 진행 순서

모든 라운드는 같은 순서로 운영합니다.

1. 기존 잔액 및 보유 아이템 유지
2. 기존 공개 아이템 유지
3. 필요한 아이템 추가 공개
4. 구매 시작
5. 참가자 추가 구매
6. 구매 종료
7. 아이템별 매입금 설정
8. 매입금 공개
9. 운영진 외부 계절 추첨
10. 계절 결과 입력
11. 판매 시작
12. 참가자 판매 신청
13. 판매 종료
14. 정산
15. 다음 라운드

`/계절투자 이벤트관리 다음라운드`를 실행하면 라운드 번호가 증가하고 상태가 `SETTING`으로 변경됩니다. 참가자의 잔액, 판매 수익, 보유 아이템, 공개 아이템은 유지되고, 운영진은 아이템을 추가 공개한 뒤 참가자가 기존 잔액으로 기존 보유량에 새 구매 수량을 누적하도록 진행할 수 있습니다. 다음 라운드 이동 중 `ROUND_ITEM_EXPIRATION` 거래는 새로 생성하지 않으며, 남은 아이템은 이벤트를 최종 종료할 때만 환급 없이 소멸합니다.

## 디스호스트/Pterodactyl 배포

1. Python 3.11 이상 서버를 생성합니다.
2. GitHub Actions의 `청춘거래소-파이썬-디스호스트` 아티팩트를 다운로드합니다.
3. ZIP을 업로드하고 압축 해제합니다.
4. `.env.example`을 참고해 `.env`를 작성합니다.
5. 필요 라이브러리는 `requirements.txt`의 `discord.py==2.4.0`, `python-dotenv==1.0.1`입니다.
6. 시작 파일/명령을 `python app.py`로 지정합니다.
7. 서버를 시작합니다.

## 테스트

```bash
python -m unittest discover -s tests
python -m py_compile app.py youth_exchange.py
```

## GitHub Actions

`.github/workflows/build-python-dishost-package.yml`는 Python 3.11에서 테스트와 문법 검사를 실행한 뒤, `app.py`, `youth_exchange.py`, `requirements.txt`, `.env.example`, `README.md`, `README-DISHOST.md`, `data/.gitkeep`만 포함한 디스호스트 ZIP을 생성해 아티팩트로 업로드합니다.
