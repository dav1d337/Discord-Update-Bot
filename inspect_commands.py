import discord
from discord.ext import commands
from db import SteamDatabase
from steam_tracker import SteamTracker

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

db = SteamDatabase(':memory:')
db.init_db()
tracker = SteamTracker(bot, db, 'dummy')
bot.add_cog(tracker)
print([c.name for c in bot.commands])
