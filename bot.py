import os, json, time, uuid, logging
from datetime import datetime, timezone
import requests

# ============================================================
# MEMECOIN-BOT — PAPER TRADING ONLY
# No wallet, no private key, no transaction signing.
# ============================================================

API_PROFILES = "https://api.dexscreener.com/token-profiles/latest/v1"
API_TOKENS = "https://api.dexscreener.com/tokens/v1/{chain}/{addresses}"

def env(name, default, cast=str):
    v = os.getenv(name)
    return default if v is None or v == "" else cast(v)

MODE = env("MODE", "paper")
if MODE != "paper":
    raise RuntimeError("This build is PAPER ONLY. MODE must be 'paper'.")

START_BALANCE = env("PAPER_START_BALANCE", 1000.0, float)
SCAN_SECONDS = env("SCAN_INTERVAL_SECONDS", 30, int)
MIN_SCORE = env("MIN_SCORE", 70, int)
POSITION_PCT = env("POSITION_PCT", 0.05, float)
MAX_POSITIONS = env("MAX_OPEN_POSITIONS", 3, int)
TP = env("TAKE_PROFIT_PCT", 0.30, float)
SL = env("STOP_LOSS_PCT", 0.12, float)
MIN_LIQ = env("MIN_LIQUIDITY_USD", 5000.0, float)
MIN_VOL = env("MIN_VOLUME_5M_USD", 1000.0, float)
MIN_BUYS = env("MIN_BUYS_5M", 5, int)
MIN_SELLS = env("MIN_SELLS_5M", 1, int)
MAX_AGE = env("MAX_AGE_MINUTES", 60, int)
MAX_CANDIDATES = env("MAX_CANDIDATES_PER_SCAN", 120, int)
STATE_FILE = env("STATE_FILE", "paper_state.json")
LOG_FILE = env("LOG_FILE", "trades.jsonl")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger("memecoin-bot")
http = requests.Session()
http.headers.update({"User-Agent": "MEMECOIN-BOT-PAPER/1.0"})

def utc():
    return datetime.now(timezone.utc).isoformat()

def write_event(kind, payload):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"ts": utc(), "type": kind, **payload}, ensure_ascii=False) + "\n")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"balance": START_BALANCE, "positions": [], "realized_pnl": 0.0,
            "trades": 0, "wins": 0, "losses": 0}

def save_state(s):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    os.replace(tmp, STATE_FILE)

def get_profiles():
    r = http.get(API_PROFILES, timeout=15)
    r.raise_for_status()
    data = r.json()
    out, seen = [], set()
    for x in data:
        if x.get("chainId") != "solana":
            continue
        a = x.get("tokenAddress")
        if a and a not in seen:
            seen.add(a); out.append(a)
        if len(out) >= MAX_CANDIDATES:
            break
    return out

def chunks(xs, n=30):
    for i in range(0, len(xs), n):
        yield xs[i:i+n]

def get_pairs(addresses):
    pairs = []
    for batch in chunks(addresses, 30):
        url = API_TOKENS.format(chain="solana", addresses=",".join(batch))
        r = http.get(url, timeout=15)
        r.raise_for_status()
        pairs.extend(r.json().get("pairs") or [])
    return pairs

def normalize(p):
    tx = p.get("txns") or {}
    m5 = tx.get("m5") or {}
    liq = p.get("liquidity") or {}
    vol = p.get("volume") or {}
    created = p.get("pairCreatedAt")
    age = None
    if created:
        age = max(0.0, (time.time()*1000 - created)/60000)
    return {
        "address": (p.get("baseToken") or {}).get("address"),
        "symbol": (p.get("baseToken") or {}).get("symbol"),
        "name": (p.get("baseToken") or {}).get("name"),
        "price": float(p.get("priceUsd") or 0),
        "liquidity": float(liq.get("usd") or 0),
        "volume5m": float(vol.get("m5") or 0),
        "buys5m": int(m5.get("buys") or 0),
        "sells5m": int(m5.get("sells") or 0),
        "age": age,
        "pair": p.get("pairAddress"),
        "url": p.get("url"),
    }

def score(t):
    # Centralized, deterministic paper profile.
    # Values are environment-configurable; no live execution is possible.
    s, reasons = 0, []
    if t["liquidity"] >= MIN_LIQ: s += 25; reasons.append("liquidity")
    if t["volume5m"] >= MIN_VOL: s += 25; reasons.append("volume_5m")
    if t["buys5m"] >= MIN_BUYS: s += 20; reasons.append("buy_pressure")
    if t["sells5m"] >= MIN_SELLS: s += 5; reasons.append("two_sided")
    if t["age"] is not None and t["age"] <= MAX_AGE: s += 15; reasons.append("fresh")
    if t["price"] > 0: s += 10; reasons.append("price")
    return s, reasons

def buy(state, t, sc, reasons):
    if len(state["positions"]) >= MAX_POSITIONS or state["balance"] <= 0:
        return
    amount = min(state["balance"], state["balance"] * POSITION_PCT)
    pos = {
        "id": str(uuid.uuid4()), "address": t["address"], "symbol": t["symbol"],
        "entry": t["price"], "amount": amount, "score": sc,
        "opened": utc(), "reason": reasons
    }
    state["balance"] -= amount
    state["positions"].append(pos)
    write_event("BUY_PAPER", {"position": pos})
    log.info("PAPER BUY %s | score=%s | $%.2f", t["symbol"], sc, amount)

def close(state, pos, price, reason):
    proceeds = pos["amount"] * (price / pos["entry"])
    pnl = proceeds - pos["amount"]
    state["balance"] += proceeds
    state["realized_pnl"] += pnl
    state["trades"] += 1
    if pnl >= 0: state["wins"] += 1
    else: state["losses"] += 1
    state["positions"] = [x for x in state["positions"] if x["id"] != pos["id"]]
    write_event("SELL_PAPER", {"position": pos, "exit": price, "proceeds": proceeds,
                               "pnl": pnl, "reason": reason})
    log.info("PAPER %s %s | pnl=%+.2f", reason, pos["symbol"], pnl)

def refresh_positions(state):
    if not state["positions"]:
        return
    addresses = [p["address"] for p in state["positions"]]
    try:
        pairs = get_pairs(addresses)
    except Exception as e:
        write_event("ERROR", {"where":"position_refresh", "error":str(e)})
        return
    latest = {}
    for p in pairs:
        t = normalize(p)
        if t["address"] and t["price"] > 0:
            latest[t["address"]] = t["price"]
    for pos in list(state["positions"]):
        price = latest.get(pos["address"])
        if not price:
            continue
        change = price / pos["entry"] - 1
        if change >= TP:
            close(state, pos, price, "TAKE_PROFIT")
        elif change <= -SL:
            close(state, pos, price, "STOP_LOSS")

def scan_once(state):
    addresses = get_profiles()
    pairs = get_pairs(addresses)
    candidates = []
    for p in pairs:
        if p.get("chainId") != "solana":
            continue
        t = normalize(p)
        if not t["address"] or t["price"] <= 0:
            continue
        sc, reasons = score(t)
        write_event("SCREEN", {"token": t, "score": sc, "reasons": reasons})
        candidates.append((sc, t, reasons))
    candidates.sort(key=lambda x: x[0], reverse=True)
    if candidates:
        sc, t, reasons = candidates[0]
        if sc >= MIN_SCORE:
            buy(state, t, sc, reasons)

def main():
    if not os.path.exists(LOG_FILE):
        open(LOG_FILE, "a").close()
    state = load_state()
    log.info("MEMECOIN-BOT PAPER START | balance=$%.2f", state["balance"])
    write_event("START", {"mode":"paper", "balance":state["balance"]})
    while True:
        try:
            refresh_positions(state)
            scan_once(state)
            save_state(state)
            time.sleep(SCAN_SECONDS)
        except KeyboardInterrupt:
            save_state(state); break
        except Exception as e:
            write_event("ERROR", {"where":"main_loop", "error":str(e)})
            log.exception("Loop error")
            save_state(state)
            time.sleep(max(10, SCAN_SECONDS))

if __name__ == "__main__":
    main()
