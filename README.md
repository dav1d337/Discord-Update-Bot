# Discord Steam Update Bot

A simple Discord bot to track Steam game updates using Steam news.

## Features
- Add Steam games by AppID
- Remove tracked games
- List tracked games
- Automatically check Steam news every 10 minutes
- Notify Discord when a game receives a new Steam news item

## Setup

1. Install Python 3.10 or newer.
2. Create a virtual environment (recommended):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
3. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
4. Copy `.env.example` to `.env` and fill in your values:
   ```powershell
   copy .env.example .env
   ```
5. Add your Discord bot token to `DISCORD_TOKEN`.
6. Add your Steam API key to `STEAM_API_KEY`.

## Running

```powershell
python bot.py
```

## Bot Commands

- `!addgame <appid>` — Adds a Steam game to the tracked list.
- `!removegame <appid>` — Removes a Steam game from tracking.
- `!listgames` — Lists all tracked games.
- `!setchannel #kanal` — Leitet automatische Steam-Benachrichtigungen in diesen Kanal.
- `!removechannel` — Entfernt den festen Benachrichtigungskanal und nutzt wieder den Standardkanal.
- `!checkupdates` — Checks Steam news manually for tracked games.

## Notes

- The bot will send update notifications to the first available text channel in each guild.
- The project stores tracked games in `steam_watchlist.db`.
- You can add your Steam API key later; tracking will work once the key is configured.
