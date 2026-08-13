import asyncio
import json
import urllib.request
from datetime import datetime

import websockets


# ============================================================
# CONFIGURAZIONE PAPER TRADING
# ============================================================

STARTING_BALANCE = 100.00
POSITION_SIZE = 10.00

TAKE_PROFIT = 0.30
STOP_LOSS = -0.20

MAX_POSITIONS = 5
MIN_SCORE = 60

PUMPPORTAL_WS = "wss://pumpportal.fun/api/data"

DEXSCREENER_URL = (
    "https://api.dexscreener.com/token-pairs/v1/solana/"
)


# ============================================================
# STATO DEL BOT
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
        return float(value)
    except (TypeError, ValueError):
        return default


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(value, maximum))


# ============================================================
# DEX SCREENER
# ============================================================

def fetch_dex_data_sync(mint):

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

        pairs = []

        for pair in data:

            liquidity = safe_float(
                pair.get("liquidity", {}).get("usd")
            )

            if liquidity > 0:
                pairs.append(pair)

        if not pairs:
            return None

        pairs.sort(
            key=lambda pair: safe_float(
                pair.get("liquidity", {}).get("usd")
            ),
            reverse=True
        )

        return pairs[0]

    except Exception as error:

        print(
            f"⚠️ DEX Screener error: {error}",
            flush=True
        )

        return None


async def fetch_dex_data(mint):

    return await asyncio.to_thread(
        fetch_dex_data_sync,
        mint
    )


# ============================================================
# DATI DI MERCATO
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

    transactions = pair.get(
        "txns",
        {}
    ).get(
        "m5",
        {}
    )

    buys = int(
        safe_float(
            transactions.get("buys")
        )
    )

    sells = int(
        safe_float(
            transactions.get("sells")
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

    return {
        "price": price,
        "liquidity": liquidity,
        "volume_5m": volume_5m,
        "volume_1h": volume_1h,
        "price_change_5m": price_change_5m,
        "price_change_1h": price_change_1h,
        "buys_5m": buys,
        "sells_5m": sells,
        "market_cap": market_cap,
        "fdv": fdv,
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
    volume = market["volume_5m"]

    buys = market["buys_5m"]
    sells = market["sells_5m"]

    risk = 0

    if liquidity < 5000:
        risk += 35

    elif liquidity < 15000:
        risk += 20

    elif liquidity < 30000:
        risk += 10

    if volume < 1000:
        risk += 20

    elif volume < 5000:
        risk += 10

    total = buys + sells

    if total >= 10:

        sell_ratio = sells / total

        if sell_ratio > 0.70:
            risk += 25

        elif sell_ratio > 0.60:
            risk += 15

    return clamp(risk)


# ============================================================
# FOMO / MOMENTUM
# ============================================================

def calculate_fomo(market):

    if not market:
        return 0

    score = 0

    price_5m = market["price_change_5m"]
    price_1h = market["price_change_1h"]

    volume = market["volume_5m"]

    buys = market["buys_5m"]
    sells = market["sells_5m"]

    total = buys + sells

    if 2 <= price_5m <= 10:
        score += 20

    elif 10 < price_5m <= 25:
        score += 15

    elif price_5m > 25:
        score += 5

    elif price_5m > 0:
        score += 8

    if 5 <= price_1h <= 40:
        score += 10

    elif price_1h > 40:
        score += 5

    if volume >= 50000:
        score += 15

    elif volume >= 20000:
        score += 12

    elif volume >= 5000:
        score += 7

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
# QUALITÀ TOKEN
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
        "fake"
    ]

    text = (
        f"{name} {symbol}"
    ).lower()

    if any(
        word in text
        for word in suspicious_words
    ):
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

    score = quality + fomo

    if risk >= 70:
        score -= 40

    elif risk >= 50:
        score -= 25

    elif risk >= 30:
        score -= 10

    if market:

        liquidity = market["liquidity"]

        if liquidity >= 50000:
            score += 10

        elif liquidity >= 25000:
            score += 7

        elif liquidity >= 10000:
            score += 4

    return {
        "score": clamp(score),
        "quality": quality,
        "fomo": fomo,
        "risk": risk,
    }


# ============================================================
# PAPER BUY
# ============================================================

def paper_buy(data, market, analysis):

    global balance
    global buy_count

    mint = data.get("mint")

    if not mint:
        return

    if mint in positions:
        return

    if balance < POSITION_SIZE:
        return

    if len(positions) >= MAX_POSITIONS:
        return

    if analysis["score"] < MIN_SCORE:
        return

    price = market["price"]

    if price <= 0:
        return

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
        "score": analysis["score"],
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
        f"Score: {analysis['score']}/100"
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

    position = positions.get(mint)

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

    closed_trades.append({
        "name": position["name"],
        "symbol": position["symbol"],
        "mint": mint,
        "entry_time": position["entry_time"],
        "exit_time": now(),
        "pnl_percent": change * 100,
        "pnl_dollars": pnl_dollars,
        "reason": reason,
    })

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
        f"P/L: ${pnl_dollars:.2f} "
        f"({change * 100:.2f}%)"
    )
    print(
        f"Balance: ${balance:.2f}"
    )
    print("==========================================")
    print()


# ============================================================
# MONITOR POSIZIONI
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

                pair = await fetch_dex_data(
                    mint
                )

                market = extract_market_data(
                    pair
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
                    f"{change * 100:.2f}%",
                    flush=True
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
                f"⚠️ Position monitor error: {error}",
                flush=True
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

    print(
        f"[{now()}] 🔎 "
        f"Analyzing {name} (${symbol})",
        flush=True
    )

    market_pair = await fetch_dex_data(
        mint
    )

    if not market_pair:

        print(
            "⚠️ No DEX Screener pair found",
            flush=True
        )

        return

    market = extract_market_data(
        market_pair
    )

    if not market:

        return

    analysis = score_token(
        data,
        market
    )

    print(
        f"📊 Score: "
        f"{analysis['score']}/100",
        flush=True
    )

    print(
        f"🔥 FOMO: "
        f"{analysis['fomo']}/60",
        flush=True
    )

    print(
        f"🛡️ Risk: "
        f"{analysis['risk']}/100",
        flush=True
    )

    print(
        f"💧 Liquidity: "
        f"${market['liquidity']:,.2f}",
        flush=True
    )

    print(
        f"📊 Volume 5m: "
        f"${market['volume_5m']:,.2f}",
        flush=True
    )

    print(
        f"📈 Price 5m: "
        f"{market['price_change_5m']:.2f}%",
        flush=True
    )

    print(
        f"💰 Market Cap: "
        f"${market['market_cap']:,.2f}",
        flush=True
    )

    paper_buy(
        data,
        market,
        analysis
    )


# ============================================================
# SCANNER PUMPPORTAL
# ============================================================

async def scanner():

    print(
        "",
        flush=True
    )

    print(
        "🚀 PAPER MEME COIN BOT STARTED",
        flush=True
    )

    print(
        f"💰 Starting balance: "
        f"${balance:.2f}",
        flush=True
    )

    print(
        f"🎯 Minimum score: "
        f"{MIN_SCORE}/100",
        flush=True
    )

    print(
        f"💵 Position size: "
        f"${POSITION_SIZE:.2f}",
        flush=True
    )

    print(
        "",
        flush=True
    )

    while True:

        try:

            async with websockets.connect(
                PUMPPORTAL_WS,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=10
            ) as ws:

                print(
                    "✅ Connected to PumpPortal",
                    flush=True
                )

                await ws.send(
                    json.dumps({
                        "method":
                        "subscribeNewToken"
                    })
                )

                print(
                    "👀 Listening for new tokens...",
                    flush=True
                )

                print(
                    "",
                    flush=True
                )

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
                            f"{error}",
                            flush=True
                        )

        except Exception as error:

            print(
                f"⚠️ Connection error: "
                f"{error}",
                flush=True
            )

            print(
                "🔄 Reconnecting in 5 seconds...",
                flush=True
            )

            await asyncio.sleep(5)


# ============================================================
# STATO PERIODICO
# ============================================================

async def status_loop():

    while True:

        print()
        print(
            "================ BOT STATUS ================",
            flush=True
        )

        print(
            f"💰 Balance: ${balance:.2f}",
            flush=True
        )

        print(
            f"📊 Tokens analyzed: "
            f"{analyzed_tokens}",
            flush=True
        )

        print(
            f"🟢 Paper buys: "
            f"{buy_count}",
            flush=True
        )

        print(
            f"🔴 Paper sells: "
            f"{sell_count}",
            flush=True
        )

        print(
            f"📦 Open positions: "
            f"{len(positions)}/{MAX_POSITIONS}",
            flush=True
        )

        print(
            f"📚 Closed trades: "
            f"{len(closed_trades)}",
            flush=True
        )

        print(
            "============================================",
            flush=True
        )

        await asyncio.sleep(30)


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "🚀 BOT MAIN AVVIATO",
        flush=True
    )

    await asyncio.gather(
        scanner(),
        monitor_positions(),
        status_loop()
    )


if __name__ == "__main__":

    print(
        "🚀 BOT.PY CARICATO CORRETTAMENTE",
        flush=True
    )

    try:

        asyncio.run(main())

    except KeyboardInterrupt:

        print(
            "🛑 Bot stopped",
            flush=True
        )

        print(
            f"💰 Final paper balance: "
            f"${balance:.2f}",
            flush=True
        )

    except Exception as error:

        print(
            f"🔥 FATAL BOT ERROR: "
            f"{error}",
            flush=True
        )
