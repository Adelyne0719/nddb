import os
import sys
import json
import logging
import discord
from datetime import datetime
from logging.handlers import RotatingFileHandler
from discord.ext import commands
from dotenv import load_dotenv
from grammar_checker import GrammarChecker

# --- 경로 설정 (PyInstaller 원파일 패키징 지원) ---
if getattr(sys, "frozen", False):
    # .exe로 실행: exe가 있는 실제 폴더
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # .py로 실행: 스크립트가 있는 폴더
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ENV_FILE = os.path.join(BASE_DIR, ".env")
COUNT_FILE = os.path.join(BASE_DIR, "spell_check_counts.json")
LOG_FILE = os.path.join(BASE_DIR, "nddb.log")

# --- 로깅 설정 (5MB x 3파일 로테이션) ---
logger = logging.getLogger("nddb")
logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(file_handler)
logger.addHandler(console_handler)

# --- .env 파일 자동 생성 ---
if not os.path.exists(ENV_FILE):
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("DISCORD_TOKEN=여기에_디스코드_봇_토큰_입력\n")
        f.write("GEMINI_API_KEY=여기에_제미나이_API_키_입력\n")
    logger.info(f".env 파일이 생성되었습니다: {ENV_FILE}")
    logger.info("DISCORD_TOKEN과 GEMINI_API_KEY를 입력한 뒤 다시 실행해 주세요.")
    input("엔터를 누르면 종료됩니다...")
    sys.exit(0)

load_dotenv(ENV_FILE)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not DISCORD_TOKEN or not GEMINI_API_KEY \
        or "여기에" in DISCORD_TOKEN or "여기에" in GEMINI_API_KEY:
    logger.warning(f".env 파일에 토큰/키를 입력해 주세요: {ENV_FILE}")
    input("엔터를 누르면 종료됩니다...")
    sys.exit(0)

# --- 봇 설정 ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents, max_messages=100)
checker = GrammarChecker(api_key=GEMINI_API_KEY)


def load_counts() -> dict:
    if os.path.exists(COUNT_FILE):
        try:
            with open(COUNT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}
    return {}


def save_counts(counts: dict):
    # atomic write: 임시 파일에 쓴 뒤 이름 변경 (정전 시 파일 손상 방지)
    tmp_file = COUNT_FILE + ".tmp"
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=4, ensure_ascii=False)
    os.replace(tmp_file, COUNT_FILE)


user_spell_counts = load_counts()


def make_accuracy_bar(user_month: dict, bar_length: int = 15) -> str:
    """정확도 텍스트아트 바를 생성합니다."""
    total = user_month.get("_total", 0)
    if total == 0:
        return ""
    error_count = sum(v for k, v in user_month.items() if k != "_total")
    correct = total - error_count
    ratio = correct / total

    filled = round(ratio * bar_length)
    empty = bar_length - filled
    bar = "█" * filled + "░" * empty

    return (
        f"\n**정확도**\n"
        f"`{bar}` **{ratio:.0%}**\n"
        f"✅ {correct}회 정확 / ❌ {error_count}회 오류 (총 {total}회)"
    )


@bot.event
async def on_ready():
    activity = discord.Game(name="!도움")
    await bot.change_presence(activity=activity)
    logger.info(f"봇 로그인 완료: {bot.user.name}")


@bot.event
async def on_message(message):
    # 봇 메시지 무시
    if message.author.bot:
        return

    # 명령어 처리
    if message.content.startswith(bot.command_prefix):
        await bot.process_commands(message)
        return

    # 되/돼 계열 글자가 포함된 메시지만 검사
    if not checker._contains_doe_dwae(message.content):
        return

    try:
        result = await checker.check(message.content)

        # 되/돼 검사 총 횟수 기록
        month_key = datetime.now().strftime("%Y-%m")
        user_id = str(message.author.id)
        if user_id not in user_spell_counts:
            user_spell_counts[user_id] = {}
        if month_key not in user_spell_counts[user_id]:
            user_spell_counts[user_id][month_key] = {}
        user_month = user_spell_counts[user_id][month_key]
        user_month["_total"] = user_month.get("_total", 0) + 1

        if result is None:
            save_counts(user_spell_counts)
            return

        # 교정 메시지 생성
        lines = [f"{message.author.mention} 님, '되/돼' 맞춤법을 확인해 주세요!\n"]

        for c in result["corrections"]:
            lines.append(f"❌ {c['original']}  →  ✅ {c['corrected']}")
            lines.append(f"💡 {c['explanation']}\n")

            sub_key = f"{c['original']}→{c['corrected']}"
            user_month[sub_key] = user_month.get(sub_key, 0) + 1

        save_counts(user_spell_counts)

        # 이번에 틀린 항목의 누적 횟수 표시
        count_parts = []
        for c in result["corrections"]:
            sub_key = f"{c['original']}→{c['corrected']}"
            count_parts.append(f"{sub_key} {user_month[sub_key]}회")
        lines.append(f"({', '.join(count_parts)})")

        await message.channel.send("\n".join(lines))
        logger.info(f"교정: {message.author} - {[c['original']+'→'+c['corrected'] for c in result['corrections']]}")

    except Exception as e:
        logger.error(f"메시지 처리 중 오류: {e}", exc_info=True)


@bot.command(name="통계", aliases=["stats"])
async def stats(ctx, target_user: discord.Member = None):
    """이번 달 맞춤법 오류 통계. 사용법: !통계 / !통계 @유저"""
    if target_user is None:
        target_user = ctx.author

    user_id = str(target_user.id)
    month_key = datetime.now().strftime("%Y-%m")
    month_display = datetime.now().strftime("%Y년 %m월")

    user_month = user_spell_counts.get(user_id, {}).get(month_key)

    if not user_month or not any(k != "_total" for k in user_month):
        await ctx.send(f"**{target_user.display_name}** 님은 {month_display}에 맞춤법을 틀린 기록이 없습니다!")
        return

    error_stats = {k: v for k, v in user_month.items() if k != "_total"}
    sorted_stats = sorted(error_stats.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"{target_user.display_name} 님의 {month_display} 맞춤법 통계",
        color=discord.Color.blue(),
    )

    lines = []
    for rank, (key, count) in enumerate(sorted_stats, 1):
        lines.append(f"**{rank}.** {key} — **{count}회**")

    lines.append(make_accuracy_bar(user_month))

    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


@bot.command(name="전체통계", aliases=["allstats"])
async def all_stats(ctx, target_user: discord.Member = None):
    """전체 누적 맞춤법 오류 통계. 사용법: !전체통계 / !전체통계 @유저"""
    if target_user is None:
        target_user = ctx.author

    user_id = str(target_user.id)
    user_data = user_spell_counts.get(user_id)

    if not user_data:
        await ctx.send(f"**{target_user.display_name}** 님은 맞춤법을 틀린 기록이 없습니다!")
        return

    # 모든 월의 통계를 합산
    total = {}
    for month_counts in user_data.values():
        for key, count in month_counts.items():
            total[key] = total.get(key, 0) + count

    error_stats = {k: v for k, v in total.items() if k != "_total"}
    sorted_stats = sorted(error_stats.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"{target_user.display_name} 님의 전체 누적 맞춤법 통계",
        color=discord.Color.purple(),
    )

    lines = []
    for rank, (key, count) in enumerate(sorted_stats, 1):
        lines.append(f"**{rank}.** {key} — **{count}회**")

    lines.append(make_accuracy_bar(total))

    embed.description = "\n".join(lines)
    await ctx.send(embed=embed)


@bot.command(name="도움")
async def help_command(ctx):
    """되/돼 봇 사용법을 안내합니다."""
    embed = discord.Embed(
        title="되/돼 맞춤법 봇",
        description=(
            "채팅에서 '되'와 '돼'의 잘못된 사용을 자동으로 감지하고 교정해 드립니다.\n\n"
            "**기본 규칙**\n"
            "• '돼' = '되어'의 줄임말\n"
            "• '되어'로 바꿔서 자연스러우면 → **돼**\n"
            "• '되어'로 바꿔서 어색하면 → **되**\n\n"
            "**자주 틀리는 예시**\n"
            "• ~~되서~~ → 돼서 (되어서)\n"
            "• ~~되요~~ → 돼요 (되어요)\n"
            "• ~~돼고~~ → 되고\n"
            "• ~~돼면~~ → 되면\n\n"
            "**명령어**\n"
            "• `!통계` - 이번 달 내 맞춤법 통계\n"
            "• `!통계 @유저` - 해당 유저의 이번 달 통계\n"
            "• `!전체통계` - 전체 누적 맞춤법 통계\n"
            "• `!전체통계 @유저` - 해당 유저의 전체 통계\n"
            "• `!도움` - 이 도움말 표시"
        ),
        color=discord.Color.green(),
    )
    await ctx.send(embed=embed)


bot.run(DISCORD_TOKEN)
