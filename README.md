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

## Running in the Cloud (GitHub Actions)

The repository includes a workflow (`.github/workflows/run-bot.yml`) that keeps the bot running continuously using GitHub Actions — no external server required.

**How it works:**
- A scheduled job starts every 6 hours and runs the bot for ~5 h 50 min.
- The SQLite database (`steam_watchlist.db`) is persisted between runs via the Actions cache, so tracked games and channel settings survive restarts.
- There is a brief restart window of ~10 minutes every 6 hours.
- You can also trigger a manual run at any time from the **Actions** tab.

**Setup:**
1. Go to **Settings → Secrets and variables → Actions** in your repository.
2. Add the following repository secrets:
   - `DISCORD_TOKEN` — your Discord bot token
   - `STEAM_API_KEY` — your Steam API key
3. Enable Actions if they are not already active (**Settings → Actions → General**).
4. The bot will start automatically on the next scheduled trigger, or you can start it immediately via **Actions → Run Discord Bot → Run workflow**.

> **Note:** GitHub Actions minutes are free for public repositories. For private repositories the free tier provides 2 000 minutes/month; continuous operation (~720 h/month) will exceed that and incur charges.

## Notes

- The bot will send update notifications to the first available text channel in each guild.
- The project stores tracked games in `steam_watchlist.db`.
- You can add your Steam API key later; tracking will work once the key is configured.
