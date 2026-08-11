import asyncio
import json
import websockets
from datetime import datetime

STARTING_BALANCE = 100.00
POSITION_SIZE = 10.00

balance = STARTING_BALANCE
positions = {}

WS_URL = "wss://pumpportal.fun/api/data"


async def scanner():
    global balance

    print("🚀 PAPER MEME COIN SCANNER STARTED")
    print(f"💰 Paper balance: €{balance:.2f}")

    async with websockets.connect(WS_URL) as ws:

        await ws.send(json.dumps({
            "method": "subscribeNewToken"
        }))

        print("✅ Connected to PumpPortal")
        print("📡 Listening for new Pump.fun tokens...\n")

        async for message in ws:
            try:
                data = json.loads(message)

                timestamp = datetime.now().strftime("%H:%M:%S")

                name = data.get("name", "Unknown")
                symbol = data.get("symbol", "???")
                mint = data.get("mint", "")

                print(
                    f"[{timestamp}] 🆕 {name} (${symbol})"
                )

                if mint:
                    print(f"   Contract: {mint}")

                # Paper-trading entry
                if balance >= POSITION_SIZE and mint not in positions:

                    balance -= POSITION_SIZE

                    positions[mint] = {
                        "name": name,
                        "symbol": symbol,
                        "entry_time": timestamp,
                        "amount": POSITION_SIZE
                    }

                    print(
                        f"   🟢 PAPER BUY €{POSITION_SIZE:.2f}"
                    )
                    print(
                        f"   💰 Remaining balance: €{balance:.2f}\n"
                    )

            except Exception as error:
                print(f"⚠️ Error: {error}")


if __name__ == "__main__":
    asyncio.run(scanner())
