import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from grammar_checker import GrammarChecker

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 봇 설정
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
checker = GrammarChecker(api_key=GEMINI_API_KEY)


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

    # '되' 또는 '돼'가 포함된 메시지만 검사
    if '되' not in message.content and '돼' not in message.content:
        return

    result = await checker.check(message.content)

    if result is None:
        return

    # 교정 메시지 생성
    lines = [f"{message.author.mention} 님, '되/돼' 맞춤법을 확인해 주세요!\n"]

    for c in result["corrections"]:
        lines.append(f"❌ {c['original']}  →  ✅ {c['corrected']}")
        lines.append(f"💡 {c['explanation']}\n")

    await message.channel.send("\n".join(lines))


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
            "• `!도움` - 이 도움말 표시"
        ),
        color=discord.Color.green(),
    )
    await ctx.send(embed=embed)


bot.run(DISCORD_TOKEN)
