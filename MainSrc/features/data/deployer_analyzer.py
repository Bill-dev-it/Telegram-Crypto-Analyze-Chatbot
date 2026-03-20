import os
import time
import logging
import requests
from typing import Optional, Dict, Any

# Configure module logger
logger = logging.getLogger(__name__)

# Known Tornado Cash and anonymous mixing addresses (Ethereum)
TORNADO_CASH_ADDRESSES = [
    "0x12d66f87a04a9e220743712ce6d9bb1b5616b8fc", # 0.1 ETH
    "0x47ce0c6ed5b0ce3d3a51f16aecfca7ce3e64baa8", # 1 ETH
    "0x910cbd523d972eb0a6f4cae4618ad62622b39dbf", # 10 ETH
    "0xa160cdab225685da0d56aa342ad8841c3b53f291", # 100 ETH
    "0xd90e2f925ba6a4b7517cf29c441a96a60bdf845c"  # Router
]

def fetch_contract_creator(contract_address: str, api_key: Optional[str]) -> Optional[str]:
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": "1",
        "module": "contract",
        "action": "getcontractcreation",
        "contractaddresses": contract_address
    }
    if api_key:
        params["apikey"] = api_key
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("status") == "1" and data.get("result"):
            return data["result"][0].get("contractCreator")
    except Exception as e:
        logger.error(f"Error fetching contract creator: {e}")
    return None

def fetch_deployer_normal_txs(deployer_address: str, api_key: Optional[str]) -> list[Dict[str, Any]]:
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": "1",
        "module": "account",
        "action": "txlist",
        "address": deployer_address,
        "startblock": 0,
        "endblock": 99999999,
        "sort": "asc"
    }
    if api_key:
        params["apikey"] = api_key
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("status") == "1":
            return data.get("result", [])
    except Exception as e:
        logger.error(f"Error fetching deployer txs: {e}")
    return []

def fetch_token_transfers(deployer_address: str, token_address: str, api_key: Optional[str]) -> list[Dict[str, Any]]:
    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": "1",
        "module": "account",
        "action": "tokentx",
        "contractaddress": token_address,
        "address": deployer_address,
        "page": 1,
        "offset": 100,
        "sort": "asc"
    }
    if api_key:
        params["apikey"] = api_key
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get("status") == "1":
            return data.get("result", [])
    except Exception as e:
        logger.error(f"Error fetching token transfers: {e}")
    return []

def analyze_deployer(token_address: str) -> Dict[str, Any]:
    api_key = os.getenv("ETHERSCAN_API_KEY", "")
    if not api_key:
        logger.warning("No ETHERSCAN_API_KEY set. Deployer analysis may fail.")

    report = {
        "creator_address": None,
        "funded_by_tornado": False,
        "spam_token_risk": False,
        "recent_deployments": 0,
        "abnormal_transfers": False,
        "credibility_score": 100,
        "conclusion": "Safe"
    }

    creator = fetch_contract_creator(token_address, api_key)
    if not creator:
        report["conclusion"] = "Could not fetch creator address."
        return report

    report["creator_address"] = creator
    
    txs = fetch_deployer_normal_txs(creator, api_key)
    
    # 1. Check Tornado Cash funding and 2. Count recent deployments
    thirty_days_ago = int(time.time()) - (30 * 24 * 3600)
    deploy_count: int = 0
    
    for tx in txs:
        # Check funding from Tornado Cash
        # Sometimes deployers get funded via internal txs, but we'll check normal txs mainly
        if tx.get("from", "").lower() in TORNADO_CASH_ADDRESSES:
            report["funded_by_tornado"] = True
            
        # Count deployments (to is empty string)
        if tx.get("to") == "" and int(tx.get("timeStamp", 0)) > thirty_days_ago:
            deploy_count += 1
            
    report["recent_deployments"] = deploy_count
    if deploy_count > 5:
        report["spam_token_risk"] = True
        
    # 3. Check abnormal transfers to Top Holders
    token_txs = fetch_token_transfers(creator, token_address, api_key)
    transfers_out = [tx for tx in token_txs if tx.get("from", "").lower() == creator.lower()]
    
    unique_receivers = set()
    for tx in transfers_out[:10]: # Look at first 10 transfers out
        to_addr = tx.get("to", "").lower()
        if to_addr:
            unique_receivers.add(to_addr)
            
    # If the deployer manually sent tokens to >= 3 different wallets right after deployment
    # This might indicate hiding tokens in shark wallets before adding liquidity
    if len(unique_receivers) >= 3:
        report["abnormal_transfers"] = True

    # 4. Determine Credibility
    penalty = 0
    if report["funded_by_tornado"]:
        penalty += 50
    if report["spam_token_risk"]:
        penalty += 30
    if report["abnormal_transfers"]:
        penalty += 40
        
    score = max(0, 100 - penalty)
    report["credibility_score"] = score
    
    if score < 40:
        report["conclusion"] = "Extremely High Risk - SCAM LIKELY"
    elif score < 70:
        report["conclusion"] = "High Risk - Suspicious Creator Activity"
    else:
        report["conclusion"] = "Low/Moderate Risk - No major red flags"

    return report

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_token = "0x6982508145454Ce325dDbE47a25d4ec3d2311933" # PEPE
    res = analyze_deployer(test_token)
    print(res)
