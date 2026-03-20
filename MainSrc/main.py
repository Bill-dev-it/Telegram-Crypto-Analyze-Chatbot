from typing import Final
import os
import asyncio
import base64
import httpx
from dotenv import load_dotenv

from telegram import (
    Update,
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)
import requests
from groq import AsyncGroq
import re


# deep‑scan agent & on‑chain/data utilities
from features.deepscan.agent import agent as deepscan_agent
from features.data.binance_price_fetcher import get_binance_ticker_price
from features.data.dexscreener_data_fetcher import fetch_dexscreener_token_data
from features.data.deployer_analyzer import analyze_deployer
from features.data.token_holders_analyzer import analyze_token_holders
from features.data.goplus_security_fetcher import check_goplus_token_security
from features.data.etherscan_source_fetcher import fetch_etherscan_contract_source
from features.data.report_generator import generate_telegram_report
from features.data.groq_ai_analyzer import analyze_solidity_with_groq

# ── Multi-chain support (Brick 1) ─────────────────────────────────────
from features.chain_support import (
    ChainInfo, CHAINS, detect_address_type, detect_chain, is_valid_address,
    build_chain_scan_buttons, build_chain_report_buttons,
    dexscreener_url, explorer_url, goplus_url,
)

from features.price_alerts import AlertManager, alert_polling_loop, format_alert_message

alert_manager = AlertManager()

load_dotenv()

TOKEN: Final        = os.getenv("BOT_TOKEN")
BOT_USERNAME: Final = os.getenv("BOT_USERNAME", "@CryptoAnalysis_AI_bot")  # for Telegram deep-linking in scan results
GROQ_API_KEY        = os.getenv("GROQ_API_KEY")
ANTHROPIC_API_KEY   = os.getenv("ANTHROPIC_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY not found in .env")

groq_client = AsyncGroq(api_key=GROQ_API_KEY)

# ─── System Prompt ────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are CryptoSafe AI – a Telegram assistant specialized in cryptocurrency risk analysis.
Main goal: help users understand risks, avoid scams, honeypots, rug pulls, and never promise profits.

Response style:
- Concise, clear, polite but serious when discussing risks
- Always include: "Cryptocurrency is highly risky — only invest what you can afford to lose. This is NOT financial advice."
- Use moderate emojis: 🛡️ 💰 ⚠️ 📉
- Always respond in English
- Never encourage FOMO, never say "buy now", "it will moon", or recommend specific buys/sells
- For price questions → rely on real-time data (via fetch_price function)
- For scam/risk questions → analyze based on general knowledge + ask for contract address if deeper check needed

Core knowledge (up to date as of 2026):
- Bitcoin: safest major coin, no rug risk, but highly volatile
- Ethereum: largest smart contract platform, relatively safe, main risks from dApps/contracts
- Solana: fast & cheap, but many meme coins are rugs, history of outages
- Stablecoins (USDT/USDC): relatively stable, but still carry issuer risk
- Common scams: rug pulls, honeypots, phishing, fake giveaways, pig butchering, impersonation of support/devs
- Red flags: guaranteed returns, urgency/pressure, requests for private keys/seeds, unsolicited DMs, large dev token holdings

Never:
- Give specific buy/sell/hold advice
- Predict future prices
- Claim any coin is "100% safe"
"""

# ─── Main menu keyboard ───────────────────────────────────────────────
MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💰 Price"),        KeyboardButton("🔬 Scan / Audit")],
        [KeyboardButton("📋 Full Report"),  KeyboardButton("🛡️ Security Check")],
        [KeyboardButton("📊 Dex Data"),     KeyboardButton("🐋 Holders")],
        [KeyboardButton("Help / Commands")],
        [KeyboardButton("🔔 My Alerts"),  KeyboardButton("📈 Chart Analysis")],
        [KeyboardButton("🔥 Trending"), KeyboardButton("👁️ Watchlist")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Ask anything or choose an action…"
)

chat_histories = {}


# ═══════════════════════════════════════════════════════════════════════
# MIME TYPE DETECTION (for chart images)
# ═══════════════════════════════════════════════════════════════════════

def detect_mime_type(image_bytes: bytes) -> str:
    if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
        return "image/png"
    if image_bytes[:6] in (b'GIF87a', b'GIF89a'):
        return "image/gif"
    if image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP':
        return "image/webp"
    return "image/jpeg"


# ═══════════════════════════════════════════════════════════════════════
# CHART ANALYSIS — VISION ENGINE
# ═══════════════════════════════════════════════════════════════════════

CHART_VISION_SYSTEM_PROMPT = """You are a Technical Analysis expert for the crypto and stock markets.
Task: Analyze the candlestick chart image sent by the user.

Mandatory Rules:
- Answer ENTIRELY in English
- Objective analysis, no profit promises
- ALWAYS end with a risk disclaimer
- If the image is NOT a price chart, state clearly and ask to resend

Analysis Structure:

1. 🕯️ DETECTED CANDLESTICK PATTERNS
   - List recognized patterns (Head & Shoulders, Double Top/Bottom, Bull/Bear Flag,
     Pennant, Wedge, Triangle, Doji, Hammer, Shooting Star, Engulfing, etc.)
   - Pattern location on the chart

2. 📈 TREND ANALYSIS
   - Current trend: Uptrend / Downtrend / Sideways
   - Observed Support and Resistance levels
   - MA/EMA lines if visible

3. 📊 VOLUME ANALYSIS (if the chart has volume bars)
   - Volume confirmation or divergence with price
   - Unusual volume spikes

4. 🚨 RISK WARNINGS
   Evaluate each sign (Yes / No / Suspected):
   - Pump & Dump: sudden spike + high volume then immediate reversal
   - Unusually long wicks: price manipulation, stop-loss hunting
   - Price-volume divergence: price up but volume declining = weak signal
   - Clear reversal patterns

5. 🎯 3 SCENARIOS FORECAST
   - 🟢 BULLISH: conditions + estimated % probability
   - 🔴 BEARISH: conditions + estimated % probability
   - 🟡 SIDEWAYS: estimated % probability
   (All 3 must total 100%)

6. ⚡ CONCLUSION
   One concise summary sentence.

⚠️ This is not financial advice. Always DYOR and manage your risk carefully."""


async def analyze_chart_image(image_bytes: bytes) -> str:
    if not GEMINI_API_KEY:
        return "❌ GEMINI_API_KEY not configured.\nAdd to .env:\n`GEMINI_API_KEY=your_key`"

    mime_type = detect_mime_type(image_bytes)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": image_b64,
                        }
                    },
                    {
                        "text": (
                            "You are a professional crypto technical analyst.\n"
                            "Analyze this candlestick chart. Use plain structure with emojis.\n"
                            "Do NOT use ** or __ markdown. Use plain text only.\n"
                            "Use emoji headers exactly as shown below:\n\n"
                            "1. 🕯️ DETECTED CANDLESTICK PATTERNS\n"
                            "   - List all patterns (H&S, Double Top/Bottom, Doji, Hammer, Engulfing, Flag, Wedge etc)\n"
                            "   - Where on the chart each pattern appears\n\n"
                            "2. 📈 TREND ANALYSIS\n"
                            "   - Current trend: Uptrend / Downtrend / Sideways\n"
                            "   - Support and Resistance levels\n"
                            "   - MA/EMA lines if visible\n\n"
                            "3. 📊 VOLUME ANALYSIS\n"
                            "   - Volume confirmation or divergence\n"
                            "   - Unusual spikes\n\n"
                            "4. 🚨 RISK WARNINGS\n"
                            "   - Pump & Dump signs: Yes / No / Suspected\n"
                            "   - Manipulation wicks: Yes / No\n"
                            "   - Price-volume divergence: Yes / No\n\n"
                            "5. 🎯 3 SCENARIOS FORECAST\n"
                            "   - 🟢 BULLISH: conditions + % probability\n"
                            "   - 🔴 BEARISH: conditions + % probability\n"
                            "   - 🟡 SIDEWAYS: % probability\n"
                            "   (must total 100%)\n\n"
                            "6. ⚡ CONCLUSION\n"
                            "   One concise summary sentence.\n\n"
                            "⚠️ End with: This is not financial advice. Always DYOR."
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192,
        }
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            response = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}",
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                return "❌ Gemini returned no analysis. Please try again."
            text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
            return text.strip() or "❌ Empty response from Gemini. Please try again."

    except httpx.HTTPStatusError as e:
        code = e.response.status_code
        body = e.response.text[:200]
        print(f"[chart] Gemini error {code}: {body}")
        if code == 400:
            return "❌ Invalid image format. Please send a clearer chart screenshot."
        elif code == 429:
            return "❌ Rate limited. Try again in 30 seconds."
        else:
            return f"❌ API Error ({code}). Try again later."
    except httpx.TimeoutException:
        return "❌ Analysis timed out. Please try again."
    except Exception as e:
        print(f"[analyze_chart_image] {e}")
        return f"❌ Unexpected error: {str(e)[:100]}"


# ═══════════════════════════════════════════════════════════════════════
# PRICE FEATURE
# ═══════════════════════════════════════════════════════════════════════

async def fetch_price(coin_input: str) -> str:
    try:
        bin_price = get_binance_ticker_price(coin_input)
        if bin_price is not None:
            return (
                f"💰 **{coin_input.upper()}** now:\n"
                f"Price (Binance): ${bin_price:,.2f} USD\n\n"
                f"⚠️ Cryptocurrency is highly volatile — for reference only."
            )
    except Exception:
        pass

    common = {
        'btc': 'bitcoin', 'bitcoin': 'bitcoin',
        'eth': 'ethereum', 'ethereum': 'ethereum',
        'sol': 'solana',   'solana': 'solana',
        'bnb': 'binancecoin',
        'doge': 'dogecoin',
    }
    cg_id = common.get(coin_input.lower(), coin_input.lower())

    try:
        url = (
            f"https://api.coingecko.com/api/v3/simple/price"
            f"?ids={cg_id}&vs_currencies=usd&include_24hr_change=true"
        )
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        data   = r.json()[cg_id]
        price  = data['usd']
        change = data.get('usd_24h_change', 0)
        emoji  = "🟢" if change >= 0 else "🔴"
        return (
            f"💰 **{coin_input.upper()}**\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💵 Price: **${price:,.2f}** USD\n"
            f"📈 24h: **{change:+.2f}%** {emoji}\n"
            f"📌 _CoinGecko data_\n\n"
            f"⚠️ Highly volatile. Not financial advice."
        )
    except Exception as e:
        print(f"Price fetch error: {e}")
        return f"❌ Couldn't fetch price for {coin_input.upper()}. Try btc, eth, sol..."


# ═══════════════════════════════════════════════════════════════════════
# SCAN — PARALLEL DATA FETCHER (multi-chain aware)
# ═══════════════════════════════════════════════════════════════════════

async def fetch_all_scan_data(addr: str) -> tuple[dict, ChainInfo]:
    """
    Detects chain automatically, then fetches all data sources in parallel.
    Returns (data_dict, chain_info).
    """
    loop = asyncio.get_running_loop()

    async def safe_run(fn, *args):
        try:
            return await asyncio.wait_for(
                loop.run_in_executor(None, fn, *args),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            print(f"[scan] {fn.__name__} timed out")
            return None
        except Exception as e:
            print(f"[scan] {fn.__name__} error: {e}")
            return None

    # Step 1: detect chain
    chain = await detect_chain(addr, check_goplus_token_security)

    # Step 2: fetch everything in parallel
    goplus_t, dex_t, holders_t, deployer_t, source_t = await asyncio.gather(
        safe_run(check_goplus_token_security, addr),
        safe_run(fetch_dexscreener_token_data, addr),
        safe_run(analyze_token_holders, addr),
        safe_run(analyze_deployer, addr),
        # Source code only for EVM chains
        safe_run(fetch_etherscan_contract_source, addr) if chain.id != "solana" else asyncio.sleep(0),
    )

    return {
        "goplus":   goplus_t,
        "dex":      dex_t,
        "holders":  holders_t,
        "deployer": deployer_t,
        "source":   source_t,
        "chain":    chain,       # store chain in data dict for convenience
    }, chain


# ═══════════════════════════════════════════════════════════════════════
# SCAN — RISK ENGINE
# ═══════════════════════════════════════════════════════════════════════

def _safe_float(val, default: float = 0.0) -> float:
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def compute_risk_score(data: dict) -> tuple:
    goplus  = data.get("goplus")  or {}
    dex     = data.get("dex")     or {}
    holders = data.get("holders") or {}

    penalties   = {}
    red_flags   = []
    green_flags = []

    # 1. Honeypot
    if str(goplus.get("is_honeypot", "0")) == "1":
        penalties["honeypot"] = 60
        red_flags.append("🍯 HONEYPOT — you cannot sell this token!")
    else:
        green_flags.append("✅ Not a honeypot (GoPlus)")

    # 2. Taxes
    buy_tax   = _safe_float(goplus.get("buy_tax",  0))
    sell_tax  = _safe_float(goplus.get("sell_tax", 0))
    total_tax = buy_tax + sell_tax
    if total_tax > 30:
        penalties["high_tax"] = 35
        red_flags.append(f"💸 Extreme tax: Buy {buy_tax:.0f}% + Sell {sell_tax:.0f}% = {total_tax:.0f}%")
    elif total_tax > 10:
        penalties["high_tax"] = 20
        red_flags.append(f"⚠️ High tax: Buy {buy_tax:.0f}% + Sell {sell_tax:.0f}% = {total_tax:.0f}%")
    elif total_tax > 5:
        penalties["moderate_tax"] = 8
        red_flags.append(f"📌 Moderate tax: {total_tax:.0f}% total")
    else:
        green_flags.append(f"✅ Low tax: Buy {buy_tax:.0f}% / Sell {sell_tax:.0f}%")

    # 3. Blacklist / Whitelist
    if str(goplus.get("is_blacklisted", "0")) == "1":
        penalties["blacklist"] = 15
        red_flags.append("🚫 Blacklist function — can ban wallets")
    if str(goplus.get("is_whitelisted", "0")) == "1":
        penalties["whitelist"] = 10
        red_flags.append("⚠️ Whitelist — some wallets blocked from trading")

    # 4. Mint / Ownership
    if str(goplus.get("is_mintable", "0")) == "1":
        penalties["mintable"] = 20
        red_flags.append("🏭 Mintable — owner can print unlimited tokens")
    owner_addr = str(goplus.get("owner_address", ""))
    if owner_addr not in ["", "0x0000000000000000000000000000000000000000"]:
        owner_pct = _safe_float(goplus.get("owner_percent", 0))
        if owner_pct > 10:
            penalties["owner_hold"] = 15
            red_flags.append(f"👑 Owner holds {owner_pct:.1f}% of supply — dump risk")
    if str(goplus.get("is_proxy", "0")) == "1":
        penalties["proxy"] = 10
        red_flags.append("🔄 Proxy contract — logic can be changed")

    # 5. Trading controls
    if str(goplus.get("can_take_back_ownership", "0")) == "1":
        penalties["reclaim_ownership"] = 15
        red_flags.append("⚠️ Can reclaim ownership — rug pull risk")
    if str(goplus.get("hidden_owner", "0")) == "1":
        penalties["hidden_owner"] = 20
        red_flags.append("👻 Hidden owner — extremely suspicious")
    if str(goplus.get("trading_cooldown", "0")) == "1":
        penalties["cooldown"] = 5
        red_flags.append("⏱️ Trading cooldown enabled")

    # 6. Liquidity
    liq_usd = _safe_float(dex.get("liquidity", {}).get("usd", 0))
    if liq_usd == 0:
        penalties["no_liquidity"] = 30
        red_flags.append("💧 No liquidity on DexScreener — dead or unverifiable")
    elif liq_usd < 5_000:
        penalties["low_liquidity"] = 25
        red_flags.append(f"💧 Very low liquidity: ${liq_usd:,.0f} — easily manipulated")
    elif liq_usd < 50_000:
        penalties["low_liquidity"] = 12
        red_flags.append(f"💧 Low liquidity: ${liq_usd:,.0f}")
    elif liq_usd < 500_000:
        penalties["medium_liquidity"] = 5
        green_flags.append(f"✅ Moderate liquidity: ${liq_usd:,.0f}")
    else:
        green_flags.append(f"✅ Strong liquidity: ${liq_usd:,.0f}")

    # 7. Volume
    vol_24h = _safe_float(dex.get("volume", {}).get("h24", 0))
    if vol_24h < 1_000 and liq_usd > 0:
        penalties["low_volume"] = 10
        red_flags.append(f"📉 Extremely low 24h volume: ${vol_24h:,.0f}")
    elif vol_24h < 10_000:
        penalties["low_volume"] = 5
        red_flags.append(f"📉 Low 24h volume: ${vol_24h:,.0f}")
    else:
        green_flags.append(f"✅ Active trading: ${vol_24h:,.0f} 24h volume")

    # 8. Whale concentration
    top10_pct = _safe_float(holders.get("top_10_percentage", 0))
    if top10_pct > 80:
        penalties["whales"] = 25
        red_flags.append(f"🐋 Top 10 hold {top10_pct:.1f}% — extreme concentration")
    elif top10_pct > 60:
        penalties["whales"] = 15
        red_flags.append(f"🐋 Top 10 hold {top10_pct:.1f}% — high concentration")
    elif top10_pct > 40:
        penalties["whales"] = 8
        red_flags.append(f"🐋 Top 10 hold {top10_pct:.1f}% — moderate concentration")
    elif top10_pct > 0:
        green_flags.append(f"✅ Reasonable distribution — top 10 hold {top10_pct:.1f}%")

    # 9. Source verification
    if str(goplus.get("is_open_source", "1")) == "0":
        penalties["unverified"] = 15
        red_flags.append("📄 Contract NOT verified — source hidden")
    else:
        green_flags.append("✅ Contract source verified on-chain")

    risk_percent = round(min(max(sum(penalties.values()), 0), 100), 1)
    return risk_percent, red_flags, green_flags


def format_scan_result(addr, risk_percent, red_flags, green_flags, data, ai_summary="", chain: ChainInfo = None) -> str:
    dex          = data.get("dex") or {}
    safe_percent = round(100 - risk_percent, 1)
    chain        = chain or CHAINS["eth"]   # fallback

    if risk_percent <= 20:
        verdict, bar = "LOW RISK 🟢",      "🟩🟩🟩🟩🟩"
    elif risk_percent <= 45:
        verdict, bar = "MODERATE RISK 🟡", "🟨🟨🟨⬜⬜"
    elif risk_percent <= 70:
        verdict, bar = "HIGH RISK 🔴",     "🟥🟥🟥🟥⬜"
    else:
        verdict, bar = "EXTREME RISK 🚨",  "🚨🚨🚨🚨🚨"

    missing    = sum(1 for k in ["goplus", "dex", "holders"] if not data.get(k))
    confidence = ["High ✅", "Medium ⚠️", "Low ❌ (data sources failed)"][min(missing, 2)]

    name   = dex.get("name", "Unknown")
    symbol = dex.get("symbol", "?")
    price  = dex.get("priceUsd", "N/A")
    short  = f"{addr[:6]}...{addr[-4:]}"

    lines = [
        f"🔬 *SCAN RESULT — {short}*",
        f"━━━━━━━━━━━━━━━━━━━━",
        f"⛓️ Chain: *{chain.emoji} {chain.name}*",
        f"📛 Token: *{name}* ({symbol})",
        f"💵 Price: ${price}",
        f"",
        f"🎯 *Risk Score: {risk_percent:.0f}/100*",
        f"{bar}",
        f"Verdict: *{verdict}*",
        f"✅ Safe: *{safe_percent:.0f}%*  |  ⚠️ Risk: *{risk_percent:.0f}%*",
        f"📡 Confidence: {confidence}",
        f"",
    ]
    if red_flags:
        lines += [f"🚩 *Red Flags ({len(red_flags)}):*"] + [f"  {f}" for f in red_flags] + [""]
    if green_flags:
        lines += [f"🟢 *Positive Signals ({len(green_flags)}):*"] + [f"  {f}" for f in green_flags] + [""]
    if ai_summary:
        trimmed = ai_summary.strip()[:600] + ("…" if len(ai_summary) > 600 else "")
        lines += ["🤖 *AI Code Audit:*", trimmed, ""]

    sources = [k.capitalize() for k in ["goplus", "dex", "holders", "source"] if data.get(k)]
    lines.append(f"📡 *Data from:* {', '.join(sources) or 'None'}")
    lines.append("")
    lines.append("⚠️ _Not financial advice. Always DYOR._")
    return "\n".join(lines)


def build_scan_buttons(addr: str, chain: ChainInfo = None) -> InlineKeyboardMarkup:
    chain = chain or CHAINS["eth"]
    return build_chain_scan_buttons(addr, chain)


def build_report_buttons(token_addr: str, chain: ChainInfo = None) -> InlineKeyboardMarkup:
    chain = chain or CHAINS["eth"]
    return build_chain_report_buttons(token_addr, chain)

# ═══════════════════════════════════════════════════════════════════════
# CHAIN DETECTION  — tries multiple fetchers to identify the chain
# ═══════════════════════════════════════════════════════════════════════

async def fetch_trending_tokens() -> dict:
    """
    Fetch trending / top gainers & losers from DexScreener.
    Returns dict with keys: gainers, losers, trending
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.dexscreener.com/token-boosts/top/v1",
                headers={"Accept": "application/json"}
            )
            response.raise_for_status()
            boosted = response.json()

            # Also fetch latest trending pairs
            resp2 = await client.get(
                "https://api.dexscreener.com/token-profiles/latest/v1",
                headers={"Accept": "application/json"}
            )
            resp2.raise_for_status()
            latest = resp2.json()

        return {"boosted": boosted, "latest": latest}
    except Exception as e:
        print(f"[trending] fetch error: {e}")
        return {}


def format_trending_message(data: dict) -> str:
    if not data:
        return "❌ Could not fetch trending data. Try again in a moment."

    boosted = data.get("boosted", [])
    latest  = data.get("latest",  [])

    lines = [
        "🔥 *TRENDING TOKENS — DexScreener*",
        "━━━━━━━━━━━━━━━━━━━━",
        ""
    ]

    # Top boosted tokens
    if boosted and isinstance(boosted, list):
        lines.append("🚀 *Top Boosted Right Now:*")
        for token in boosted[:5]:
            name    = token.get("description", token.get("tokenAddress", "?"))[:30]
            chain   = token.get("chainId", "?").upper()
            addr    = token.get("tokenAddress", "")
            boosts  = token.get("totalAmount", 0)
            short   = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
            url     = token.get("url", f"https://dexscreener.com/{token.get('chainId','')}/{addr}")
            lines.append(f"  🔸 [{name}]({url}) `{chain}` | 🔥 {boosts} boosts")
        lines.append("")

    # Latest token profiles
    if latest and isinstance(latest, list):
        lines.append("🆕 *Latest Listed:*")
        for token in latest[:5]:
            name  = token.get("description", token.get("tokenAddress", "?"))[:30]
            chain = token.get("chainId", "?").upper()
            addr  = token.get("tokenAddress", "")
            url   = token.get("url", f"https://dexscreener.com/{token.get('chainId','')}/{addr}")
            lines.append(f"  🔹 [{name}]({url}) `{chain}`")
        lines.append("")

    lines += [
        "📡 _Data from DexScreener_",
        "",
        "⚠️ _New/boosted tokens carry extremely high risk._",
        "_Always scan before buying: /scan <address>_"
    ]

    return "\n".join(lines)

# ═══════════════════════════════════════════════════════════════════════
# TRENDING COMMAND — shows top boosted tokens and latest listings from DexScreener
# ═══════════════════════════════════════════════════════════════════════
async def trending_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = await update.message.reply_text(
        "🔥 Fetching trending tokens...\n⏳ Checking DexScreener..."
    )
    data      = await fetch_trending_tokens()
    formatted = format_trending_message(data)
    await msg.edit_text(
        formatted,
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
# ═══════════════════════════════════════════════════════════════════════
# COMMANDS
# ═══════════════════════════════════════════════════════════════════════
onboarded_users: set[int] = set()   # in-memory; or persist to data/onboarded.json if needed

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id   = update.effective_user.id
    user_name = update.effective_user.first_name or "there"
    is_new    = user_id not in onboarded_users

    # Send welcome image
    image_url = "https://cellphones.com.vn/sforum/wp-content/uploads/2022/11/su-sup-do-cua-bitcoin-6.jpeg"
    caption = (
        f'🛡️ *Welcome{"back" if not is_new else ""}, {user_name}!*\n'
        f'*CryptoSafe AI* – Crypto Risk Analysis Engine\n'
        '━━━━━━━━━━━━━━━━━━━━\n\n'
        'I help you identify scams, honeypots & risky tokens.\n\n'
        '**📊 What you can do:**\n'
        '  💰 `/price <coin>` – Real-time prices\n'
        '  🔬 `/scan <address>` – Contract vulnerability check\n'
        '  📈 `/chart` – Candlestick chart AI analysis\n'
        '  📊 `/dex <token>` – Market & liquidity analysis\n'
        '  🕵️ `/deployer <token>` – Creator credibility score\n'
        '  🐋 `/holders <token>` – Whale concentration risk\n'
        '  🚨 `/goplus <token>` – Honeypot & tax detection\n'
        '  📄 `/source <address>` – Verified source code\n'
        '  📋 `/report <token>` – Full risk assessment\n\n'
        '  🔔 `/alert BTC above 70000` – Price alerts\n'
        '  🔥 `/trending` – Top trending tokens right now\n\n'
        '📸 **Send any chart image** for AI pattern analysis!\n\n'
        '⚠️ **Remember:** Only invest what you can afford to lose. '
        'This is NOT financial advice.'
    )
    try:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=image_url,
            caption=caption,
            parse_mode='Markdown'
        )
    except Exception:
        await update.message.reply_text(caption, parse_mode='Markdown')

    if is_new:
        onboarded_users.add(user_id)
        await asyncio.sleep(1.0)
        await update.message.reply_text(
            "👋 *First time here?*\n\n"
            "Would you like a quick 3-step intro to learn what this bot can do?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("📖 Yes, show me!", callback_data="onboard_step1"),
                InlineKeyboardButton("⏭️ Skip", callback_data="onboard_done"),
            ]])
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="What would you like to do?",
            reply_markup=MAIN_MENU_KEYBOARD
        )

# ═══════════════════════════════════════════════════════════════════════
# ONBOARDING STEPS — a quick 3-step intro to the bot's main features for new users
# ═══════════════════════════════════════════════════════════════════════
async def _onboarding_step_1(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg_target = update.message or update.callback_query.message
    await msg_target.reply_text(
        "👋 *Step 1 of 3 — Check if a token is safe*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Before buying any token, always run a scan first.\n\n"
        "Just paste a contract address:\n"
        "`0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984`\n\n"
        "Or use the command:\n"
        "`/scan 0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984`\n\n"
        "The bot will check for honeypots, high taxes, rug pull risks and more. 🔬",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Next", callback_data="onboard_step2"),
            InlineKeyboardButton("⏭️ Skip intro", callback_data="onboard_done"),
        ]])
    )


async def _onboarding_step_2(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.message.reply_text(
        "📈 *Step 2 of 3 — Analyze any chart*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "See a chart that looks suspicious? Just *send the image* here.\n\n"
        "AI will detect:\n"
        "  🕯️ Pump & Dump patterns\n"
        "  📊 Volume manipulation\n"
        "  🎯 Bull / Bear / Sideways forecast\n\n"
        "Try it anytime — just send a screenshot of any price chart. 📸",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Next", callback_data="onboard_step3"),
            InlineKeyboardButton("⏭️ Skip intro", callback_data="onboard_done"),
        ]])
    )


async def _onboarding_step_3(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.message.reply_text(
        "🔔 *Step 3 of 3 — Stay ahead of the market*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Set a price alert so you never miss a move:\n"
        "`/alert BTC above 70000`\n"
        "`/alert ETH below 3000`\n\n"
        "Check what's hot right now:\n"
        "`/trending`\n\n"
        "Track any wallet for activity:\n"
        "`/watch 0xabc... WhaleName`\n\n"
        "You're all set! 🚀",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Let's go!", callback_data="onboard_done"),
        ]])
    )


async def _onboarding_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.callback_query.message.reply_text(
        "🛡️ *You're ready!* Here's your menu:",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU_KEYBOARD
    )
    
# ═══════════════════════════════════════════════════════════════════════
# HELP COMMAND — lists all commands with descriptions and usage examples
# ═══════════════════════════════════════════════════════════════════════
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        '📖 **Command Reference**\n'
        '━━━━━━━━━━━━━━━━━━━━━━\n\n'
        '💰 `/price` <symbol> — Real-time price\n\n'
        '🔍 `/scan` <address> — Contract audit\n\n'
        '📈 `/chart` — Send a chart image for AI analysis\n\n'
        '📊 `/dex` <address> — Market & liquidity data\n\n'
        '🕵️ `/deployer` <address> — Creator credibility\n\n'
        '🐋 `/holders` <address> — Whale analysis\n\n'
        '🚨 `/goplus` <address> — Honeypot & tax check\n\n'
        '📄 `/source` <address> — Verified source code\n\n'
        '📋 `/report` <address> — Full risk assessment\n\n'
        '🔔 `/alert BTC above 70000` – Price alerts\n'
        '🔥 `/trending` – Top trending tokens right now\n\n'
        '📸 **Send any chart image anytime** for technical analysis.\n\n'
        '💬 **Free chat:** Ask anything about crypto!'
    )


async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /price btc | /price sol | /price eth...")
        return
    coin = ' '.join(context.args).lower()
    await update.message.reply_text(await fetch_price(coin))


async def chart_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "📈 *Chart Analysis*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "Just *send or forward any chart image* — crypto or stock.\n\n"
        "AI will identify:\n"
        "  🕯️ Candle patterns (H&S, Flag, Doji, Hammer...)\n"
        "  📈 Trend & support/resistance levels\n"
        "  📊 Unusual volume spikes\n"
        "  🚨 Pump & Dump / manipulation signals\n"
        "  🎯 3-scenario forecast (Bull / Bear / Sideways)\n\n"
        "⚠️ _Not financial advice. Always DYOR._",
        parse_mode="Markdown"
    )


async def scan_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text(
            "Usage: `/scan <contract_address>`\n\n"
            "Supports:\n"
            " Ethereum · 🟡 BSC · 🔵 Arbitrum\n"
            " Base · 🟣 Polygon · 🟢 Solana",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args).strip()

    # Validate address format
    if not is_valid_address(query):
        # Treat as Solidity code
        result = deepscan_agent.process_query(query)
        await update.message.reply_text(f"🔎 *Code scan result:*\n\n{result}", parse_mode="Markdown")
        return

    addr       = query
    addr_type  = detect_address_type(addr)
    status_msg = await update.message.reply_text(
        f"🔬 Scanning token...\n"
        f"🔍 Detecting chain ({'EVM' if addr_type == 'evm' else 'Solana'}) · Fetching data in parallel..."
    )

    data, chain = await fetch_all_scan_data(addr)
    
    # Check if ALL data sources returned nothing
    if not any([data.get("goplus"), data.get("dex"), data.get("holders")]):
        await status_msg.edit_text(
            f"⚠️ *No data found for this address*\n\n"
            f"`{addr}`\n\n"
            f"Possible reasons:\n"
            f"  • This is not a token contract\n"
            f"  • Token not listed on any DEX yet\n"
            f"  • Invalid or burn address\n"
            f"  • Wrong chain — try specifying manually\n\n"
            f"_Cannot generate a risk score without data._",
            parse_mode="Markdown"
        )
        return
    sources_hit = [k for k in ["goplus", "dex", "holders"] if data.get(k)]

    await status_msg.edit_text(
        f"✅ Chain: {chain.emoji} {chain.name}\n"
        f"✅ Data from: {', '.join(sources_hit) or 'none'}\n"
        f"🧠 Running risk analysis..."
    )

    ai_summary = ""
    if data.get("source") and isinstance(data["source"], dict):
        src = data["source"].get("SourceCode", "")
        if src:
            try:
                loop = asyncio.get_running_loop()
                ai_summary = await asyncio.wait_for(
                    loop.run_in_executor(None, analyze_solidity_with_groq, src),
                    timeout=15.0
                )
            except Exception as e:
                print(f"AI audit error: {e}")

    risk_percent, red_flags, green_flags = compute_risk_score(data)
    message = format_scan_result(addr, risk_percent, red_flags, green_flags, data, ai_summary, chain)

    await status_msg.delete()
    await update.message.reply_text(
        message,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=build_scan_buttons(addr, chain),
    )


async def dex_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /dex <token_contract_address>")
        return
    addr = context.args[0].strip()
    loop = asyncio.get_running_loop()   # FIX
    data = await loop.run_in_executor(None, fetch_dexscreener_token_data, addr)

    if not data or not isinstance(data, dict):
        await update.message.reply_text("❌ Could not retrieve data from DexScreener.")
        return

    name   = data.get('name', 'Unknown') + f" ({data.get('symbol', '?')})"
    price  = data.get('priceUsd', 'N/A')
    mc     = data.get('fdv', data.get('marketCap', 'N/A'))
    liq    = data.get('liquidity', {}).get('usd', 'N/A')
    volume = data.get('volume', {}).get('h24', 'N/A')
    age    = data.get('pairAge', 'N/A')
    txns   = (
        data.get('txns', {}).get('h24', {}).get('buys', 0)
        + data.get('txns', {}).get('h24', {}).get('sells', 0)
    )
    risk_note = "⚠️ Liquidity very low → manipulation risk" if isinstance(liq, (int, float)) and liq < 10000 else ""

    try: price_fmt = f"${float(price):,.6f}"
    except: price_fmt = f"${price}"
    try: mc_fmt = f"${float(mc):,.0f}"
    except: mc_fmt = str(mc)
    try: liq_fmt = f"${float(liq):,.0f}"
    except: liq_fmt = str(liq)
    try: vol_fmt = f"${float(volume):,.0f}"
    except: vol_fmt = str(volume)

    response = (
        f"📊 **DexScreener – {name}**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 Price: **{price_fmt}** USD\n"
        f"📈 Market Cap / FDV: **{mc_fmt}**\n"
        f"💧 Liquidity: **{liq_fmt}** USD\n"
        f"🔄 Volume 24h: **{vol_fmt}**\n"
        f"🕒 Pair Age: **{age}**\n"
        f"🔁 Transactions 24h: **{txns:,}**\n\n"
        f"{risk_note}\n"
        f"🔗 [View on DexScreener](https://dexscreener.com/ethereum/{addr.lower().replace('0x','')})\n\n"
        f"⚠️ Not financial advice."
    )
    await update.message.reply_text(response, parse_mode='Markdown', disable_web_page_preview=True)


async def deployer_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /deployer <token_contract_address>")
        return

    addr   = context.args[0].strip()
    loop   = asyncio.get_running_loop()

    status_msg = await update.message.reply_text("🕵️ Analyzing deployer...")

    try:
        report = await asyncio.wait_for(
            loop.run_in_executor(None, analyze_deployer, addr),
            timeout=10.0
        )
    except asyncio.TimeoutError:
        await status_msg.edit_text("❌ Deployer analysis timed out.")
        return
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)[:100]}")
        return

    if not report:
        await status_msg.edit_text("❌ Could not retrieve deployer information.")
        return

    # Handle both dict and string responses
    if isinstance(report, dict):
        # Convert dict to readable string
        lines = [f"*{k}:* {v}" for k, v in report.items()]
        summary = "🕵️ *Deployer Analysis*\n━━━━━━━━━━━━━━━━━━━━\n\n" + "\n".join(lines)
    else:
        summary = "🕵️ *Deployer Analysis*\n━━━━━━━━━━━━━━━━━━━━\n\n" + str(report)

    # Add tornado cash warning
    summary_lower = summary.lower()
    if "tornado" in summary_lower:
        summary += "\n\n🚩 *Warning:* Tornado Cash related → high anonymity risk."

    await status_msg.edit_text(
        summary + "\n\n⚠️ Not financial advice.",
        parse_mode="Markdown"
    )

async def holders_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /holders <token_contract_address>")
        return
    addr   = context.args[0]
    loop   = asyncio.get_running_loop()   # FIX
    result = await loop.run_in_executor(None, analyze_token_holders, addr)
    if not result:
        await update.message.reply_text("❌ Could not analyze holders.")
        return

    # Handle dict response
    if isinstance(result, dict):
        top10    = result.get("top_10_percentage", 0)
        risk     = result.get("risk_level", "Unknown")
        total    = result.get("total_holders_analyzed", 0)

        if top10 > 80:
            concentration = "🚨 Extreme — massive dump risk"
        elif top10 > 60:
            concentration = "🔴 High — whales dominate"
        elif top10 > 40:
            concentration = "🟡 Moderate — some concentration"
        else:
            concentration = "🟢 Healthy distribution"

        risk_emoji = {"Low": "🟢", "Medium": "🟡", "High": "🔴", "Extreme": "🚨"}.get(risk, "⚪")

        msg = (
            f"🐋 *Holders Analysis*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"👥 Holders analyzed: *{total}*\n"
            f"📊 Top 10 hold: *{top10:.1f}%*\n"
            f"⚖️ Concentration: {concentration}\n"
            f"🎯 Risk Level: {risk_emoji} *{risk}*\n\n"
            f"⚠️ _Not financial advice._"
        )
    else:
        msg = f"🐋 *Holders Analysis*\n━━━━━━━━━━━━━━━━━━━━\n\n{result}"

    await update.message.reply_text(msg, parse_mode="Markdown")

async def goplus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /goplus <token_contract_address>")
        return
    addr = context.args[0].strip()
    loop = asyncio.get_running_loop()   # FIX
    data = await loop.run_in_executor(None, check_goplus_token_security, addr)

    if not data or not isinstance(data, dict):
        await update.message.reply_text("❌ Could not retrieve GoPlus data.")
        return

    honeypot  = data.get('is_honeypot', 'Unknown')
    buy_tax   = data.get('buy_tax', '0')
    sell_tax  = data.get('sell_tax', '0')
    is_proxy  = data.get('is_proxy', False)
    blacklist = data.get('blacklist', False)

    risk_flags = []
    if honeypot == '1':                                              risk_flags.append("🚨 Honeypot detected!")
    if float(buy_tax or 0) > 10 or float(sell_tax or 0) > 10:       risk_flags.append(f"⚠️ High tax: Buy {buy_tax}% – Sell {sell_tax}%")
    if blacklist:                                                    risk_flags.append("🚫 Blacklist enabled")
    if is_proxy:                                                     risk_flags.append("⚠️ Proxy contract → logic may change")

    response = (
        f"🛡️ **GoPlus Security Check**\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🍯 Honeypot: **{'Yes' if honeypot == '1' else 'No'}**\n"
        f"💸 Tax buy/sell: **{buy_tax}% / {sell_tax}%**\n"
        f"📜 Proxy: **{'Yes' if is_proxy else 'No'}**\n"
        f"🚫 Blacklist: **{'Yes' if blacklist else 'No'}**\n\n"
        f"{chr(10).join(risk_flags) if risk_flags else '🟢 No major risks detected'}\n\n"
        f"🔗 [Full GoPlus report](https://gopluslabs.io/token-security/{addr})\n\n"
        f"⚠️ Not financial advice."
    )
    await update.message.reply_text(response, parse_mode='Markdown', disable_web_page_preview=True)


async def source_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /source <contract_address>")
        return
    addr = context.args[0]
    loop = asyncio.get_running_loop()   # FIX
    data = await loop.run_in_executor(None, fetch_etherscan_contract_source, addr)
    if data:
        text = (
            f"Contract: {data.get('ContractName')} ({addr})\n"
            f"Compiler: {data.get('CompilerVersion')}\n"
            f"--- source truncated ---\n{data.get('SourceCode','')[:1000]}..."
        )
        await update.message.reply_text(text)
    else:
        await update.message.reply_text("❌ Could not retrieve source from Etherscan.")


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: /report <token_contract_address>")
        return

    token      = context.args[0]
    loop       = asyncio.get_running_loop()
    # Works for both direct command and callback button
    msg_target = update.message or update.callback_query.message
    status_msg = await msg_target.reply_text(
        "📋 Generating full report...\n⏳ Detecting chain & fetching all data in parallel..."
    )

    # Detect chain first
    chain = await detect_chain(token, check_goplus_token_security)

    # Fetch all in parallel
    goplus, dex, deploy, holders, source = await asyncio.gather(
        loop.run_in_executor(None, check_goplus_token_security, token),
        loop.run_in_executor(None, fetch_dexscreener_token_data, token),
        loop.run_in_executor(None, analyze_deployer, token),
        loop.run_in_executor(None, analyze_token_holders, token),
        loop.run_in_executor(None, fetch_etherscan_contract_source, token) if chain.id != "solana" else asyncio.sleep(0),
    )

    ai_report = ""
    if source and "SourceCode" in source:
        try:
            ai_report = await asyncio.wait_for(
                loop.run_in_executor(None, analyze_solidity_with_groq, source["SourceCode"]),
                timeout=15.0
            )
        except Exception as e:
            print(f"AI report error: {e}")

    final = generate_telegram_report(
        token,
        goplus  or {},
        dex     or {},
        deploy  or {},
        holders or {},
        ai_report or ""
    )

    await status_msg.delete()
    await msg_target.reply_text(
        final,
        parse_mode="Markdown",
        reply_markup=build_report_buttons(token, chain)
    )


async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage:
      /alert BTC above 70000
      /alert ETH below 3000
      /alerts          → list your alerts
      /delalert <id>   → delete one alert
    """
    args = context.args

    # /alerts — list
    if not args or args[0].lower() == "list":
        user_alerts = alert_manager.get_user_alerts(update.effective_user.id)
        if not user_alerts:
            await update.message.reply_text(
                "🔔 You have no active alerts.\n\n"
                "Set one with:\n`/alert BTC above 70000`\n`/alert ETH below 3000`",
                parse_mode="Markdown"
            )
            return
        lines = ["🔔 *Your Active Alerts:*\n━━━━━━━━━━━━━━━━━━━━"]
        for a in user_alerts:
            arrow = "📈" if a.direction == "above" else "📉"
            lines.append(f"{arrow} *{a.symbol}* {a.direction} *${a.target:,.2f}*\n   ID: `{a.alert_id}`")
        lines.append("\nDelete with: `/delalert <id>`")
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # /alert BTC above 70000
    if len(args) < 3:
        await update.message.reply_text(
            "Usage: `/alert <coin> <above|below> <price>`\n\n"
            "Examples:\n`/alert BTC above 70000`\n`/alert ETH below 3000`",
            parse_mode="Markdown"
        )
        return

    symbol    = args[0].upper()
    direction = args[1].lower()
    if direction not in ("above", "below"):
        await update.message.reply_text("Direction must be `above` or `below`.", parse_mode="Markdown")
        return

    try:
        target = float(args[2].replace(",", ""))
    except ValueError:
        await update.message.reply_text("Invalid price. Use a number like `70000` or `3000.50`.", parse_mode="Markdown")
        return

    alert = alert_manager.add_alert(
        user_id=update.effective_user.id,
        chat_id=update.effective_chat.id,
        symbol=symbol,
        target=target,
        direction=direction
    )
    arrow = "📈" if direction == "above" else "📉"
    await update.message.reply_text(
        f"✅ *Alert set!*\n\n"
        f"{arrow} I'll notify you when *{symbol}* goes *{direction}* *${target:,.2f}*\n\n"
        f"🆔 Alert ID: `{alert.alert_id}`\n"
        f"Delete anytime: `/delalert {alert.alert_id}`",
        parse_mode="Markdown"
    )


async def delalert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not context.args:
        await update.message.reply_text("Usage: `/delalert <alert_id>`", parse_mode="Markdown")
        return
    alert_id = context.args[0]
    success  = alert_manager.remove_alert(update.effective_user.id, alert_id)
    if success:
        await update.message.reply_text("✅ Alert deleted.")
    else:
        await update.message.reply_text("❌ Alert not found. Use `/alert list` to see your alerts.", parse_mode="Markdown")
# ═══════════════════════════════════════════════════════════════════════
# PHOTO HANDLER — CHART ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

async def handle_chart_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    status_msg = await update.message.reply_text(
        "📊 *Analyzing chart...*\n"
        "⏳ Detecting patterns · Volume · Pump/Dump signals...\n\n"
        "_Usually takes 10-20 seconds_",
        parse_mode="Markdown"
    )

    try:
        image_bytes = None

        # Case 1: sent as File/Document
        if update.message.document:
            doc = update.message.document
            if not doc.mime_type or not doc.mime_type.startswith("image/"):
                await status_msg.edit_text("❌ Please send an image file (PNG, JPG).")
                return
            file        = await context.bot.get_file(doc.file_id)
            image_bytes = bytes(await file.download_as_bytearray())

        # Case 2: sent as compressed Photo
        elif update.message.photo:
            photo       = update.message.photo[-1]
            file        = await context.bot.get_file(photo.file_id)
            image_bytes = bytes(await file.download_as_bytearray())

        else:
            await status_msg.edit_text("❌ No image found.")
            return

       

        analysis = await analyze_chart_image(image_bytes)
        try:
            await status_msg.delete()
        except Exception:
            pass

        header = "📊 *CANDLESTICK CHART ANALYSIS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
        full   = header + analysis

        if len(full) > 4000:
            split_at = 3800 - len(header)
            await update.message.reply_text(
                header + analysis[:split_at] + "\n\n_(continued...)_",
                parse_mode="Markdown"
            )
            await update.message.reply_text(
                "_(continued)_\n\n" + analysis[split_at:],
                parse_mode="Markdown"
            )
        # Clean up Gemini markdown to be Telegram-safe
        analysis = (analysis
            .replace("**", "*")        # bold
            .replace("__", "_")        # italic
            .replace("•", "-")         # bullets
        )
        full = header + analysis

        if len(full) > 4000:
            split_at = 3800 - len(header)
            await update.message.reply_text(
                header + analysis[:split_at] + "\n\n_(continued...)_",
                parse_mode="Markdown"
            )
            await update.message.reply_text(
                "_(continued)_\n\n" + analysis[split_at:],
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(full, parse_mode="Markdown")

    except Exception as e:
        print(f"[handle_chart_photo] {e}")
        await status_msg.edit_text(
            "❌ Could not analyze this image. Please try again."
        )

# ═══════════════════════════════════════════════════════════════════════
# LLM (streaming)
# ═══════════════════════════════════════════════════════════════════════

async def generate_response(user_id: int, user_message: str):
    if user_id not in chat_histories:
        chat_histories[user_id] = [{"role": "system", "content": SYSTEM_PROMPT}]
    chat_histories[user_id].append({"role": "user", "content": user_message})
    if len(chat_histories[user_id]) > 15:
        chat_histories[user_id] = chat_histories[user_id][-15:]

    full_response = ""
    try:
        stream = await groq_client.chat.completions.create(
            messages=chat_histories[user_id],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_tokens=2048,
            stream=True
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                delta = chunk.choices[0].delta.content
                full_response += delta
                yield delta
    except Exception as e:
        yield f"\n\nGroq error: {str(e)[:100]}... Please try again."
    chat_histories[user_id].append({"role": "assistant", "content": full_response})


# ═══════════════════════════════════════════════════════════════════════
# MESSAGE HANDLER
# ═══════════════════════════════════════════════════════════════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()

    # ── Menu buttons ───────────────────────────────────────────────────
    if text == "💰 Price":
        await update.message.reply_text("Which coin? Examples: btc eth sol pepe", reply_markup=MAIN_MENU_KEYBOARD)
        return
    elif text == "🔬 Scan / Audit":
        await update.message.reply_text("Paste a contract address (0x...) or Solidity code:", reply_markup=MAIN_MENU_KEYBOARD)
        return
    elif text == "📋 Full Report":
        await update.message.reply_text("Paste the token contract address for a full risk report:", reply_markup=MAIN_MENU_KEYBOARD)
        return
    elif text == "🛡️ Security Check":
        await update.message.reply_text("Paste token address for GoPlus / honeypot check:", reply_markup=MAIN_MENU_KEYBOARD)
        return
    elif text in ["📊 Dex Data", "🐋 Holders"]:
        await update.message.reply_text(f"Paste token contract address for {text.lower()}:", reply_markup=MAIN_MENU_KEYBOARD)
        return
    elif text == "📈 Chart Analysis":
        await update.message.reply_text(
            "📸 *Send any candlestick chart image!*\n\n"
            "AI will detect patterns, volume anomalies, pump/dump signals\n"
            "and give a 3-scenario Bull/Bear/Sideways forecast.\n\n"
            "⚠️ _Not financial advice._",
            parse_mode="Markdown",
            reply_markup=MAIN_MENU_KEYBOARD
        )
        return
    elif text == "Help / Commands":
        await help_command(update, context)
        return
    elif text == "🔔 My Alerts":
        context.args = ["list"]
        await alert_command(update, context)
        return
    elif text == "🔥 Trending":
        await trending_command(update, context)
        return
    
    user_id   = update.effective_user.id
    chat_type = update.message.chat.type
    
    if chat_type in ['group', 'supergroup']:
        if BOT_USERNAME.lower() not in text.lower():
            return
        text = text.replace(BOT_USERNAME, '').replace('@CryptoSafeAI_bot', '').strip()

    text_lower = text.lower()

    # ── Direct contract address → scan (EVM or Solana) ───────────────
    if is_valid_address(text):
        context.args = [text]
        await scan_command(update, context)
        return

    # ── scan/audit keyword ─────────────────────────────────────────────
    if text_lower.startswith("scan ") or text_lower.startswith("audit "):
        parts = text.split(None, 1)
        if len(parts) > 1 and is_valid_address(parts[1].strip()):
            context.args = [parts[1].strip()]
            await scan_command(update, context)
            return

    # ── Quick price ────────────────────────────────────────────────────
    price_kws    = ['price', 'cost', 'how much', 'today', 'current price', 'expense', 'worth', 'value']
    common_coins = ['btc', 'bitcoin', 'eth', 'ethereum', 'sol', 'solana']
    if any(kw in text_lower for kw in price_kws) and any(c in text_lower for c in common_coins):
        for coin in common_coins:
            if coin in text_lower:
                await update.message.reply_text(await fetch_price(coin))
                return

    if text_lower.startswith('/price '):
        await update.message.reply_text(await fetch_price(text.split(' ', 1)[1].strip()))
        return

    if text_lower.startswith('/report ') or text_lower.startswith('report '):
        context.args = [text.split(' ', 1)[1].strip()]
        await report_command(update, context)
        return

    # ── LLM fallback (streaming) ───────────────────────────────────────
    msg                  = await update.message.reply_text("Analyzing... 🧠")
    full_text, last_edit = "", 0

    async for token in generate_response(user_id, text):
        full_text += token
        now = asyncio.get_running_loop().time()   # FIX
        if now - last_edit >= 1.2:
            try:
                await msg.edit_text(full_text + (" ▌" if len(full_text) % 2 else ""))
                last_edit = now
            except Exception:
                pass

    try:
        await msg.edit_text(full_text)
    except Exception:
        await update.message.reply_text(full_text)
        
   


# ═══════════════════════════════════════════════════════════════════════
# ERROR HANDLER
# ═══════════════════════════════════════════════════════════════════════

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    print(f'Error: {context.error}')


# ═══════════════════════════════════════════════════════════════════════
# CALLBACK HANDLER
# ═══════════════════════════════════════════════════════════════════════

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    data  = query.data

    if data.startswith("scan_refresh|"):
        parts     = data.split("|")
        addr      = parts[1]
        chain_id  = parts[2] if len(parts) > 2 else "eth"
        chain     = CHAINS.get(chain_id, CHAINS["eth"])
        await query.message.edit_text(
            f"🔄 Re-scanning `{addr[:8]}...` on {chain.emoji} {chain.name}",
            parse_mode="Markdown"
        )
        scan_data, chain = await fetch_all_scan_data(addr)
        risk_percent, red_flags, green_flags = compute_risk_score(scan_data)
        msg = format_scan_result(addr, risk_percent, red_flags, green_flags, scan_data, chain=chain)
        await query.message.edit_text(
            msg,
            parse_mode="Markdown",
            disable_web_page_preview=True,
            reply_markup=build_scan_buttons(addr, chain)
        )
        return

    if data.startswith("full_report|"):
        parts = data.split("|")
        addr  = parts[1]
        await query.message.reply_text(f"📋 Generating full report for `{addr[:8]}...`", parse_mode="Markdown")
        context.args = [addr]
        await report_command(update, context)
        return

    if data.startswith("refresh_report|"):
        parts    = data.split("|")
        addr     = parts[1]
        chain_id = parts[2] if len(parts) > 2 else "eth"
        chain    = CHAINS.get(chain_id, CHAINS["eth"])
        await query.message.edit_text(
            f"🔄 Refreshing report for {addr}...",
            reply_markup=build_report_buttons(addr, chain)
        )
        return
    if data == "onboard_step2":
        await update.callback_query.answer()
        await _onboarding_step_2(update, context)
        return

    if data == "onboard_step3":
        await update.callback_query.answer()
        await _onboarding_step_3(update, context)
        return

    if data == "onboard_done":
        await update.callback_query.answer()
        await _onboarding_done(update, context)
        return
    if data == "onboard_step1":
        await _onboarding_step_1(update, context)
        return
    if data == "main_menu":
        await query.message.reply_text("Main menu", reply_markup=MAIN_MENU_KEYBOARD)
        return


# ═══════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════

def main() -> None:
    print('🚀 CryptoSafe AI starting...')

    async def post_init(application):
        asyncio.create_task(alert_polling_loop(application.bot, alert_manager, interval=60))

    # ✅ ONE line only — with post_init
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler('start',    start_command))
    app.add_handler(CommandHandler('help',     help_command))
    app.add_handler(CommandHandler('price',    price_command))
    app.add_handler(CommandHandler('chart',    chart_command))
    app.add_handler(CommandHandler('scan',     scan_command))
    app.add_handler(CommandHandler('dex',      dex_command))
    app.add_handler(CommandHandler('deployer', deployer_command))
    app.add_handler(CommandHandler('holders',  holders_command))
    app.add_handler(CommandHandler('goplus',   goplus_command))
    app.add_handler(CommandHandler('source',   source_command))
    app.add_handler(CommandHandler('report',   report_command))
    app.add_handler(CommandHandler('alert',    alert_command))
    app.add_handler(CommandHandler('delalert', delalert_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_chart_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler('trending', trending_command))
    
    print('Polling...')
    app.run_polling(
        poll_interval=3,
        timeout=20,
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == '__main__':
    import signal, sys

    def shutdown(signum, frame):
        print("Shutting down gracefully...")
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    main()