import os
import io
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
BASE_URL = "https://biquote.io"
EXPIRY_SECONDS = 10
MIN_SCORE = 90
SYMBOLS = {
    "eurusd": "EURUSD",
    "gbpusd": "GBPUSD",
    "usdjpy": "USDJPY",
    "audusd": "AUDUSD",
    "xauusd": "XAUUSD",
    "gold": "XAUUSD",
    "gbpjpy": "GBPJPY",
    "eurjpy": "EURJPY",
    "usdcad": "USDCAD",
}
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("ai-trader-pro")
session = requests.Session()
session.headers.update({"User-Agent": "AI-TRADER-PRO/1.0"})


def fetch_candles(symbol: str) -> pd.DataFrame:
    """Fetch closed 1-minute candles. Never use an unfinished candle."""
    response = session.get(
        f"{BASE_URL}/api/{symbol}/ohlc",
        params={"interval": "1m", "limit": 160},
        timeout=12,
    )
    response.raise_for_status()
    payload = response.json()
    bars = payload.get("bars", [])
    if not bars:
        raise ValueError("Aucune bougie disponible.")
    df = pd.DataFrame(bars)
    required = {"openTime", "open", "high", "low", "close", "isOpen"}
    if not required.issubset(df.columns):
        raise ValueError("Format de données inattendu.")
    df = df[df["isOpen"] == False].copy()  # noqa: E712
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df.sort_values("openTime").reset_index(drop=True)
    if len(df) < 60:
        raise ValueError("Pas assez de bougies clôturées pour analyser.")
    last_time = pd.to_datetime(df.iloc[-1]["openTime"], utc=True)
    age = (datetime.now(timezone.utc) - last_time.to_pydatetime()).total_seconds()
    # 1m candle start may be up to ~2 minutes old after it closes.
    if age > 150:
        raise ValueError("Les données sont trop anciennes. Réessaie plus tard.")
    return df


def indicators(df: pd.DataFrame) -> dict:
    close = df["close"]
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    ema9 = close.ewm(span=9, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    mid = close.rolling(20).mean()
    std = close.rolling(20).std()
    upper = mid + 2 * std
    lower = mid - 2 * std
    low14 = df["low"].rolling(14).min()
    high14 = df["high"].rolling(14).max()
    stoch = 100 * (close - low14) / (high14 - low14).replace(0, np.nan)
    values = {
        "price": float(close.iloc[-1]),
        "rsi": float(rsi.iloc[-1]),
        "ema9": float(ema9.iloc[-1]),
        "ema21": float(ema21.iloc[-1]),
        "macd": float(macd.iloc[-1]),
        "macd_signal": float(signal.iloc[-1]),
        "upper": float(upper.iloc[-1]),
        "lower": float(lower.iloc[-1]),
        "stoch": float(stoch.iloc[-1]),
    }
    if not all(np.isfinite(v) for v in values.values()):
        raise ValueError("Indicateurs incomplets.")
    return values


def analyse(symbol: str) -> dict:
    df = fetch_candles(symbol)
    x = indicators(df)
    buy = 0
    sell = 0
    reasons = []

    if x["ema9"] > x["ema21"]:
        buy += 20
        reasons.append("EMA 9 au-dessus EMA 21")
    elif x["ema9"] < x["ema21"]:
        sell += 20
        reasons.append("EMA 9 sous EMA 21")

    if x["macd"] > x["macd_signal"]:
        buy += 20
        reasons.append("MACD haussier")
    elif x["macd"] < x["macd_signal"]:
        sell += 20
        reasons.append("MACD baissier")

    if 50 < x["rsi"] < 70:
        buy += 20
        reasons.append("RSI orienté à la hausse")
    elif 30 < x["rsi"] < 50:
        sell += 20
        reasons.append("RSI orienté à la baisse")

    if x["stoch"] > 50:
        buy += 15
        reasons.append("Stochastique au-dessus de 50")
    elif x["stoch"] < 50:
        sell += 15
        reasons.append("Stochastique sous 50")

    if x["price"] > (x["upper"] + x["lower"]) / 2:
        buy += 15
        reasons.append("Prix au-dessus de la médiane Bollinger")
    elif x["price"] < (x["upper"] + x["lower"]) / 2:
        sell += 15
        reasons.append("Prix sous la médiane Bollinger")

    score = max(buy, sell)
    direction = "BUY" if buy > sell else "SELL" if sell > buy else "AUCUN SIGNAL"
    # The score is a rule-confluence score, NOT a probability of winning.
    if score < MIN_SCORE or buy == sell:
        direction = "AUCUN SIGNAL"

    return {
        "symbol": symbol,
        "direction": direction,
        "score": score,
        "price": x["price"],
        "rsi": x["rsi"],
        "stoch": x["stoch"],
        "reasons": reasons,
    }


def make_signal_image(direction: str, symbol: str, score: int) -> io.BytesIO:
    color = (24, 150, 95) if direction == "BUY" else (190, 55, 55)
    image = Image.new("RGB", (900, 420), (17, 24, 39))
    draw = ImageDraw.Draw(image)
    try:
        big = ImageFont.truetype("DejaVuSans-Bold.ttf", 105)
        medium = ImageFont.truetype("DejaVuSans-Bold.ttf", 48)
        small = ImageFont.truetype("DejaVuSans.ttf", 27)
    except OSError:
        big = medium = small = ImageFont.load_default()
    draw.rounded_rectangle((35, 35, 865, 385), radius=30, fill=(30, 41, 59))
    draw.text((75, 65), "AI TRADER PRO", font=medium, fill=(255, 255, 255))
    draw.text((75, 145), direction, font=big, fill=color)
    draw.text((80, 285), f"{symbol}  |  Score technique : {score}/100", font=small, fill=(220, 226, 235))
    draw.text((80, 335), "Expiration demandee : 10 secondes", font=small, fill=(170, 182, 198))
    output = io.BytesIO()
    image.save(output, format="PNG")
    output.seek(0)
    return output


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "BIENVENUE SUR AI TRADER PRO\n\n"
        "Analyses manuelles uniquement.\n"
        "Expiration visée : 10 secondes\n"
        "Score minimum : 90/100 (score technique, pas une probabilité).\n\n"
        "Commandes :\n"
        "/eurusd  /gbpusd  /usdjpy  /audusd\n"
        "/gold  /gbpjpy  /eurjpy  /usdcad\n"
        "/signal — liste des marchés disponibles\n"
        "/help — aide\n\n"
        "Un signal n'est jamais une garantie de gain."
    )
    await update.message.reply_text(text)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def send_analysis(update: Update, symbol: str):
    await update.message.reply_text(f"Analyse de {symbol} en cours...")
    try:
        result = analyse(symbol)
        if result["direction"] == "AUCUN SIGNAL":
            await update.message.reply_text(
                f"📊 {symbol}\nAUCUN SIGNAL\n"
                f"Score technique : {result['score']}/100\n"
                "Le seuil minimum de 90/100 n'est pas atteint.\n"
                "Aucune entrée recommandée."
            )
            return
        caption = (
            f"📊 {symbol}\n"
            f"Signal : {result['direction']}\n"
            f"Score de confluence : {result['score']}/100\n"
            f"Prix indicatif : {result['price']}\n"
            f"RSI 14 : {result['rsi']:.1f} | Stoch : {result['stoch']:.1f}\n"
            f"Expiration visée : {EXPIRY_SECONDS} secondes\n\n"
            "⚠️ Score technique, pas une probabilité de réussite. "
            "Données BiQuote et indicateurs 1 minute : cela ne valide pas "
            "une prévision fiable à 10 secondes. Tester uniquement en démo."
        )
        photo = make_signal_image(result["direction"], symbol, result["score"])
        await update.message.reply_photo(photo=photo, caption=caption)
    except requests.RequestException as exc:
        log.warning("Market data request failed for %s: %s", symbol, exc)
        await update.message.reply_text(
            f"❌ Impossible de récupérer les données de {symbol}. "
            "AUCUN SIGNAL. Réessaie plus tard."
        )
    except Exception as exc:
        log.exception("Analysis failed for %s", symbol)
        await update.message.reply_text(
            f"❌ Analyse impossible pour {symbol}. AUCUN SIGNAL.\n"
            "Vérifie les données et réessaie plus tard."
        )


def make_symbol_handler(symbol: str):
    async def handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        await send_analysis(update, symbol)
    return handler


async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Choisis une paire pour lancer une analyse séparée :\n"
        "/eurusd /gbpusd /usdjpy /audusd\n"
        "/gold /gbpjpy /eurjpy /usdcad"
    )


def main():
    if not TOKEN:
        raise RuntimeError("La variable TELEGRAM_BOT_TOKEN est absente.")
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("signal", signal_command))
    for command, symbol in SYMBOLS.items():
        app.add_handler(CommandHandler(command, make_symbol_handler(symbol)))
    log.info("AI TRADER PRO démarre en mode webhook.")
    render_url = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    if not render_url:
        raise RuntimeError("RENDER_EXTERNAL_URL est absent. Déploie le bot comme Web Service sur Render.")
    port = int(os.getenv("PORT", "10000"))
    webhook_path = "telegram"
    webhook_secret = __import__("hashlib").sha256(
        ("AI-TRADER-PRO:" + TOKEN).encode("utf-8")
    ).hexdigest()[:32]
    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path=webhook_path,
        webhook_url=f"{render_url}/{webhook_path}",
        secret_token=webhook_secret,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
