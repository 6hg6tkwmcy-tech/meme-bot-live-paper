import asyncio

import json

import websockets

from datetime import datetime

# ==========================================

# PAPER TRADING

# ==========================================

STARTING_BALANCE = 100.00

POSITION_SIZE = 10.00

TAKE_PROFIT = 0.30

STOP_LOSS = -0.20

MAX_POSITIONS = 5

MIN_SCORE = 50

balance = STARTING_BALANCE

positions = []

closed_trades = []

WS_URL = "wss://pumpportal.fun/api/data"

# ==========================================

# TOKEN SCORING

# ==========================================

def score_token(data):

    score = 0

    name = str(data.get("name", "")).strip()

    symbol = str(data.get("symbol", "")).strip()

    if len(name) >= 3:

        score += 10

    if len(symbol) >= 2:

        score += 10

    if data.get("uri"):

        score += 20

    if data.get("twitter"):

        score += 15

    if data.get("telegram"):

        score += 10

    if data.get("website"):

        score += 10

    suspicious_words = [

        "test",

        "scam",

        "rug",

        "fake"

    ]

    text = f"{name} {symbol}".lower()

    if any(word in text for word in suspicious_words):

        score -= 40

    return max(0, min(score, 100))

# ==========================================

# PAPER BUY

# ==========================================

def paper_buy(data):

    global balance

    mint = data.get("mint")

    if not mint:

        return

    if mint in positions:

        return

    if balance < POSITION_SIZE:

        return

    if len(positions) >= MAX_POSITIONS:

        return

    score = score_token(data)

    if score < MIN_SCORE:

        return

    name = data.get("name", "Unknown")

    symbol = data.get("symbol", "???")

    balance -= POSITION_SIZE

    positions[mint] = {

        "name": name,

        "symbol": symbol,

        "mint": mint,

        "entry_time": datetime.now().strftime("%H:%M:%S"),

        "amount": POSITION_SIZE,

        "score": score,

        "entry_price": None,

        "last_price": None

    }

    print()

    print("====================================")

    print("🟢 PAPER BUY")

    print(f"Token: {name} (${symbol})")

    print(f"Score: {score}/100")

    print(f"Amount: ${POSITION_SIZE:.2f}")

    print(f"Balance: ${balance:.2f}")

    print("====================================")

    print()

# ==========================================

# PAPER SELL

# ==========================================

def close_position(mint, exit_price, reason):

    global balance

    position = positions.get(mint)

    if not position:

        return

    entry_price = position.get("entry_price")

    if entry_price is None:

        return

    if exit_price is None:

        return

    try:

        entry_price = float(entry_price)

        exit_price = float(exit_price)

    except (TypeError, ValueError):

        return

    if entry_price <= 0:

        return

    pnl_percent = (

        (exit_price - entry_price)

        / entry_price

    )

    pnl_dollars = POSITION_SIZE * pnl_percent

    balance += POSITION_SIZE + pnl_dollars

    trade = {

        "name": position["name"],

        "symbol": position["symbol"],

        "mint": mint,

        "entry_time": position["entry_time"],

        "exit_time": datetime.now().strftime("%H:%M:%S"),

        "pnl_percent": pnl_percent * 100,

        "pnl_dollars": pnl_dollars,

        "reason": reason

    }

    closed_trades.append(trade)

    del positions[mint]

    print()

    print("====================================")

    print("🔴 PAPER SELL")

    print(f"Token: {position['name']} (${position['symbol']})")

    print(f"Reason: {reason}")

    print(

        f"P/L: ${pnl_dollars:.2f} "

        f"({pnl_percent * 100:.2f}%)"

    )

    print(f"Balance: ${balance:.2f}")

    print("====================================")

    print()

# ==========================================

# PRICE UPDATE

# ==========================================

def update_position(mint, price):

    position = positions.get(mint)

    if not position:

        return

    try:

        price = float(price)

    except (TypeError, ValueError):

        return

    if price <= 0:

        return

    if position["entry_price"] is None:

        position["entry_price"] = price

        position["last_price"] = price

        print(

            f"📊 Entry price: "

            f"{position['name']} = {price}"

        )

        return

    position["last_price"] = price

    change = (

        (price - position["entry_price"])

        / position["entry_price"]

    )

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

# ==========================================

# SCANNER

# ==========================================

async def scanner():

    global balance

    print()

    print("🚀 PAPER MEME COIN BOT STARTED")

    print(f"💰 Starting balance: ${balance:.2f}")

    print(f"🎯 Minimum score: {MIN_SCORE}/100")

    print()

    while True:

        try:

            async with websockets.connect(

                WS_URL,

                ping_interval=20,

                ping_timeout=20

            ) as ws:

                print("✅ Connected to PumpPortal")

                print("👀 Listening for new tokens...")

                print()

                await ws.send(

                    json.dumps({

                        "method": "subscribeNewToken"

                    })

                )

                async for message in ws:

                    try:

                        data = json.loads(message)

                        mint = data.get("mint")

                        if not mint:

                            continue

                        name = data.get(

                            "name",

                            "Unknown"

                        )

                        symbol = data.get(

                            "symbol",

                            "???"

                        )

                        score = score_token(data)

                        timestamp = datetime.now().strftime(

                            "%H:%M:%S"

                        )

                        print(

                            f"[{timestamp}] 🆕 "

                            f"{name} (${symbol}) "

                            f"| Score: {score}/100"

                        )

                        paper_buy(data)

                    except Exception as error:

                        print(

                            f"⚠️ Message error: {error}"

                        )

        except Exception as error:

            print()

            print(

                f"⚠️ Connection error: {error}"

            )

            print("🔄 Reconnecting in 5 seconds...")

            await asyncio.sleep(5)

# ==========================================

# MAIN

# ==========================================

if __name__ == "__main__":

    try:

        asyncio.run(scanner())

    except KeyboardInterrupt:

        print()

        print("🛑 Bot stopped")

        print(

            f"💰 Final paper balance: "

            f"${balance:.2f}"

        )
