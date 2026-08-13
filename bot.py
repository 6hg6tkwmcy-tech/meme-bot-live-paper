import asyncio
import json
import urllib.request
import websockets
from datetime import datetime

# ============================================================
# MEME BOT LIVE — PAPER TRADING
# ============================================================
# SOLO SIMULAZIONE
# Nessun wallet
# Nessuna chiave privata
# Nessuna transazione reale
# ============================================================


# ============================================================
# CONFIGURAZIONE
# ============================================================

STARTING_BALANCE = 100.00
POSITION_SIZE = 10.00

TAKE_PROFIT = 0.30       # +30%
STOP_LOSS = -0.20        # -20%

MAX_POSITIONS = 5
MIN_SCORE = 60

MAX_TOKEN_AGE_MINUTES = 60

PUMPPORTAL_WS = "wss://pumpportal.fun/api/data"

DEXSCREENER_URL = (
    "https://api.dexscreener.com/token-pairs/v1/solana/"
)


# ============================================================
# STATO PAPER TRADING
# ============================================================

balance = STARTING_BALANCE

positions = {}

closed_trades = []

analyzed_tokens = 0

buy_count = 0

sell_count = 0


# ============================================================
# UTILITÀ
# ============================================================

def now():
    return datetime.now().strftime("%H:%M:%S")


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(value, maximum))


# ============================================================
# DEX SCREENER
# ============================================================

def fetch_dex_data_sync(mint):
    """
    Recupera le coppie DEX del token da DEX Screener.
    Viene eseguito in un thread per non bloccare l'event loop.
    """

    try:
        url = DEXSCREENER_URL + mint

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "MemeBotLive/1.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=8
        ) as response:

            raw = response.read().decode("utf-8")

            data = json.loads(raw)

        if not isinstance(data, list):
            return None

        if not data:
            return None

        valid_pairs = []

        for pair in data:

            liquidity = safe_float(
                pair.get("liquidity", {}).get("usd")
            )

            if liquidity > 0:
                valid_pairs.append(pair)

        if not valid_pairs:
            return None

        valid_pairs.sort(
            key=lambda pair: safe_float(
                pair.get("liquidity", {}).get("usd")
            ),
            reverse=True
        )

        return valid_pairs[0]

    except Exception as error:

        print(
            f"⚠️ DEX Screener error: {error}"
        )

        return None


async def fetch_dex_data(mint):

    return await asyncio.to_thread(
        fetch_dex_data_sync,
        mint
    )


# ============================================================
# ESTRAZIONE DATI DEX
# ============================================================

def extract_market_data(pair):

    if not pair:
        return None

    liquidity = safe_float(
        pair.get("liquidity", {}).get("usd")
    )

    volume_5m = safe_float(
        pair.get("volume", {}).get("m5")
    )

    volume_1h = safe_float(
        pair.get("volume", {}).get("h1")
    )

    price_change_5m = safe_float(
        pair.get("priceChange", {}).get("m5")
    )

    price_change_1h = safe_float(
        pair.get("priceChange", {}).get("h1")
    )

    txns_5m = pair.get(
        "txns", {}
    ).get("m5", {})

    buys_5m = int(
        safe_float(
            txns_5m.get("buys")
        )
    )

    sells_5m = int(
        safe_float(
            txns_5m.get("sells")
        )
    )

    price = safe_float(
        pair.get("priceUsd")
    )

    market_cap = safe_float(
        pair.get("marketCap")
    )

    fdv = safe_float(
        pair.get("fdv")
    )

    pair_created = pair.get(
        "pairCreatedAt"
    )

    return {
        "price": price,
        "liquidity": liquidity,
        "volume_5m": volume_5m,
        "volume_1h": volume_1h,
        "price_change_5m": price_change_5m,
        "price_change_1h": price_change_1h,
        "buys_5m": buys_5m,
        "sells_5m": sells_5m,
        "market_cap": market_cap,
        "fdv": fdv,
        "pair_created_at": pair_created,
        "dex": pair.get("dexId"),
        "pair_address": pair.get("pairAddress"),
    }


# ============================================================
# RISK SCORE
# ============================================================

def calculate_risk(market):

    if not market:
        return 100

    liquidity = market["liquidity"]

    volume_5m = market["volume_5m"]

    market_cap = market["market_cap"]

    buys = market["buys_5m"]

    sells = market["sells_5m"]

    risk = 0

    # Liquidità troppo bassa
    if liquidity < 5_000:
        risk += 35

    elif liquidity < 15_000:
        risk += 20

    elif liquidity < 30_000:
        risk += 10

    # Volume molto basso
    if volume_5m < 1_000:
        risk += 20

    elif volume_5m < 5_000:
        risk += 10

    # Market cap estremamente basso
    if market_cap > 0 and market_cap < 20_000:
        risk += 10

    # Pressione di vendita
    total_txns = buys + sells

    if total_txns >= 10:

        sell_ratio = sells / total_txns

        if sell_ratio > 0.70:
            risk += 25

        elif sell_ratio > 0.60:
            risk += 15

    return clamp(risk, 0, 100)


# ============================================================
# FOMO / MOMENTUM SCORE
# ============================================================

def calculate_fomo(market):

    if not market:
        return 0

    score = 0

    price_5m = market["price_change_5m"]

    price_1h = market["price_change_1h"]

    volume_5m = market["volume_5m"]

    buys = market["buys_5m"]

    sells = market["sells_5m"]

    total = buys + sells

    # Momentum prezzo
    if 2 <= price_5m <= 10:
        score += 20

    elif 10 < price_5m <= 25:
        score += 15

    elif price_5m > 25:
        # Movimento troppo verticale:
        # possibile ingresso tardivo
        score += 5

    elif price_5m > 0:
        score += 8

    # Momentum 1h
    if 5 <= price_1h <= 40:
        score += 10

    elif price_1h > 40:
        score += 5

    # Volume
    if volume_5m >= 50_000:
        score += 15

    elif volume_5m >= 20_000:
        score += 12

    elif volume_5m >= 5_000:
        score += 7

    # Buy pressure
    if total >= 10:

        buy_ratio = buys / total

        if buy_ratio >= 0.70:
            score += 15

        elif buy_ratio >= 0.60:
            score += 10

        elif buy_ratio >= 0.55:
            score += 5

    return clamp(score, 0, 60)


# ============================================================
# TOKEN QUALITY
# ============================================================

def calculate_token_quality(data):

    score = 0

    name = str(
        data.get("name", "")
    ).strip()

    symbol = str(
        data.get("symbol", "")
    ).strip()

    if len(name) >= 3:
        score += 5

    if len(symbol) >= 2:
        score += 5

    if data.get("uri"):
        score += 5

    if data.get("twitter"):
        score += 5

    if data.get("telegram"):
        score += 5

    if data.get("website"):
        score += 5

    suspicious_words = [
        "test",
        "scam",
        "rug",
        "fake",
        "airdrop",
        "free"
    ]

    text = (
        f"{name} {symbol}"
    ).lower()

    for word in suspicious_words:

        if word in text:
            score -= 20

    return clamp(score, 0, 30)


# ============================================================
# SCORE COMPLESSIVO
# ============================================================

def score_token(data, market):

    quality = calculate_token_quality(
        data
    )

    fomo = calculate_fomo(
        market
    )

    risk = calculate_risk(
        market
    )

    # Score principale
    score = quality + fomo

    # Penalità rischio
    if risk >= 70:
        score -= 40

    elif risk >= 50:
        score -= 25

    elif risk >= 30:
        score -= 10

    # Bonus liquidità
    if market:

        liquidity = market["liquidity"]

        if liquidity >= 50_000:
            score += 10

        elif liquidity >= 25_000:
            score += 7

        elif liquidity >= 10_000:
            score += 4

    return {
        "score": clamp(score),
        "quality": quality,
        "fomo": fomo,
        "risk": risk
    }


# ============================================================
# PAPER BUY
# ============================================================

def paper_buy(data, market, analysis):

    global balance
    global buy_count

    mint = data.get("mint")

    if not mint:
        return False

    if mint in positions:
        return False

    if balance < POSITION_SIZE:
        return False

    if len(positions) >= MAX_POSITIONS:
        return False

    score = analysis["score"]

    if score < MIN_SCORE:
        return False

    price = market["price"]

    if price <= 0:
        return False

    name = data.get(
        "name",
        "Unknown"
    )

    symbol = data.get(
        "symbol",
        "???"
    )

    balance -= POSITION_SIZE

    positions[mint] = {

        "name": name,

        "symbol": symbol,

        "mint": mint,

        "entry_time": now(),

        "amount": POSITION_SIZE,

        "score": score,

        "entry_price": price,

        "last_price": price,

        "best_price": price,

        "liquidity": market["liquidity"],

        "volume_5m": market["volume_5m"],

        "fomo": analysis["fomo"],

        "risk": analysis["risk"],

    }

    buy_count += 1

    print()

    print("==========================================")

    print("🟢 PAPER BUY")

    print(
        f"Token: {name} (${symbol})"
    )

    print(
        f"Score: {score}/100"
    )

    print(
        f"FOMO: {analysis['fomo']}/60"
    )

    print(
        f"Risk: {analysis['risk']}/100"
    )

    print(
        f"Liquidity: ${market['liquidity']:,.2f}"
    )

    print(
        f"Volume 5m: ${market['volume_5m']:,.2f}"
    )

    print(
        f"Entry: ${price:.10f}"
    )

    print(
        f"Amount: ${POSITION_SIZE:.2f}"
    )

    print(
        f"Balance: ${balance:.2f}"
    )

    print("==========================================")

    print()

    return True


# ============================================================
# PAPER SELL
# ============================================================

def close_position(
    mint,
    exit_price,
    reason
):

    global balance
    global sell_count

    position = positions.get(
        mint
    )

    if not position:
        return

    entry_price = safe_float(
        position.get("entry_price")
    )

    exit_price = safe_float(
        exit_price
    )

    if entry_price <= 0:
        return

    if exit_price <= 0:
        return

    change = (
        exit_price - entry_price
    ) / entry_price

    pnl_dollars = (
        POSITION_SIZE * change
    )

    balance += (
        POSITION_SIZE +
        pnl_dollars
    )

    trade = {

        "name": position["name"],

        "symbol": position["symbol"],

        "mint": mint,

        "entry_time": position["entry_time"],

        "exit_time": now(),

        "entry_price": entry_price,

        "exit_price": exit_price,

        "pnl_percent": change * 100,

        "pnl_dollars": pnl_dollars,

        "reason": reason,

    }

    closed_trades.append(
        trade
    )

    del positions[mint]

    sell_count += 1

    print()

    print("==========================================")

    print("🔴 PAPER SELL")

    print(
        f"Token: {position['name']} "
        f"(${position['symbol']})"
    )

    print(
        f"Reason: {reason}"
    )

    print(
        f"Entry: ${entry_price:.10f}"
    )

    print(
        f"Exit: ${exit_price:.10f}"
    )

    print(
        f"P/L: ${pnl_dollars:.2f} "
        f"({change * 100:.2f}%)"
    )

    print(
        f"Balance: ${balance:.2f}"
    )

    print("==========================================")

    print()


# ============================================================
# CONTROLLO POSIZIONI
# ============================================================

async def monitor_positions():

    while True:

        try:

            if not positions:

                await asyncio.sleep(5)

                continue

            current_positions = list(
                positions.keys()
            )

            for mint in current_positions:

                market_pair = await fetch_dex_data(
                    mint
                )

                if not market_pair:
                    continue

                market = extract_market_data(
                    market_pair
                )

                if not market:
                    continue

                price = market["price"]

                if price <= 0:
                    continue

                position = positions.get(
                    mint
                )

                if not position:
                    continue

                position["last_price"] = price

                if price > position["best_price"]:
                    position["best_price"] = price

                entry = position["entry_price"]

                change = (
                    price - entry
                ) / entry

                print(
                    f"📈 {position['symbol']} "
                    f"{change * 100:.2f}%"
                )

                if change >= TAKE_PROFIT:

                    close_position(
                        mint,
                        price,
                        "TAKE PROFIT"
                    )

                elif change <= STOP_LOSS:

                    close_position(
                        mint,
                        price,
                        "STOP LOSS"
                    )

            await asyncio.sleep(5)

        except Exception as error:

            print(
                f"⚠️ Position monitor error: {error}"
            )

            await asyncio.sleep(5)


# ============================================================
# ANALISI TOKEN
# ============================================================

async def analyze_token(data):

    global analyzed_tokens

    mint = data.get("mint")

    if not mint:
        return

    analyzed_tokens += 1

    name = data.get(
        "name",
        "Unknown"
    )

    symbol = data.get(
        "symbol",
        "???"
    )

    print()

    print(
        f"[{now()}] 🔎 "
        f"Analyzing {name} (${symbol})"
    )

    market_pair = await fetch_dex_data(
        mint
    )

    if not market_pair:

        print(
            "⚠️ No DEX Screener pair found"
        )

        return

    market = extract_market_data(
        market_pair
    )

    if not market:

        print(
            "⚠️ Market data unavailable"
        )

        return

    analysis = score_token(
        data,
        market
    )

    print(
        f"📊 Score: "
        f"{analysis['score']}/100"
    )

    print(
        f"🔥 FOMO: "
        f"{analysis['fomo']}/60"
    )

    print(
        f"🛡️ Risk: "
        f"{analysis['risk']}/100"
    )

    print(
        f"💧 Liquidity: "
        f"${market['liquidity']:,.2f}"
    )

    print(
        f"📊 Volume 5m: "
        f"${market['volume_5m']:,.2f}"
    )

    print(
        f"📈 Price 5m: "
        f"{market['price_change_5m']:.2f}%"
    )

    print(
        f"💰 Market Cap: "
        f"${market['market_cap']:,.2f}"
    )

    # Solo paper trading
    paper_buy(
        data,
        market,
        analysis
    )


# ============================================================
# PUMPPORTAL SCANNER
# ============================================================

async def scanner():

    print()

    print(
        "🚀 PAPER MEME COIN BOT STARTED"
    )

    print(
        f"💰 Starting balance: "
        f"${balance:.2f}"
    )

    print(
        f"🎯 Minimum score: "
        f"{MIN_SCORE}/100"
    )

    print(
        f"💵 Position size: "
        f"${POSITION_SIZE:.2f}"
    )

    print()

    while True:

        try:

            async with websockets.connect(

                PUMPPORTAL_WS,

                ping_interval=20,

                ping_timeout=20,

                close_timeout=10

            ) as ws:

                print(
                    "✅ Connected to PumpPortal"
                )

                await ws.send(
                    json.dumps({
                        "method":
                        "subscribeNewToken"
                    })
                )

                print(
                    "👀 Listening for new tokens..."
                )

                print()

                async for message in ws:

                    try:

                        data = json.loads(
                            message
                        )

                        if not isinstance(
                            data,
                            dict
                        ):
                            continue

                        mint = data.get(
                            "mint"
                        )

                        if not mint:
                            continue

                        asyncio.create_task(
                            analyze_token(data)
                        )

                    except Exception as error:

                        print(
                            f"⚠️ Message error: "
                            f"{error}"
                        )

        except Exception as error:

            print()

            print(
                f"⚠️ Connection error: "
                f"{error}"
            )

            print(
                "🔄 Reconnecting in 5 seconds..."
            )

            await asyncio.sleep(5)


# ============================================================
# STATUS
# ============================================================

async def status_loop():

    while True:

        try:

            print()

            print(
                "================ BOT STATUS ================"
            )

            print(
                f"💰 Balance: "
                f"${balance:.2f}"
            )

            print(
                f"📊 Tokens analyzed: "
                f"{analyzed_tokens}"
            )

            print(
                f"🟢 Paper buys: "
                f"{buy_count}"
            )

            print(
                f"🔴 Paper sells: "
                f"{sell_count}"
            )

            print(
                f"📦 Open positions: "
                f"{len(positions)}/{MAX_POSITIONS}"
            )

            print(
                f"📚 Closed trades: "
                f"{len(closed_trades)}"
            )

            print(
                "============================================"
            )

            await asyncio.sleep(30)

        except Exception as error:

            print(
                f"⚠️ Status error: {error}"
            )

            await asyncio.sleep(30)


# ============================================================
# MAIN
# ============================================================

async def main():

    await asyncio.gather(

        scanner(),

        monitor_positions(),

        status_loop()

    )


if __name__ == "__main__":

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print()

        print(
            "🛑 Bot stopped"
        )

        print(
            f"💰 Final paper balance: "
            f"${balance:.2f}"
        )
