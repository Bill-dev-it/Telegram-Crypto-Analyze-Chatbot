from typing import Dict, Any


def generate_telegram_report(
    token_address: str,
    goplus_data: Dict[str, Any],
    dex_data: Dict[str, Any],
    deployer_data: Dict[str, Any],
    holders_data: Dict[str, Any],
    ai_report: str
) -> str:
    """
    Generates an English, emoji-rich Telegram report summarizing
    the Token Scan result, and provides a final investment conclusion.
    """

    # 1. Format GoPlus Security Data
    goplus_section = "🛡 **Smart Contract Security (GoPlus)**:\n"
    if not goplus_data:
        goplus_section += "   ⚠️ Unable to retrieve security data.\n"
        honeypot_risk = True  # Assume risk if no data
    else:
        is_honeypot = goplus_data.get("is_honeypot")
        buy_tax = goplus_data.get("buy_tax", 0)
        sell_tax = goplus_data.get("sell_tax", 0)

        if is_honeypot:
            goplus_section += "   ❌ **HONEYPOT DETECTED**: You cannot sell this token!\n"
            honeypot_risk = True
        else:
            goplus_section += "   ✅ No honeypot detected.\n"
            honeypot_risk = False

        tax_str = f"Buy Tax: {buy_tax}% | Sell Tax: {sell_tax}%"
        if buy_tax is not None and sell_tax is not None:
            if buy_tax > 10 or sell_tax > 10:
                goplus_section += f"   ⚠️ {tax_str} (High tax!)\n"
            else:
                goplus_section += f"   ✅ {tax_str}\n"
        else:
            goplus_section += "   ⚠️ Tax information unavailable.\n"

    # 2. Format DexScreener Market Data
    market_section = "\n📈 **Market Data (DexScreener)**:\n"
    liquidity_risk = False
    wash_trading_risk = False

    if not dex_data:
        market_section += "   ⚠️ No live market data available.\n"
        liquidity_risk = True  # Assume risk
    else:
        liquidity = dex_data.get("liquidity.usd", 0)
        volume_24h = dex_data.get("volume.h24", 0)
        market_cap = dex_data.get("marketCap", 0)

        market_section += f"   💧 Liquidity: ${liquidity:,.0f}\n"
        market_section += f"   📊 24h Volume: ${volume_24h:,.0f}\n"

        if market_cap:
            market_section += f"   🌐 Market Cap: ${market_cap:,.0f}\n"

        websites = dex_data.get("websites", [])
        socials = dex_data.get("socials", [])
        social_str = f"🌐 Websites: {len(websites)} | 📱 Socials: {len(socials)}"
        if len(websites) == 0 and len(socials) == 0:
            market_section += f"   ❌ **ALERT**: NO COMMUNITY PRESENCE (0 Websites, 0 Socials). Likely a scam token!\n"
        else:
            market_section += f"   ✅ {social_str}\n"

        # Liquidity Check
        if liquidity < 10000:
            market_section += "   ❌ **RUG PULL RISK**: Liquidity is extremely low (< $10k).\n"
            liquidity_risk = True
        elif market_cap and market_cap > 0 and (liquidity / market_cap) < 0.05:
            market_section += "   ⚠️ **WARNING**: Thin liquidity (< 5% of Market Cap) — easy to manipulate.\n"
            liquidity_risk = True
        else:
            market_section += "   ✅ Liquidity is at a stable level.\n"

        # Wash Trading Check
        if liquidity > 0 and (volume_24h / liquidity) > 5:
            market_section += "   ⚠️ **WASH TRADING WARNING**: Volume is >5x the liquidity — signs of fake volume!\n"
            wash_trading_risk = True

    # 3. Format Deployer Data
    deployer_section = "\n🕵️‍♂️ **Deployer Analysis (Creator)**:\n"
    deployer_risk = False
    if not deployer_data:
        deployer_section += "   ⚠️ Unable to analyze creator history.\n"
    else:
        creator = deployer_data.get("creator_address")
        score = deployer_data.get("credibility_score", 100)
        funded_by_tornado = deployer_data.get("funded_by_tornado", False)
        spam_risk = deployer_data.get("spam_token_risk", False)
        abnormal_transfers = deployer_data.get("abnormal_transfers", False)

        if creator:
            deployer_section += f"   👤 Wallet: `{creator}`\n"

        deployer_section += f"   🎯 Credibility Score: {score}/100\n"

        if funded_by_tornado:
            deployer_section += "   ❌ **RED ALERT**: Deployer funds originated from a Mixer (Tornado Cash)!\n"
            deployer_risk = True
        if spam_risk:
            deployer_section += "   ⚠️ **WARNING**: This wallet deployed multiple spam tokens in the past 30 days.\n"
            deployer_risk = True
        if abnormal_transfers:
            deployer_section += "   ⚠️ **WARNING**: Suspicious token distribution detected (fake airdrop / whale wallet farming).\n"
            deployer_risk = True

        if not (funded_by_tornado or spam_risk or abnormal_transfers):
            deployer_section += "   ✅ Deployer history looks clean — no red flags found.\n"

    # 4. Format Holders Data
    holders_section = "\n🐋 **Token Distribution (Top Holders)**:\n"
    holders_risk = False
    if not holders_data:
        holders_section += "   ⚠️ Unable to analyze token distribution.\n"
    else:
        top_10 = holders_data.get("top_10_percentage", 0)
        risk_level = holders_data.get("risk_level", "Medium")

        holders_section += f"   🍩 Top 10 wallet concentration: {top_10:.2f}%\n"
        if risk_level == "Extreme":
            holders_section += "   ❌ **RUG PULL WARNING**: Top 10 wallets hold over 80% of circulating supply!\n"
            holders_risk = True
        elif risk_level == "High":
            holders_section += "   ⚠️ **HIGH RISK**: Top 10 wallets hold over 50% of supply — beware of whale dumps.\n"
            holders_risk = True
        elif risk_level == "Medium":
            holders_section += "   ⚠️ Moderate concentration (> 30%).\n"
        else:
            holders_section += "   ✅ Token distribution looks healthy (Top 10 < 30%).\n"

    # 5. Format AI Report
    ai_section = "\n🤖 **Source Code Analysis (AI)**:\n"
    ai_risk = False
    if "❌ RISK ALERT" in ai_report or "failed" in ai_report.lower():
        ai_section += f"   ❌ Error: {ai_report.strip()}\n"
        ai_risk = True
    else:
        if "High" in ai_report or "Critical" in ai_report or "Scam" in ai_report:
            ai_section += "   ❌ AI detected serious vulnerabilities or risks in the smart contract!\n"
            ai_risk = True
        else:
            ai_section += "   ✅ AI found no critical suspicious patterns in the source code.\n"

    # 6. Final Conclusion
    conclusion = "\n⚖️ **FINAL VERDICT**: "
    reason = ""

    if honeypot_risk:
        conclusion += "❌ **AVOID (SCAM LIKELY)**"
        reason = "Token is a Honeypot — you can buy but cannot sell."
    elif deployer_data and deployer_data.get("funded_by_tornado"):
        conclusion += "❌ **AVOID (SCAM DEPLOYER)**"
        reason = "Creator wallet used anonymous funds from Tornado Cash (99% scammer)."
    elif liquidity_risk and wash_trading_risk:
        conclusion += "❌ **AVOID (HIGH RISK)**"
        reason = "Fake volume (Wash Trading) combined with extremely thin liquidity — price can collapse at any time."
    elif holders_risk:
        conclusion += "❌ **DUMP RISK WARNING**"
        reason = "Token supply is heavily controlled by a small number of whale wallets."
    elif liquidity_risk:
        conclusion += "⚠️ **HIGH RISK**"
        reason = "Liquidity is too low — high risk of rug pull or severe price slippage."
    elif deployer_risk:
        conclusion += "⚠️ **HIGH RISK (SUSPICIOUS CREATOR)**"
        reason = "Token creator has a highly suspicious history (spam tokens or fake distribution)."
    elif ai_risk:
        conclusion += "⚠️ **CAUTION (WARNING)**"
        reason = "Source code contains potential risks or is unverified/non-transparent."
    elif wash_trading_risk:
        conclusion += "⚠️ **CAUTION (WARNING)**"
        reason = "Trading volume appears to be mostly bots buying/selling to create artificial FOMO."
    else:
        conclusion += "✅ **WATCHLIST / RELATIVELY SAFE**"
        reason = "No honeypot detected, liquidity is stable, and no obvious red flags found."

    final_report = (
        f"🔍 **AntiGravity Quick Scan**\n"
        f"🔗 Network: Ethereum | Token: `{token_address}`\n\n"
        f"{goplus_section}"
        f"{market_section}"
        f"{deployer_section}"
        f"{holders_section}"
        f"{ai_section}"
        f"{conclusion}\n"
        f"📝 **Reason**: {reason}\n\n"
        f"⚠️ _Not financial advice. Always DYOR._"
    )

    return final_report