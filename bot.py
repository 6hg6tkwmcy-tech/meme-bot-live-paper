import asyncio
import json
import urllib.request
from datetime import datetime

import websockets


# ============================================================
# CONFIG
# ============================================================

STARTING_BALANCE = 100.00
POSITION_SIZE = 10.00

TAKE_PROFIT = 0.30
STOP_LOSS = -0.20

MAX_POSITIONS = 5
MIN_SCORE = 60

PUMPPORTAL_WS = "wss://pumpportal.fun/api/data"
DEXSCREENER_URL = "https://api.dexscreener.com/token-pairs/v1/solana/"


# ============================================================
# PAPER TRADING STATE
# ============================================================

balance = STARTING_BALANCE
positions = {}
closed_trades = []

analyzed_tokens = 0
buy_count = 0
sell_count = 0


# ============================================================
# UTILS
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

def fetch_dex_sync(mint):
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

            data = json.loads(
                response.read().decode("utf-8")
            )

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
            f"DEX ERROR: {error}",
            flush=True
        )

        return None


async def fetch_dex(mint):
    return await asyncio.to_thread(
        fetch_dex_sync,
        mint
    )


def market_data(pair):

    if not pair:
        return None

    txns = pair.get(
        "txns",
        {}
    ).get(
        "m5",
        {}
    )

    volume = pair.get(
        "volume",
        {}
    )

    change = pair.get(
        "priceChange",
        {}
    )

    liquidity = pair.get(
        "liquidity",
        {}
    )

    return {
        "price": safe_float(
            pair.get("priceUsd")
        ),

        "liquidity": safe_float(
            liquidity.get("usd")
        ),

        "volume_5m": safe_float(
            volume.get("m5")
        ),

        "volume_1h": safe_float(
            volume.get("h1")
        ),

        "change_5m": safe_float(
            change.get("m5")
        ),

        "change_1h": safe_float(
            change.get("h1")
        ),

        "buys": int(
            safe_float(
                txns.get("buys")
            )
        ),

        "sells": int(
            safe_float(
                txns.get("sells")
            )
        ),

        "market_cap": safe_float(
            pair.get("marketCap")
        ),
    }


# ============================================================
# SCORE
# ============================================================

def calculate_score(token, market):

    if not market:
        return 0

    score = 0

    name = str(
        token.get("name", "")
    ).strip()

    symbol = str(
        token.get("symbol", "")
    ).strip()

    if len(name) >= 3:
        score += 10

    if len(symbol) >= 2:
        score += 10

    if token.get("uri"):
        score += 10

    if token.get("twitter"):
        score += 5

    if token.get("telegram"):
        score += 5

    if token.get("website"):
        score += 5

    liquidity = market["liquidity"]

    if liquidity >= 50000:
        score += 15

    elif liquidity >= 25000:
        score += 10

    elif liquidity >= 10000:
        score += 5

    volume = market["volume_5m"]

    if volume >= 50000:
        score += 15

    elif volume >= 20000:
        score += 10

    elif volume >= 5000:
        score += 5

    change = market["change_5m"]

    if 2 <= change <= 15:
        score += 10

    elif 15 < change <= 30:
        score += 5

    buys = market["buys"]
    sells = market["sells"]

    total = buys + sells

    if total >= 10:

        buy_ratio = buys / total

        if buy_ratio >= 0.70:
            score += 10

        elif buy_ratio >= 0.60:
            score += 5

    suspicious = [
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
        for word in suspicious
    ):
        score -= 40

    return clamp(score)


# ============================================================
# PAPER BUY
# ============================================================

def paper_buy(token, market, score):

    global balance
    global buy_count

    mint = token.get("mint")

    if not mint:
        return

    if mint in positions:
        return

    if balance < POSITION_SIZE:
        return

    if len(positions) >= MAX_POSITIONS:
        return

    if score < MIN_SCORE:
        return

    price = market["price"]

    if price <= 0:
        return

    name = token.get(
        "name",
        "Unknown"
    )

    symbol = token.get(
        "symbol",
        "???"
    )

    balance -= POSITION_SIZE

    positions[mint] = {
        "name": name,
        "symbol": symbol,
        "entry_price": price,
        "entry_time": now(),
        "amount": POSITION_SIZE,
        "score": score
    }

    buy_count += 1

    print()
    print("====================================")
    print("🟢 PAPER BUY")
    print(
        f"Token: {name} (${symbol})"
    )
    print(
        f"Score: {score}/100"
    )
    print(
        f"Price: ${price:.10f}"
    )
    print(
        f"Amount: ${POSITION_SIZE:.2f}"
    )
    print(
        f"Balance: ${balance:.2f}"
    )
    print("====================================")
    print()


# ============================================================
# PAPER SELL
# ============================================================

def close_position(
    mint,
    price,
    reason
):

    global balance
    global sell_count

    position = positions.get(mint)

    if not position:
        return

    entry = position["entry_price"]

    if entry <= 0 or price <= 0:
        return

    change = (
        price - entry
    ) / entry

    pnl = POSITION_SIZE * change

    balance += (
        POSITION_SIZE + pnl
    )

    closed_trades.append({
        "mint": mint,
        "name": position["name"],
        "symbol": position["symbol"],
        "pnl": pnl,
        "pnl_percent": change * 100,
        "reason": reason
    })

    del positions[mint]

    sell_count += 1

    print()
    print("====================================")
    print("🔴 PAPER SELL")
    print(
        f"Token: {position['name']} "
        f"(${position['symbol']})"
    )
    print(
        f"Reason: {reason}"
    )
    print(
        f"P/L: ${pnl:.2f} "
        f"({change * 100:.2f}%)"
    )
    print(
        f"Balance: ${balance:.2f}"
    )
    print("====================================")
    print()


# ============================================================
# ANALYZE TOKEN
# ============================================================

async def analyze_token(token):

    global analyzed_tokens

    mint = token.get("mint")

    if not mint:
        return

    analyzed_tokens += 1

    name = token.get(
        "name",
        "Unknown"
    )

    symbol = token.get(
        "symbol",
        "???"
    )

    print(
        f"[{now()}] 🆕 "
        f"{name} (${symbol})",
        flush=True
    )

    pair = await fetch_dex(
        mint
    )

    if not pair:

        print(
            "   ⚠️ No DEX data",
            flush=True
        )

        return

    market = market_data(
        pair
    )

    if not market:
        return

    score = calculate_score(
        token,
        market
    )

    print(
        f"   Score: {score}/100",
        flush=True
    )

    print(
        f"   Liquidity: "
        f"${market['liquidity']:,.2f}",
        flush=True
    )

    print(
        f"   Volume 5m: "
        f"${market['volume_5m']:,.2f}",
        flush=True
    )

    print(
        f"   Price change 5m: "
        f"{market['change_5m']:.2f}%",
        flush=True
    )

    print(
        f"   Buys/Sells: "
        f"{market['buys']}/"
        f"{market['sells']}",
        flush=True
    )

    paper_buy(
        token,
        market,
        score
    )


# ============================================================
# PUMPPORTAL
# ============================================================

async def scanner():

    print(
        "🚀 PAPER MEME COIN BOT STARTED",
        flush=True
    )

    print(
        f"💰 Balance: ${balance:.2f}",
        flush=True
    )

    print(
        f"🎯 Minimum score: {MIN_SCORE}/100",
        flush=True
    )

    while True:

        try:

            async with websockets.connect(
                PUMPPORTAL_WS,
                ping_interval=20,
                ping_timeout=20
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

                        if not data.get(
                            "mint"
                        ):
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

            await asyncio.sleep(5)


# ============================================================
# MONITOR
# ============================================================

async def monitor_positions():

    while True:

        try:

            for mint in list(
                positions.keys()
            ):

                pair = await fetch_dex(
                    mint
                )

                market = market_data(
                    pair
                )

                if not market:
                    continue

                price = market["price"]

                position = positions.get(
                    mint
                )

                if not position:
                    continue

                entry = position["entry_price"]

                if entry <= 0:
                    continue

                change = (
                    price - entry
                ) / entry

                print(
                    f"📈 "
                    f"{position['symbol']} "
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
                f"⚠️ Monitor error: "
                f"{error}",
                flush=True
            )

            await asyncio.sleep(5)


# ============================================================
# STATUS
# ============================================================

async def status_loop():

    while True:

        print()
        print(
            "========== BOT STATUS ==========",
            flush=True
        )

        print(
            f"Balance: ${balance:.2f}",
            flush=True
        )

        print(
            f"Tokens analyzed: "
            f"{analyzed_tokens}",
            flush=True
        )

        print(
            f"Paper buys: {buy_count}",
            flush=True
        )

        print(
            f"Paper sells: {sell_count}",
            flush=True
        )

        print(
            f"Open positions: "
            f"{len(positions)}/{MAX_POSITIONS}",
            flush=True
        )

        print(
            f"Closed trades: "
            f"{len(closed_trades)}",
            flush=True
        )

        print(
            "================================",
            flush=True
        )

        await asyncio.sleep(30)


# ============================================================
# MAIN
# ============================================================

async def main():

    print(
        "BOT MAIN AVVIATO",
        flush=True
    )

    await asyncio.gather(
        scanner(),
        monitor_positions(),
        status_loop()
    )


if __name__ == "__main__":

    print(
        "BOT.PY CARICATO",
        flush=True
    )

    try:

        asyncio.run(main())

    except Exception as error:

        print(
            f"FATAL ERROR: {error}",
            flush=True
        )
