# MEMECOIN-BOT — PAPER ONLY

This build cannot execute real trades: it has no wallet, private key, signing code, or exchange execution API.

Data source: DEX Screener public API.
Runtime: Python 3.12 / Railway Docker deploy.

## Files to upload
- bot.py
- requirements.txt
- Dockerfile
- .env.example
- README.md

## Railway
Deploy from the GitHub repository. No public domain is required because this is a background worker.

## Important
The numeric values in `.env.example` are a technical starter profile, not a claim that they are the exact historical strategy values from the earlier chat. Before treating the strategy as the final one, the previously agreed numeric parameters must be restored if they are not already present in the current project context.
