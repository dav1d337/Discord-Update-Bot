import asyncio
import logging
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

import aiohttp
import discord
from discord.ext import commands, tasks
from db import SteamDatabase

STEAM_NEWS_URL = "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"
STEAM_STORE_SEARCH_URL = "https://store.steampowered.com/api/storesearch"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

logger = logging.getLogger(__name__)

# Heuristics to identify Steam news that usually represent real downloadable updates.
POSITIVE_UPDATE_KEYWORDS = {
    "patch notes",
    "patchnotes",
    "patch",
    "update",
    "hotfix",
    "changelog",
    "version",
    "build",
    "download",
    "client update",
}
NEGATIVE_UPDATE_KEYWORDS = {
    "sale",
    "discount",
    "event",
    "tournament",
    "stream",
    "livestream",
    "soundtrack",
    "merch",
    "artwork",
    "screenshot",
    "community hub",
    "maintenance notice",
}
UPDATE_TAG_HINTS = {"patchnotes", "patchnote", "update", "updates", "product update"}

class SteamTracker(commands.Cog):
    def __init__(self, bot: commands.Bot, database: SteamDatabase, steam_api_key: str | None):
        super().__init__()
        print("Initializing SteamTracker cog")
        self.bot = bot
        self.database = database
        self.api_key = steam_api_key
        self.session = None

    def cog_unload(self) -> None:
        self.check_updates_loop.cancel()
        if self.session is not None:
            self.bot.loop.create_task(self.session.close())

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        if not self.check_updates_loop.is_running():
            self.log_tracked_games_snapshot()
            await self.check_updates_once()
            self.check_updates_loop.start()

    async def check_updates_once(self) -> None:
        if not self.api_key:
            return

        await self.ensure_session()
        tracked_games = self.database.list_games()
        if not tracked_games:
            return

        updates = []
        for game in tracked_games:
            appid = game["appid"]
            latest = await self.find_latest_relevant_update(game)
            if not latest:
                continue

            stored_last_id = game["last_news_id"]
            if stored_last_id is None or stored_last_id == "":
                self.database.update_game_news(
                    appid,
                    latest.get("gid"),
                    latest.get("date", 0),
                    last_news_title=latest.get("title"),
                )
                continue

            if self.is_news_new_for_game(latest, game):
                self.database.update_game_news(
                    appid,
                    latest.get("gid"),
                    latest.get("date", 0),
                    last_news_title=latest.get("title"),
                )
                updates.append((game, latest))

        if updates:
            await self.broadcast_updates(updates)

    @tasks.loop(minutes=10)
    async def check_updates_loop(self) -> None:
        await self.check_updates_once()

    async def ensure_session(self) -> None:
        if self.session is None:
            self.session = aiohttp.ClientSession()

    @check_updates_loop.before_loop
    async def before_update_loop(self) -> None:
        await self.bot.wait_until_ready()
        await self.ensure_session()

    async def fetch_latest_news(self, appid: str) -> dict | None:
        newsitems = await self.fetch_recent_news(appid, count=3)
        return newsitems[0] if newsitems else None

    async def fetch_recent_news(self, appid: str, count: int = 10) -> list[dict]:
        params = {
            "appid": appid,
            "count": count,
            "maxlength": 300,
            "format": "json",
            "key": self.api_key,
        }
        try:
            await self.ensure_session()
            async with self.session.get(STEAM_NEWS_URL, params=params, timeout=20) as response:
                if response.status != 200:
                    logger.warning("Steam news request failed for appid %s with status %s", appid, response.status)
                    return []
                data = await response.json()
        except asyncio.TimeoutError:
            logger.warning("Steam news request timed out for appid %s", appid)
            return []
        except aiohttp.ClientError as error:
            logger.warning("Steam news request failed for appid %s: %s", appid, error)
            return []

        newsitems = data.get("appnews", {}).get("newsitems", [])
        if not isinstance(newsitems, list):
            return []
        return newsitems

    def compose_news_text(self, item: dict) -> str:
        tags = item.get("tags")
        joined_tags = ""
        if isinstance(tags, list):
            joined_tags = " ".join(str(tag) for tag in tags)
        elif isinstance(tags, str):
            joined_tags = tags

        parts = [
            str(item.get("title") or ""),
            str(item.get("contents") or ""),
            str(item.get("feedlabel") or ""),
            str(item.get("feedname") or ""),
            str(item.get("url") or ""),
            joined_tags,
        ]
        return " ".join(parts).lower()

    def is_download_update_news(self, item: dict) -> bool:
        tags = item.get("tags")
        if isinstance(tags, list):
            lowered_tags = {str(tag).lower() for tag in tags}
        elif isinstance(tags, str):
            lowered_tags = {tags.lower()}
        else:
            lowered_tags = set()

        if lowered_tags.intersection(UPDATE_TAG_HINTS):
            return True

        text = self.compose_news_text(item)
        has_positive = any(keyword in text for keyword in POSITIVE_UPDATE_KEYWORDS)
        has_negative = any(keyword in text for keyword in NEGATIVE_UPDATE_KEYWORDS)

        if has_positive and not has_negative:
            return True

        # Keep update-oriented posts even if they contain event wording.
        if has_positive and ("patch" in text or "hotfix" in text or "changelog" in text):
            return True

        return False

    def is_news_new_for_game(self, news: dict, game: dict) -> bool:
        news_gid = str(news.get("gid") or "")
        news_date = int(news.get("date") or 0)
        stored_gid = str(game.get("last_news_id") or "")
        stored_date = int(game.get("last_news_date") or 0)

        if not news_gid:
            return False
        if news_gid == stored_gid:
            return False
        return news_date >= stored_date

    async def find_latest_relevant_update(self, game: dict) -> dict | None:
        appid = str(game["appid"])
        newsitems = await self.fetch_recent_news(appid, count=10)
        if not newsitems:
            return None

        stored_gid = str(game.get("last_news_id") or "")
        stored_date = int(game.get("last_news_date") or 0)
        for item in newsitems:
            if not self.is_download_update_news(item):
                continue

            candidate_gid = str(item.get("gid") or "")
            candidate_date = int(item.get("date") or 0)
            if not candidate_gid:
                continue
            if stored_gid and candidate_gid == stored_gid:
                continue
            if stored_date and candidate_date < stored_date:
                continue
            return item
        return None

    def format_news_date(self, timestamp: int | None) -> str:
        if not timestamp:
            return "n/a"
        return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()

    def log_tracked_games_snapshot(self) -> None:
        tracked_games = self.database.list_games()
        logger.info("Tracked games on startup: %d", len(tracked_games))
        for game in tracked_games:
            logger.info(
                "Tracked game appid=%s name=%s last_news_id=%s last_news_date=%s last_news_title=%s",
                game.get("appid"),
                game.get("name") or "",
                game.get("last_news_id") or "",
                self.format_news_date(game.get("last_news_date")),
                game.get("last_news_title") or "",
            )

    async def fetch_app_title(self, appid: str) -> str | None:
        params = {
            "appids": appid,
            "cc": "us",
            "l": "en",
        }
        try:
            await self.ensure_session()
            async with self.session.get(STEAM_APP_DETAILS_URL, params=params, timeout=20) as response:
                if response.status != 200:
                    return None
                data = await response.json()
        except asyncio.TimeoutError:
            return None
        except aiohttp.ClientError:
            return None

        app_data = data.get(str(appid), {})
        if not app_data.get("success"):
            return None

        return app_data.get("data", {}).get("name")

    async def search_games(self, query: str) -> list[dict]:
        params = {
            "term": query,
            "cc": "us",
            "l": "en",
            "v": "2",
        }
        try:
            await self.ensure_session()
            async with self.session.get(STEAM_STORE_SEARCH_URL, params=params, timeout=20) as response:
                if response.status != 200:
                    return []
                data = await response.json()
        except asyncio.TimeoutError:
            return []
        except aiohttp.ClientError:
            return []

        results = []
        for item in data.get("items", []):
            appid = item.get("id")
            name = item.get("name")
            if appid and name:
                results.append({"appid": str(appid), "name": name})
        return results

    def format_update_size(self, size: int | str | None) -> str:
        if size is None or size == "":
            return "Nicht verfügbar"
        if isinstance(size, str):
            size = size.strip()
            if size.isdigit():
                size = int(size)
        if isinstance(size, int):
            units = ["B", "KB", "MB", "GB", "TB"]
            value = float(size)
            for unit in units:
                if value < 1024.0 or unit == units[-1]:
                    return f"{value:.1f} {unit}"
                value /= 1024.0
            return f"{value:.1f} PB"
        return str(size)

    def is_valid_url(self, url: str | None) -> bool:
        if not url:
            return False
        parsed = urlparse(url)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def normalize_news_url(self, url: str | None) -> str | None:
        if not url:
            return None
        normalized = url.strip()
        if normalized.startswith("//"):
            normalized = "https:" + normalized
        elif normalized.startswith("/"):
            normalized = "https://store.steampowered.com" + normalized
        elif not normalized.startswith("http://") and not normalized.startswith("https://"):
            normalized = "https://" + normalized

        if self.is_valid_url(normalized):
            return normalized
        return None

    def is_trusted_news_url(self, url: str | None) -> bool:
        if not self.is_valid_url(url):
            return False
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        return domain.endswith("steampowered.com") or domain.endswith("steamcommunity.com")

    def get_news_url(self, latest: dict, appid: str | None = None) -> str | None:
        url = self.normalize_news_url(latest.get("url"))
        if url and self.is_trusted_news_url(url):
            return url
        if appid:
            return f"https://store.steampowered.com/news/app/{appid}"
        return url

    def format_link_field(self, url: str | None) -> str:
        if not url:
            return "Keine URL verfügbar."
        return f"<{url}>"

    def safe_set_embed_url(self, embed: discord.Embed, url: str | None) -> None:
        if not url:
            return
        if not self.is_valid_url(url):
            return
        try:
            embed.url = url
        except (discord.HTTPException, ValueError):
            return

    def extract_news_image(self, latest: dict) -> str | None:
        candidates = [
            latest.get("image"),
            latest.get("thumbnail"),
            latest.get("thumbnail_url"),
            latest.get("image_url"),
        ]
        for image_url in candidates:
            if image_url:
                return self.normalize_news_url(str(image_url))

        contents = latest.get("contents")
        if isinstance(contents, str):
            match = re.search(r"(https?://[^\s'\"]+\.(?:png|jpe?g|gif))", contents)
            if match:
                return match.group(1)
        return None

    def build_update_embed(self, game: dict, latest: dict) -> discord.Embed:
        link = self.get_news_url(latest, game["appid"])
        embed = discord.Embed(
            title=f"Steam update: {game.get('name') or game['appid']}",
            description=latest.get("title", "Neue News verfügbar."),
            color=0x1B2838,
        )
        self.safe_set_embed_url(embed, link)
        embed.add_field(name="AppID", value=game["appid"], inline=True)
        embed.add_field(
            name="Published",
            value=f"<t:{latest.get('date')}:f>" if latest.get("date") else "Unbekannt",
            inline=True,
        )
        embed.add_field(
            name="Size",
            value=self.format_update_size(latest.get("size") or latest.get("bytes")),
            inline=True,
        )
        image = self.extract_news_image(latest)
        if image:
            embed.set_thumbnail(url=image)
        embed.add_field(
            name="Link",
            value=self.format_link_field(link),
            inline=False,
        )
        return embed

    async def broadcast_updates(self, updates: list[tuple[dict, dict]]) -> None:
        for guild in self.bot.guilds:
            channel = await self.get_notification_channel(guild)
            if not channel:
                continue

            for game, latest in updates:
                embed = self.build_update_embed(game, latest)
                try:
                    await channel.send(embed=embed)
                except discord.HTTPException as error:
                    if "Invalid Form Body" in str(error) and "embeds.0.url" in str(error):
                        embed.url = None
                        await channel.send(embed=embed)
                    else:
                        raise

    def get_default_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            return guild.system_channel
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                return channel
        return None

    async def get_notification_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        channel_id = self.database.get_notification_channel(guild.id)
        if channel_id is None:
            return self.get_default_channel(guild)

        channel = guild.get_channel(channel_id)
        if (
            isinstance(channel, discord.TextChannel)
            and channel.permissions_for(guild.me).send_messages
        ):
            return channel
        return self.get_default_channel(guild)

    @commands.command(name="addgame")
    async def add_game(self, ctx: commands.Context, *, query: str) -> None:
        if query.isdigit():
            appid = query
            if self.database.get_game(appid):
                await ctx.reply(f"AppID {appid} wird bereits verfolgt.", mention_author=False)
                return

            name = await self.fetch_app_title(appid) or "Unbekannt"
            latest = await self.find_latest_relevant_update({"appid": appid, "last_news_id": "", "last_news_date": 0}) if self.api_key else None
            if latest:
                self.database.add_game(
                    appid,
                    name=name,
                    last_news_id=latest.get("gid"),
                    last_news_date=latest.get("date", 0),
                    last_news_title=latest.get("title"),
                )
                await ctx.reply(
                    f"Spiel {name} ({appid}) hinzugefügt und Basis-News gesetzt. Ich melde neue Steam-News, sobald sie erscheinen.",
                    mention_author=False,
                )
                return

            self.database.add_game(appid, name=name)
            await ctx.reply(
                f"Spiel {name} ({appid}) hinzugefügt. Es wurden aktuell keine Steam-News gefunden oder die API ist noch nicht konfiguriert.",
                mention_author=False,
            )
            return

        results = await self.search_games(query)
        if not results:
            await ctx.reply(
                "Kein Spiel mit diesem Namen gefunden. Bitte versuche es mit einer anderen Schreibweise oder der AppID.",
                mention_author=False,
            )
            return

        if len(results) > 1:
            lines = [f"{idx + 1}. {item['name']} ({item['appid']})" for idx, item in enumerate(results[:10])]
            message = (
                "Mehrere Spiele gefunden. Bitte verwende die AppID für die richtige Auswahl:\n"
                + "\n".join(lines)
            )
            await ctx.reply(message, mention_author=False)
            return

        app = results[0]
        appid = app["appid"]
        name = app["name"]
        if self.database.get_game(appid):
            await ctx.reply(f"AppID {appid} ({name}) wird bereits verfolgt.", mention_author=False)
            return

        latest = await self.find_latest_relevant_update({"appid": appid, "last_news_id": "", "last_news_date": 0}) if self.api_key else None
        if latest:
            self.database.add_game(
                appid,
                name=name,
                last_news_id=latest.get("gid"),
                last_news_date=latest.get("date", 0),
                last_news_title=latest.get("title"),
            )
            await ctx.reply(
                f"Spiel {name} ({appid}) hinzugefügt und Basis-News gesetzt. Ich melde neue Steam-News, sobald sie erscheinen.",
                mention_author=False,
            )
            return

        self.database.add_game(appid, name=name)
        await ctx.reply(
            f"Spiel {name} ({appid}) hinzugefügt. Es wurden aktuell keine Steam-News gefunden oder die API ist noch nicht konfiguriert.",
            mention_author=False,
        )

    @commands.command(name="latestnews", aliases=["news"])
    async def latest_news(self, ctx: commands.Context, *, query: str) -> None:
        if not self.api_key:
            await ctx.reply(
                "Der Steam API-Schlüssel ist nicht gesetzt. Bitte füge STEAM_API_KEY zur .env hinzu.",
                mention_author=False,
            )
            return

        if query.isdigit():
            game = self.database.get_game(query)
            if not game:
                await ctx.reply(
                    f"AppID {query} ist nicht in der verfolgten Steam-Datenbank.",
                    mention_author=False,
                )
                return
            appid = query
            game_name = game.get("name") or query
        else:
            matches = self.database.find_games_by_name(query)
            if not matches:
                await ctx.reply(
                    "Kein verfolgtes Spiel mit diesem Namen gefunden. Bitte verwende die AppID oder einen anderen Namen.",
                    mention_author=False,
                )
                return
            if len(matches) > 1:
                lines = [f"{idx + 1}. {item['name']} ({item['appid']})" for idx, item in enumerate(matches[:10])]
                message = (
                    "Mehrere Spiele gefunden. Bitte verwende die AppID für die richtige Auswahl:\n"
                    + "\n".join(lines)
                )
                await ctx.reply(message, mention_author=False)
                return
            app = matches[0]
            appid = app["appid"]
            game_name = app.get("name") or appid

        latest = await self.find_latest_relevant_update({"appid": appid, "last_news_id": "", "last_news_date": 0})
        if not latest:
            await ctx.reply(
                "Es wurden keine aktuellen update-relevanten Steam-News gefunden oder die Steam-API konnte nicht erreicht werden.",
                mention_author=False,
            )
            return

        embed = self.build_update_embed({"appid": appid, "name": game_name}, latest)
        try:
            await ctx.send(embed=embed)
        except discord.HTTPException as error:
            if "Invalid Form Body" in str(error) and "embeds.0.url" in str(error):
                embed.url = None
                await ctx.send(embed=embed)
            else:
                raise

    @latest_news.error
    async def latest_news_error(self, ctx: commands.Context, error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                "Bitte gib eine AppID oder einen Spielnamen an. Beispiel: `!latestnews 440` oder `!news Half-Life`.",
                mention_author=False,
            )
            return
        if isinstance(error, commands.CommandInvokeError):
            await ctx.reply(
                "Beim Abrufen der Steam-News ist ein Fehler aufgetreten. Bitte versuche es später erneut.",
                mention_author=False,
            )
            return

    @commands.command(name="removegame")
    async def remove_game(self, ctx: commands.Context, appid: str) -> None:
        if not self.database.get_game(appid):
            await ctx.reply(f"AppID {appid} ist nicht in der Liste.", mention_author=False)
            return

        self.database.remove_game(appid)
        await ctx.reply(f"AppID {appid} wurde aus der Verfolgung entfernt.", mention_author=False)

    @commands.command(name="listgames")
    async def list_games(self, ctx: commands.Context) -> None:
        games = self.database.list_games()
        if not games:
            await ctx.reply("Es sind derzeit keine Spiele in der Verfolgung.", mention_author=False)
            return

        lines = [f"{game['appid']} — {game.get('name') or 'Unbekannt'}" for game in games]
        message = "Verfolgte Spiele:\n" + "\n".join(lines)
        await ctx.reply(message, mention_author=False)

    @commands.command(name="setchannel")
    async def set_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        if ctx.guild is None:
            await ctx.reply("Dieser Befehl kann nur in einem Server verwendet werden.", mention_author=False)
            return

        self.database.set_notification_channel(ctx.guild.id, channel.id)
        await ctx.reply(
            f"Benachrichtigungen werden jetzt in {channel.mention} gesendet.",
            mention_author=False,
        )

    @commands.command(name="removechannel")
    async def remove_channel(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.reply("Dieser Befehl kann nur in einem Server verwendet werden.", mention_author=False)
            return

        self.database.remove_notification_channel(ctx.guild.id)
        await ctx.reply(
            "Der feste Benachrichtigungskanal wurde entfernt. Der Bot verwendet nun wieder den Standardkanal.",
            mention_author=False,
        )

    @commands.command(name="checkupdates")
    async def check_updates(self, ctx: commands.Context) -> None:
        if not self.api_key:
            await ctx.reply("Der Steam API-Schlüssel ist nicht gesetzt. Bitte füge STEAM_API_KEY zur .env hinzu.", mention_author=False)
            return

        await ctx.reply("Prüfe aktuelle Steam-News für verfolgte Spiele...", mention_author=False)
        tracked_games = self.database.list_games()
        if not tracked_games:
            await ctx.reply("Es sind keine Spiele zum Prüfen hinterlegt.", mention_author=False)
            return

        updates = []
        for game in tracked_games:
            latest = await self.find_latest_relevant_update(game)
            if not latest:
                continue

            stored_last_id = game["last_news_id"]
            if stored_last_id and self.is_news_new_for_game(latest, game):
                self.database.update_game_news(
                    game["appid"],
                    latest.get("gid"),
                    latest.get("date", 0),
                    last_news_title=latest.get("title"),
                )
                updates.append((game, latest))

        if not updates:
            await ctx.reply("Keine neuen update-relevanten Steam-News für die verfolgten Spiele gefunden.", mention_author=False)
            return

        for game, latest in updates:
            embed = self.build_update_embed(game, latest)
            try:
                await ctx.send(embed=embed)
            except discord.HTTPException as error:
                if "Invalid Form Body" in str(error) and "embeds.0.url" in str(error):
                    embed.url = None
                    await ctx.send(embed=embed)
                else:
                    raise
