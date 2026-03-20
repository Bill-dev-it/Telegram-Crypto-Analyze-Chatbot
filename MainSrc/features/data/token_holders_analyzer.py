import os
import logging
import requests
from typing import Optional, Dict, Any

# Configure module logger
logger = logging.getLogger(__name__)

# Known burn addresses or common dead addresses to exclude from top holder analysis
BURN_ADDRESSES = [
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead"
]

def analyze_token_holders(
    token_address: str,
    api_key: Optional[str] = None,
    chain: str = "eth",
    timeout: float = 10.0
) -> Optional[Dict[str, Any]]:
    """
    Fetches the top token holders using Moralis API and calculates the concentration risk.
    Exclude burn addresses from the 'Whale' percentage calculation.
    """
    api_key = api_key or os.getenv("MORALIS_API_KEY")
    if not api_key:
        logger.warning("No Moralis API key provided. Token holders analysis may fail.")

    url = f"https://deep-index.moralis.io/api/v2.2/erc20/{token_address}/owners"
    headers = {
        "accept": "application/json",
        "X-API-Key": api_key
    }
    params = {
        "chain": chain,
        "order": "DESC"
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        owners = data.get("result", [])
        if not owners:
            return None
            
        # Filter out burn addresses
        active_owners = [
            o for o in owners 
            if o.get("owner_address", "").lower() not in BURN_ADDRESSES
        ]
        
        # Analyze top 10 active addresses (might include DEX pairs, which is expected but handled in reports)
        top_10 = active_owners[:10]
        
        top_10_percent = 0.0
        for owner in top_10:
            pct_str = owner.get("percentage_relative_to_total_supply")
            if pct_str is not None:
                top_10_percent += float(pct_str)
                
        # Determine risk
        risk_level = "Low"
        if top_10_percent > 80:
            risk_level = "Extreme"
        elif top_10_percent > 50:
            risk_level = "High"
        elif top_10_percent > 30:
            risk_level = "Medium"
            
        return {
            "top_10_percentage": top_10_percent,
            "risk_level": risk_level,
            "total_holders_analyzed": len(owners)
        }

    except Exception as e:
        logger.error(f"Error fetching token holders: {e}")
        return None

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    # Test with PEPE
    test_token = "0x6982508145454Ce325dDbE47a25d4ec3d2311933"
    result = analyze_token_holders(test_token)
    if result:
        print(f"Top 10 Holders Concentration: {result['top_10_percentage']:.2f}%")
        print(f"Risk Level: {result['risk_level']}")
    else:
        print("Failed to analyze token holders.")
