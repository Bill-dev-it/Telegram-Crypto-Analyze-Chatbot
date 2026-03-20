# CryptoSafe AI — Telegram Bot

A Telegram bot for cryptocurrency risk analysis, powered by Groq LLM, Google Gemini Vision, GoPlus, DexScreener, Etherscan, Binance, and CoinGecko.

---

## Features

| Command | Description |
|---|---|
| `/start` | Welcome screen + optional 3-step onboarding tutorial for new users |
| `/price <coin>` | Real-time price from Binance (fallback: CoinGecko) |
| `/scan <address>` | Full contract risk scan — honeypot, tax, liquidity, whale concentration |
| `/dex <address>` | Market data from DexScreener (price, liquidity, volume, pair age) |
| `/deployer <address>` | Deployer/creator history and credibility score |
| `/holders <address>` | Top holder concentration and whale risk |
| `/goplus <address>` | GoPlus honeypot and tax detection |
| `/source <address>` | Verified contract source code from Etherscan |
| `/report <address>` | Full aggregated risk report (all sources in parallel) |
| `/alert <coin> <above\|below> <price>` | Set a price alert (e.g. `/alert BTC above 70000`) |
| `/alert list` | List your active alerts |
| `/delalert <id>` | Delete a price alert |
| `/trending` | Top boosted and latest listed tokens from DexScreener |
| `/chart` | Instructions for chart analysis |
| Send any chart image | AI candlestick chart analysis via Gemini Vision |
| Free chat | General crypto Q&A powered by Groq LLaMA-3.3-70b |

---

## Multi-Chain Support

Automatically detects the chain from the contract address:

| Chain | ID |
|---|---|
| Ethereum | `eth` |
| BNB Chain | `bsc` |
| Arbitrum | `arbitrum` |
| Base | `base` |
| Polygon | `polygon` |
| Solana | `solana` |

---

## Project Structure

```
main.py                         # Entry point, all command handlers and routing
features/
  chain_support.py              # Multi-chain detection and URL builders
  price_alerts.py               # Price alert manager and polling loop
  deepscan/                     # DeepScan agent and LLM client
  data/
    binance_price_fetcher.py
    dexscreener_data_fetcher.py
    deployer_analyzer.py
    token_holders_analyzer.py
    goplus_security_fetcher.py
    etherscan_source_fetcher.py
    report_generator.py
    groq_ai_analyzer.py
data/
  price_alerts.json             # Persisted price alerts (auto-created)
```

---

## Setup

### 1. Create and activate a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate        # Linux/Mac
.venv\Scripts\activate           # Windows
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Configure `.env`
Create a `.env` file in the project root:

```env
# Required
BOT_TOKEN=your_telegram_bot_token
BOT_USERNAME=@YourBotUsername
GROQ_API_KEY=your_groq_api_key

# Required for chart analysis (free tier available)
GEMINI_API_KEY=your_gemini_api_key

# Required for full report & source scan
ETHERSCAN_API_KEY=your_etherscan_api_key

# Required for holder analysis
MORALIS_API_KEY=your_moralis_api_key

# Optional
ANTHROPIC_API_KEY=your_anthropic_api_key
BSCSCAN_API_KEY=your_bscscan_api_key
```

### 4. Run the bot
```bash
python main.py
```

---

## API Keys — Where to Get Them

| Key | Free? | Link |
|---|---|---|
| `BOT_TOKEN` | ✅ Free | [@BotFather](https://t.me/BotFather) on Telegram |
| `GROQ_API_KEY` | ✅ Free tier | [console.groq.com](https://console.groq.com) |
| `GEMINI_API_KEY` | ✅ Free tier | [aistudio.google.com](https://aistudio.google.com) |
| `ETHERSCAN_API_KEY` | ✅ Free | [etherscan.io/myapikey](https://etherscan.io/myapikey) |
| `MORALIS_API_KEY` | ✅ Free tier | [admin.moralis.io](https://admin.moralis.io) |

---

## Requirements

Add these to `requirements.txt` if not already present:

```
python-telegram-bot>=20.0
groq
httpx>=0.27.0
requests
python-dotenv
langdetect>=1.0.9
```

---

## Notes

- **Chart analysis** uses Google Gemini Vision (free). Send chart images directly as a screenshot or as a File to avoid Telegram compression.
- **Price alerts** are stored in `data/price_alerts.json` and checked every 60 seconds.
- **Onboarding** is in-memory — resets on bot restart. To persist, save `onboarded_users` to a JSON file.
- **Solana** scanning is supported for GoPlus and DexScreener but not Etherscan source fetching.
