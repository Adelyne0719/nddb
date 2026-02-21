import os
import json
import discord
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv
from grammar_checker import GrammarChecker

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 파일 경로
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COUNT_FILE = os.path.join(SCRIPT_DIR, "spell_check_counts.json")

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)
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
    with open(COUNT_FILE, "w", encoding="utf-8") as f:
        json.dump(counts, f, indent=4, ensure_ascii=False)


user_spell_counts = load_counts()


@bot.event
async def on_ready():
    print(f"봇 로그인 완료: {bot.user.name}")


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

    result = await checker.check(message.content)

    if result is None:
        return

    # 교정 메시지 생성
    lines = [f"{message.author.mention} 님, '되/돼' 맞춤법을 확인해 주세요!\n"]

    month_key = datetime.now().strftime("%Y-%m")
    user_id = str(message.author.id)
    if user_id not in user_spell_counts:
        user_spell_counts[user_id] = {}
    if month_key not in user_spell_counts[user_id]:
        user_spell_counts[user_id][month_key] = {}
    user_month = user_spell_counts[user_id][month_key]

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


@bot.command(name="통계", aliases=["stats"])
async def stats(ctx, target_user: discord.Member = None):
    """이번 달 맞춤법 오류 통계. 사용법: !통계 / !통계 @유저"""
    if target_user is None:
        target_user = ctx.author

    user_id = str(target_user.id)
    month_key = datetime.now().strftime("%Y-%m")
    month_display = datetime.now().strftime("%Y년 %m월")

    user_month = user_spell_counts.get(user_id, {}).get(month_key)

    if not user_month:
        await ctx.send(f"**{target_user.display_name}** 님은 {month_display}에 맞춤법을 틀린 기록이 없습니다!")
        return

    sorted_stats = sorted(user_month.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"{target_user.display_name} 님의 {month_display} 맞춤법 통계",
        color=discord.Color.blue(),
    )

    lines = []
    for rank, (key, count) in enumerate(sorted_stats, 1):
        lines.append(f"**{rank}.** {key} — **{count}회**")

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

    sorted_stats = sorted(total.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"{target_user.display_name} 님의 전체 누적 맞춤법 통계",
        color=discord.Color.purple(),
    )

    lines = []
    for rank, (key, count) in enumerate(sorted_stats, 1):
        lines.append(f"**{rank}.** {key} — **{count}회**")

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
