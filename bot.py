import asyncio
import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from db import SteamDatabase
from steam_tracker import SteamTracker

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
STEAM_API_KEY = os.getenv("STEAM_API_KEY")
COMMAND_PREFIX = "!"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("Steam update tracker is ready.")
    print("Loaded cogs:", list(bot.cogs.keys()))
    print("Available commands:", [c.name for c in bot.commands])


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

    print(f"Command error in {ctx.command}: {error}")


async def main():
    database = SteamDatabase("steam_watchlist.db")
    database.init_db()
    tracker = SteamTracker(bot, database, STEAM_API_KEY)
    print("Created SteamTracker instance:", tracker)
    print("Is Cog instance:", isinstance(tracker, commands.Cog))
    try:
        await bot.add_cog(tracker)
    except Exception as exc:
        print("Failed to load SteamTracker cog:", exc)
        raise

    print("Cogs loaded on startup:", list(bot.cogs.keys()))
    print("Commands loaded on startup:", [c.name for c in bot.commands])

    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is not set. Add it to .env before running the bot.")

    async with bot:
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
