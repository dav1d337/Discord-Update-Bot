@echo off
setlocal
if not exist ".venv\Scripts\activate.bat" (
    echo Virtual environment not found.
    echo Run: python -m venv .venv
    echo Then install dependencies with: pip install -r requirements.txt
    goto end
)
call .venv\Scripts\activate.bat
python bot.py
:end
endlocal
