import asyncio
import logging
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from db import SteamDatabase
from steam_tracker import SteamTracker

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
COMMAND_PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

@bot.event
async def on_ready():
    logger.info("Logged in as %s (ID: %s)", bot.user, bot.user.id)
    logger.info("Steam update tracker is ready.")
    logger.info("Loaded cogs: %s", list(bot.cogs.keys()))
    logger.info("Available commands: %s", [c.name for c in bot.commands])


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.reply(
            f"Fehlendes Argument: `{error.param.name}`. Verwendung: `!{ctx.command} <AppID|Spielname>`",
            mention_author=False,
        )
        return

    if isinstance(error, commands.CommandNotFound):
        return

    if isinstance(error, commands.CommandOnCooldown):
        await ctx.reply(str(error), mention_author=False)
        return

    logger.error("Command error in %s: %s", ctx.command, error)


async def main():
    database = SteamDatabase("steam_watchlist.db")
    database.init_db()
    tracker = SteamTracker(bot, database, STEAM_API_KEY)
    logger.info("Created SteamTracker instance: %s", tracker)
    logger.info("Is Cog instance: %s", isinstance(tracker, commands.Cog))
    try:
        await bot.add_cog(tracker)
    except Exception as exc:
        logger.exception("Failed to load SteamTracker cog: %s", exc)
        raise

    logger.info("Cogs loaded on startup: %s", list(bot.cogs.keys()))
    logger.info("Commands loaded on startup: %s", [c.name for c in bot.commands])

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to .env before running the bot.")

    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
