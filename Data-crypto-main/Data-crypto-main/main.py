import os
import sys
import logging

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from goplus_security_fetcher import check_goplus_token_security
from dexscreener_data_fetcher import fetch_dexscreener_token_data
from etherscan_source_fetcher import fetch_etherscan_contract_source
from groq_ai_analyzer import analyze_solidity_with_groq
from deployer_analyzer import analyze_deployer
from report_generator import generate_telegram_report
from token_holders_analyzer import analyze_token_holders

# Configure Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AntigravityEngine")

def run_antigravity_core_scan(token_address):
    print(f"\n{'='*60}")
    print(f"ANTIGRAVITY INITIALIZING SCAN FOR: {token_address}")
    print(f"{'='*60}\n")

    # STEP 1: Fast Security Filtering (GoPlus API)
    print("[STEP 1/5] Executing GoPlus Security Check...")
    security = check_goplus_token_security(token_address)
    
    if not security:
        logger.warning("Could not retrieve security data from GoPlus.")

    # STEP 2: Real-time Market Analysis (DexScreener API)
    print("[STEP 2/5] Fetching Liquidity & Market Data...")
    market = fetch_dexscreener_token_data(token_address)
    if market:
        liquidity = market.get("liquidity.usd", 0)
        volume_24h = market.get("volume.h24", 0)
        market_cap = market.get("marketCap", 0)
        
        print(f" -> Current Liquidity: ${liquidity:,.2f}")
        print(f" -> 24h Volume: ${volume_24h:,.2f}")
        if market_cap:
            print(f" -> Market Cap: ${market_cap:,.2f}")
            
        websites = market.get("websites", [])
        socials = market.get("socials", [])
        print(f" -> Project Links: {len(websites)} Website(s), {len(socials)} Social(s)")
            
        if liquidity < 10000:
            print(" -> 🚨 WARNING: Low liquidity detected (< $10k). High risk of Rug-pull.")
            
        # Wash Trading Check (Volume > 5x Liquidity)
        if liquidity > 0:
            vol_liq_ratio = volume_24h / liquidity
            if vol_liq_ratio > 5:
                print(f" -> 🚨 WARNING: Fake Volume / Wash Trading likely! Volume is {vol_liq_ratio:.1f}x higher than liquidity.")
                
        # Thin Liquidity Check (Liquidity < 5% of Market Cap)
        if market_cap and market_cap > 0:
            liq_mcap_ratio = liquidity / market_cap
            if liq_mcap_ratio < 0.05:
                print(f" -> 🚨 WARNING: Extremely thin liquidity! Liquidity is only {liq_mcap_ratio*100:.2f}% of Market Cap. Risk of price manipulation.")
    
    # STEP 3: Deployer History Analysis
    print("\n[STEP 3/7] Analyzing Deployer Address & History...")
    deployer_data = analyze_deployer(token_address)
    if deployer_data:
        print(f" -> Creator: {deployer_data.get('creator_address', 'Unknown')}")
        print(f" -> Credibility Score: {deployer_data.get('credibility_score', 0)}/100")
        print(f" -> Conclusion: {deployer_data.get('conclusion', '')}")

    # STEP 4: Token Holders & Distribution Risk
    print("\n[STEP 4/7] Analyzing Token Holders Distribution (Moralis)...")
    holders_data = analyze_token_holders(token_address)
    if holders_data:
        print(f" -> Total Holders Analyzed: {holders_data.get('total_holders_analyzed')} (Top visible)")
        print(f" -> Top 10 Wallet Concentration: {holders_data.get('top_10_percentage', 0):.2f}%")
        print(f" -> Risk Level: {holders_data.get('risk_level')}")
    else:
        print(" -> ⚠️ No holder data found or missing Moralis API Key.")
    
    # STEP 5: Source Code Retrieval (Etherscan API)
    print("\n[STEP 5/7] Fetching Solidity Source Code from Etherscan...")
    source_data = fetch_etherscan_contract_source(token_address)
    ai_report = ""
    if not source_data or not source_data.get("SourceCode"):
        ai_report = "❌ RISK ALERT: Unverified Source Code or API Key missing. Deep Analysis aborted."
    else:
        # STEP 6: AI-Powered Deep Vulnerability Scan (Groq Llama-3)
        print("\n[STEP 6/7] Sending Source Code to Groq AI for Analysis...")
        ai_report = analyze_solidity_with_groq(source_data["SourceCode"])
        if not ai_report:
            ai_report = "❌ AI Analysis Engine failed to respond."
            
    # STEP 7: Telegram Report Generation
    print("\n[STEP 7/7] Generating Telegram AntiGravity Report...")
    telegram_report = generate_telegram_report(
        token_address=token_address,
        goplus_data=security,
        dex_data=market,
        deployer_data=deployer_data,
        holders_data=holders_data,
        ai_report=ai_report
    )
    
    return telegram_report

if __name__ == "__main__":
    # Example: PEPE Token Address for Demonstration
    target_token = "0x6982508145454Ce325dDbE47a25d4ec3d2311933" 
    
    final_output = run_antigravity_core_scan(target_token)
    print("\n" + "#"*25 + " FINAL SECURITY REPORT " + "#"*25)
    print(final_output)