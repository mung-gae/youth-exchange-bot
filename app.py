from __future__ import annotations

import asyncio
import os
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from youth_exchange import YouthExchangeService, format_won

load_dotenv()

TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = os.getenv('GUILD_ID')
DATABASE_PATH = os.getenv('DATABASE_PATH', './data/youth-exchange.db')
ADMIN_ROLE_ID = os.getenv('ADMIN_ROLE_ID')

if not TOKEN or not GUILD_ID:
    missing = [name for name, value in {'DISCORD_TOKEN': TOKEN, 'GUILD_ID': GUILD_ID}.items() if not value]
    print(f"[청춘거래소] 필수 환경 변수가 누락되었습니다: {', '.join(missing)}")
    raise SystemExit(1)

service = YouthExchangeService(DATABASE_PATH)
print('[청춘거래소] 데이터베이스 연결 완료')
print('[청춘거래소] 데이터베이스 마이그레이션 완료')

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)
GUILD = discord.Object(id=int(GUILD_ID))


def is_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, 'guild_permissions', None)
    if perms and perms.administrator:
        return True
    if ADMIN_ROLE_ID and isinstance(interaction.user, discord.Member):
        return any(str(role.id) == ADMIN_ROLE_ID for role in interaction.user.roles)
    return False


def admin_only(interaction: discord.Interaction) -> None:
    if not is_admin(interaction):
        raise app_commands.AppCommandError('관리자 권한이 필요합니다.')


def active_event_id(interaction: discord.Interaction) -> int:
    return int(service.active_event(str(interaction.guild_id))['event_id'])


async def send_error(interaction: discord.Interaction, message: str) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(f'오류: {message}', ephemeral=True)
    else:
        await interaction.response.send_message(f'오류: {message}', ephemeral=True)

async def deliver_trade_logs(guild_id: str) -> None:
    settings = service.trade_log_settings(guild_id)
    if not settings or not settings['trade_log_enabled'] or not settings['trade_log_channel_id']:
        return
    try:
        channel = bot.get_channel(int(settings['trade_log_channel_id'])) or await bot.fetch_channel(int(settings['trade_log_channel_id']))
    except Exception as exc:
        print(f'[청춘거래소] 거래 로그 채널 조회 실패: {exc}')
        return
    for row in service.pending_trade_activity_rows(guild_id, 100):
        try:
            text = service.render_trade_activity_text(row)
            messages = [text[i:i + 1900] for i in range(0, len(text), 1900)] or [text]
            sent = None
            for message in messages:
                sent = await channel.send(message, allowed_mentions=discord.AllowedMentions.none())
            if sent:
                service.mark_trade_activity_delivered(int(row['id']), str(sent.id))
        except Exception as exc:
            print(f"[청춘거래소] 거래 로그 전송 실패: id={row['id']} 오류={exc}")
            continue


def ensure_trade_log_channel_permissions(interaction: discord.Interaction, channel: discord.TextChannel) -> str:
    bot_member = interaction.guild.me if interaction.guild else None
    if bot_member is None:
        raise app_commands.AppCommandError('봇 권한을 확인할 수 없습니다.')
    perms = channel.permissions_for(bot_member)
    if not (perms.view_channel and perms.send_messages and perms.embed_links and perms.read_message_history):
        raise app_commands.AppCommandError('거래 로그 채널에 메시지를 보낼 권한이 없습니다.\n\n봇에게 다음 권한을 허용해 주세요.\n- 채널 보기\n- 메시지 보내기\n- 임베드 링크')
    default_role = interaction.guild.default_role if interaction.guild else None
    if default_role and channel.permissions_for(default_role).view_channel:
        return '\n\n⚠️ 이 채널은 일반 유저에게도 보일 수 있습니다.\n참가자의 구매 정보가 포함되므로 관리자 전용 채널 사용을 권장합니다.'
    return ''



season_group = app_commands.Group(name='계절투자', description='청춘거래소 이벤트 명령어')


@season_group.command(name='이벤트생성', description='청춘거래소 이벤트를 생성합니다.')
@app_commands.describe(이름='이벤트 이름', 채널='진행 채널', 참가역할='참가 역할', 기본금='기본금')
async def create_event(interaction: discord.Interaction, 이름: str, 채널: Optional[discord.TextChannel] = None, 참가역할: Optional[discord.Role] = None, 기본금: int = 15000):
    try:
        admin_only(interaction)
        event_id = service.create_event(str(interaction.guild_id), 이름, str((채널 or interaction.channel).id), str(참가역할.id) if 참가역할 else None, 기본금)
        await interaction.response.send_message(f'청춘거래소 이벤트가 생성되었습니다. ID: {event_id}', ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='기본금지급', description='등록 참가자 또는 유저에게 기본금을 지급합니다.')
async def grant_starting(interaction: discord.Interaction, 유저: Optional[discord.Member] = None, 금액: int = 15000, 중복허용: bool = False):
    try:
        admin_only(interaction)
        event_id = active_event_id(interaction)
        users = [str(유저.id)] if 유저 else [row['user_id'] for row in service.db.execute('SELECT user_id FROM participants WHERE event_id=?', (event_id,)).fetchall()]
        result = service.grant_starting_fund(event_id, str(interaction.user.id), users, 금액, 중복허용)
        await interaction.response.send_message(f"신규 지급 {result['paid']}명, 제외 {result['skipped']}명, 총 {format_won(result['total'])}", ephemeral=True)
        await deliver_trade_logs(str(interaction.guild_id))
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='자금지급', description='관리자가 참가자에게 추가 자금을 지급합니다.')
async def grant_admin(interaction: discord.Interaction, 유저: discord.Member, 금액: int, 사유: str):
    try:
        admin_only(interaction)
        result = service.grant_admin_fund(active_event_id(interaction), str(interaction.user.id), str(유저.id), 금액, 사유)
        await interaction.response.send_message(f"자금 지급 완료: {format_won(result['before'])} → {format_won(result['after'])}", ephemeral=True)
        await deliver_trade_logs(str(interaction.guild_id))
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='참가등록', description='유저를 참가자로 등록합니다.')
async def add_participant(interaction: discord.Interaction, 유저: discord.Member):
    try:
        admin_only(interaction)
        service.add_participant(active_event_id(interaction), str(유저.id))
        await interaction.response.send_message(f'{유저.mention} 참가자 등록 완료', ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='아이템공개', description='아이템 ID 목록을 공개합니다. 예: 1,2,3')
async def item_public(interaction: discord.Interaction, 아이템id목록: str):
    try:
        admin_only(interaction)
        ids = [int(x.strip()) for x in 아이템id목록.split(',') if x.strip()]
        result = service.set_item_public(active_event_id(interaction), str(interaction.user.id), ids, True)
        await interaction.response.send_message(f"새로 공개된 아이템: {result['newly_public']}개\n이미 공개된 아이템: {result['already_public']}개\n현재 전체 공개 아이템: {result['total_public']}개", ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='구매시작', description='구매를 시작합니다.')
async def start_buying(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        service.start_buying(active_event_id(interaction))
        await interaction.response.send_message('구매를 시작했습니다.')
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='구매종료', description='구매를 종료합니다.')
async def close_buying(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        service.close_buying(active_event_id(interaction))
        await interaction.response.send_message('구매를 종료했습니다.')
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='상점', description='공개된 아이템을 확인합니다.')
async def shop(interaction: discord.Interaction):
    event_id = active_event_id(interaction)
    rows = service.db.execute('SELECT i.item_id,i.name,i.season,i.price FROM items i JOIN event_items ei ON ei.item_id=i.item_id WHERE ei.event_id=? AND ei.is_public=1 ORDER BY i.item_id', (event_id,)).fetchall()
    text = '\n'.join(f"{r['item_id']}. [{r['season']}] {r['name']} {format_won(r['price'])}" for r in rows) or '공개된 아이템이 없습니다.'
    await interaction.response.send_message(text, ephemeral=True)


@season_group.command(name='구매', description='공개된 아이템을 구매합니다.')
async def purchase(interaction: discord.Interaction, 아이템id: int, 수량: int):
    try:
        result = service.purchase(active_event_id(interaction), str(interaction.user.id), 아이템id, 수량)
        await interaction.response.send_message(f"{result['item']} {result['qty']}개 구매 완료. 잔액 {format_won(result['balance'])}", ephemeral=True)
        await deliver_trade_logs(str(interaction.guild_id))
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='매입금설정', description='아이템 매입금을 설정합니다.')
async def buyout(interaction: discord.Interaction, 아이템id: int, 매입금: int):
    try:
        admin_only(interaction)
        service.set_buyout(active_event_id(interaction), str(interaction.user.id), 아이템id, 매입금)
        await interaction.response.send_message('매입금을 설정했습니다.', ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='매입금공개', description='현재 라운드 매입금을 공개합니다.')
async def publish_buyout(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        service.publish_buyouts(active_event_id(interaction), str(interaction.user.id))
        await interaction.response.send_message('매입금을 공개했습니다. 외부 계절 추첨을 진행하세요.')
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='계절결과', description='외부 추첨 계절 결과를 입력합니다.')
@app_commands.choices(계절=[app_commands.Choice(name=s, value=s) for s in ['봄','여름','가을','겨울']])
async def season_result(interaction: discord.Interaction, 계절: app_commands.Choice[str]):
    try:
        admin_only(interaction)
        service.set_season(active_event_id(interaction), str(interaction.user.id), 계절.value)
        await interaction.response.send_message(f'외부 계절 결과: {계절.value}')
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='판매시작', description='판매 신청을 시작합니다.')
async def start_sale(interaction: discord.Interaction, 분: int):
    try:
        admin_only(interaction)
        end = service.start_selling(active_event_id(interaction), str(interaction.user.id), 분)
        await interaction.response.send_message(f'판매를 시작했습니다. 종료: {end}')
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='판매신청', description='선택 계절 아이템 판매를 신청합니다.')
async def sale_request(interaction: discord.Interaction, 아이템id: int, 수량: int):
    try:
        service.sale_request(active_event_id(interaction), str(interaction.user.id), 아이템id, 수량)
        await interaction.response.send_message('판매 신청을 저장했습니다.', ephemeral=True)
        await deliver_trade_logs(str(interaction.guild_id))
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='판매종료', description='판매 신청을 종료합니다.')
async def close_sale(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        service.close_selling(active_event_id(interaction))
        await interaction.response.send_message('판매를 종료했습니다.')
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='정산미리보기', description='정산 미리보기를 확인합니다.')
async def preview(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        rows = service.preview_settlement(active_event_id(interaction))
        text = '\n'.join(f"{r['name']}: {r['total_qty']}개 / 단가 {format_won(r['unit_price'])}" for r in rows) or '정산 대상이 없습니다.'
        await interaction.response.send_message(text, ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='정산', description='현재 라운드를 정산합니다.')
async def settle(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        rows = service.settle(active_event_id(interaction), str(interaction.user.id))
        text = '\n'.join(f"{r['name']}: {r['total_qty']}개 / 단가 {format_won(r['unit_price'])}" for r in rows if r['total_qty']) or '정산 대상이 없습니다.'
        await interaction.response.send_message('정산 완료\n' + text)
        await deliver_trade_logs(str(interaction.guild_id))
    except Exception as exc:
        await send_error(interaction, str(exc))


@season_group.command(name='현황', description='청춘거래소 현황을 확인합니다.')
async def status(interaction: discord.Interaction):
    try:
        event = service.active_event(str(interaction.guild_id))
        public_count = service.db.execute('SELECT COUNT(*) FROM event_items WHERE event_id=? AND is_public=1', (event['event_id'],)).fetchone()[0]
        buying_status = '진행 중' if event['status'] == 'BUYING' else '시작 전' if event['status'] == 'SETTING' else '종료'
        await interaction.response.send_message(f"이벤트: {event['name']}\n현재 라운드: {event['current_round']}\n상태: {event['status']}\n현재 공개 아이템: {public_count}개\n구매 상태: {buying_status}\n선택 계절: {event['selected_season'] or '없음'}")
    except Exception as exc:
        await send_error(interaction, str(exc))


participant_group = app_commands.Group(name='참가자관리', description='청춘거래소 참가자 관리')
item_group = app_commands.Group(name='아이템관리', description='청춘거래소 아이템 관리')
buyout_group = app_commands.Group(name='매입금관리', description='청춘거래소 매입금 관리')
sale_group = app_commands.Group(name='판매관리', description='청춘거래소 판매 관리')
lookup_group = app_commands.Group(name='조회', description='청춘거래소 개인/관리 조회')
event_group = app_commands.Group(name='이벤트관리', description='청춘거래소 이벤트 관리')


@participant_group.command(name='역할등록', description='역할의 일반 유저를 참가자로 등록합니다.')
async def role_register(interaction: discord.Interaction, 역할: discord.Role):
    try:
        admin_only(interaction)
        event_id = active_event_id(interaction)
        count = 0
        for member in 역할.members:
            if not member.bot:
                service.add_participant(event_id, str(member.id))
                count += 1
        await interaction.response.send_message(f'역할 참가자 {count}명을 등록했습니다.', ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@item_group.command(name='비공개', description='아이템 ID 목록을 비공개로 변경합니다. 예: 1,2,3')
async def item_private(interaction: discord.Interaction, 아이템id목록: str):
    try:
        admin_only(interaction)
        ids = [int(x.strip()) for x in 아이템id목록.split(',') if x.strip()]
        result = service.set_item_public(active_event_id(interaction), str(interaction.user.id), ids, False)
        await interaction.response.send_message(f"새로 비공개된 아이템: {result['newly_private']}개\n이미 비공개였던 아이템: {result['already_private']}개\n현재 전체 공개 아이템: {result['total_public']}개", ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@buyout_group.command(name='등급설정', description='가격 등급별 매입금을 일괄 설정합니다.')
@app_commands.choices(등급=[app_commands.Choice(name=s, value=s) for s in ['저가','중가','고가']])
async def tier_buyout(interaction: discord.Interaction, 등급: app_commands.Choice[str], 매입금: int):
    try:
        admin_only(interaction)
        service.set_tier_buyout(active_event_id(interaction), str(interaction.user.id), 등급.value, 매입금)
        await interaction.response.send_message(f'{등급.value} 매입금을 설정했습니다.', ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@buyout_group.command(name='확인', description='현재 라운드 매입금을 확인합니다.')
async def buyout_check(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        rows = service.buyout_rows(active_event_id(interaction))
        text = '\n'.join(f"{r['item_id']}. {r['name']}({r['price_tier']}): {format_won(r['buyout_amount'])} / 공개 {r['is_public']}" for r in rows)
        await interaction.response.send_message(text, ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@sale_group.command(name='변경', description='판매 신청 수량을 최종 수량으로 변경합니다.')
async def sale_change(interaction: discord.Interaction, 아이템id: int, 수량: int):
    try:
        service.sale_request(active_event_id(interaction), str(interaction.user.id), 아이템id, 수량)
        await interaction.response.send_message('판매 신청을 변경했습니다.', ephemeral=True)
        await deliver_trade_logs(str(interaction.guild_id))
    except Exception as exc:
        await send_error(interaction, str(exc))


@sale_group.command(name='취소', description='판매 신청을 취소합니다.')
async def sale_cancel(interaction: discord.Interaction, 아이템id: int):
    try:
        service.cancel_sale_request(active_event_id(interaction), str(interaction.user.id), 아이템id)
        await interaction.response.send_message('판매 신청을 취소했습니다.', ephemeral=True)
        await deliver_trade_logs(str(interaction.guild_id))
    except Exception as exc:
        await send_error(interaction, str(exc))


@sale_group.command(name='내판매', description='내 판매 신청을 확인합니다.')
async def my_sales(interaction: discord.Interaction):
    try:
        rows = service.my_sale_requests(active_event_id(interaction), str(interaction.user.id))
        text = '\n'.join(f"{r['name']}: {r['quantity']}개 / {r['status']}" for r in rows) or '판매 신청이 없습니다.'
        await interaction.response.send_message(text, ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@lookup_group.command(name='내정보', description='내 잔액, 보유 아이템, 누적 거래를 확인합니다.')
async def my_info(interaction: discord.Interaction):
    try:
        info = service.participant_summary(active_event_id(interaction), str(interaction.user.id))
        inv = ', '.join(f"{r['name']} {r['quantity']}개" for r in info['inventory']) or '없음'
        event = service.active_event(str(interaction.guild_id))
        text = f"현재 라운드: {event['current_round']}라운드\n잔액: {format_won(info['balance'])}\n보유: {inv}\n누적 구매: {format_won(info['bought'])}\n누적 판매: {format_won(info['sold'])}\n관리자 지급: {format_won(info['grants'])}"
        await interaction.response.send_message(text, ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@lookup_group.command(name='내역', description='내 최근 거래 내역을 확인합니다.')
async def my_history(interaction: discord.Interaction):
    try:
        rows = service.transactions_for(active_event_id(interaction), str(interaction.user.id))
        text = '\n'.join(f"{r['created_at']} {r['type']} 수량 {r['quantity']} 금액 {format_won(r['amount'])}" for r in rows) or '거래 내역이 없습니다.'
        await interaction.response.send_message(text, ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@lookup_group.command(name='유저조회', description='관리자가 유저 정보를 조회합니다.')
async def user_lookup(interaction: discord.Interaction, 유저: discord.Member):
    try:
        admin_only(interaction)
        info = service.participant_summary(active_event_id(interaction), str(유저.id))
        inv = ', '.join(f"{r['name']} {r['quantity']}개" for r in info['inventory']) or '없음'
        await interaction.response.send_message(f"잔액: {format_won(info['balance'])}\n보유: {inv}", ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))




@lookup_group.command(name='실시간거래', description='관리자가 실시간 거래 활동 기록을 조회합니다.')
@app_commands.choices(종류=[app_commands.Choice(name=n, value=v) for n, v in [('전체','전체'),('구매','ITEM_PURCHASE'),('판매신청','SALE_REQUEST'),('판매변경','SALE_REQUEST_CHANGE'),('판매취소','SALE_REQUEST_CANCEL'),('정산','SETTLEMENT'),('자금지급','ADMIN_FUND_GRANT')]])
async def trade_activity_lookup(interaction: discord.Interaction, 종류: app_commands.Choice[str], 개수: int = 20, 유저: Optional[discord.Member] = None, 아이템id: Optional[int] = None, 라운드: Optional[int] = None):
    try:
        admin_only(interaction)
        rows = service.trade_activity_rows(active_event_id(interaction), 종류.value, 개수, str(유저.id) if 유저 else None, 아이템id, 라운드)
        text = '\n---\n'.join(service.render_trade_activity_text(row)[:900] for row in rows) or '거래 활동 기록이 없습니다.'
        await interaction.response.send_message(text[:1900], ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    except Exception as exc:
        await send_error(interaction, str(exc))


@lookup_group.command(name='구매현황', description='관리자가 현재 구매/보유 현황을 조회합니다.')
async def purchase_status(interaction: discord.Interaction, 상세표시: bool = False):
    try:
        admin_only(interaction)
        rows = service.purchase_status_rows(active_event_id(interaction), 상세표시)
        lines = []
        for row in rows:
            detail = f" / 유저 {row['user_id']}" if 상세표시 and 'user_id' in row.keys() and row['user_id'] else ''
            lines.append(f"{row['item_id']}. {row['name']}({row['season']}){detail}\n전체 보유량: {row['purchased_quantity']}개\n보유 참가자: {row['buyer_count']}명\n누적 구매액: {format_won(row['total_amount'])}\n공개: {'예' if row['is_public'] else '아니요'}")
        await interaction.response.send_message('\n\n'.join(lines)[:1900] or '구매 현황이 없습니다.', ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@lookup_group.command(name='판매현황', description='관리자가 현재 판매 신청 현황을 조회합니다.')
async def sale_status_lookup(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        event = service.active_event(str(interaction.guild_id))
        rows = service.sale_status_rows(event['event_id'])
        lines = [f"현재 라운드: {event['current_round']} / 상태: {event['status']} / 계절: {event['selected_season'] or '없음'}"]
        for row in rows:
            lines.append(f"{row['item_id']}. {row['name']} 신청 {row['total_requested']}개 / 인원 {row['request_users']}명 / 취소 {row['cancelled_count'] or 0}건 / 마지막 변경 {row['last_updated'] or '-'}")
        await interaction.response.send_message('\n'.join(lines)[:1900], ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@event_group.command(name='거래로그설정', description='관리자 전용 실시간 거래 로그 채널을 설정합니다.')
async def trade_log_config(interaction: discord.Interaction, 채널: discord.TextChannel, 활성화: bool = True):
    try:
        admin_only(interaction)
        warning = ensure_trade_log_channel_permissions(interaction, 채널)
        event_id = active_event_id(interaction)
        service.configure_trade_log(str(interaction.guild_id), event_id, str(interaction.user.id), str(채널.id), 활성화)
        state = '활성화' if 활성화 else '비활성화'
        await interaction.response.send_message(f'✅ 실시간 거래 로그 채널이 설정되었습니다.\n\n채널: {채널.mention}\n상태: {state}\n기록 대상: 구매, 판매 신청, 변경, 취소, 정산, 자금 지급{warning}', ephemeral=True)
    except Exception as exc:
        await send_error(interaction, str(exc))


@event_group.command(name='다음라운드', description='정산 완료 후 다음 라운드로 진행합니다.')
async def next_round_cmd(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        result = service.next_round(active_event_id(interaction), str(interaction.user.id))
        await interaction.response.send_message(
            f"🔄 청춘거래소 {result['new_round']}라운드가 시작되었습니다!\n\n"
            '참가자의 잔액과 보유 아이템은 그대로 유지됩니다.\n'
            '이전 라운드에서 판매하지 않은 아이템도 계속 보유합니다.\n'
            '기존에 공개된 아이템도 상점에 계속 유지됩니다.\n\n'
            '운영진은 새로운 아이템을 추가 공개할 수 있으며,\n'
            '구매 시작 후 참가자는 기존 잔액으로 아이템을 추가 구매할 수 있습니다.\n\n'
            f"이전 라운드: {result['previous_round']}라운드\n"
            f"새 라운드: {result['new_round']}라운드\n"
            f"유지된 참가자 수: {result['participants']}명\n"
            f"유지된 전체 보유 아이템: {result['inventory_quantity']}개\n"
            f"유지된 공개 아이템: {result['public_items']}개\n"
            f"새 상태: {result['status']}"
        )
    except Exception as exc:
        await send_error(interaction, str(exc))


@event_group.command(name='종료', description='이벤트를 종료하고 남은 아이템을 소멸합니다.')
async def end_event_cmd(interaction: discord.Interaction):
    try:
        admin_only(interaction)
        service.end_event(active_event_id(interaction), str(interaction.user.id))
        await interaction.response.send_message('이벤트를 종료했습니다. 남은 아이템은 환급 없이 소멸했습니다.')
    except Exception as exc:
        await send_error(interaction, str(exc))


for subgroup in [participant_group, item_group, buyout_group, sale_group, lookup_group, event_group]:
    season_group.add_command(subgroup)


@bot.event
async def on_ready():
    print('[청춘거래소] Discord 로그인 완료')
    try:
        bot.tree.clear_commands(guild=GUILD)
        bot.tree.add_command(season_group, guild=GUILD)
        await bot.tree.sync(guild=GUILD)
        print('[청춘거래소] /계절투자 슬래시 명령어 자동 등록 완료')
        await deliver_trade_logs(str(GUILD_ID))
    except Exception as exc:
        print(f'[청춘거래소] 슬래시 명령어 등록 오류: {exc}')
        raise
    print('[청춘거래소] 판매 마감 작업 복구 완료')
    print('[청춘거래소] 준비 완료')


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == '__main__':
    asyncio.run(main())
