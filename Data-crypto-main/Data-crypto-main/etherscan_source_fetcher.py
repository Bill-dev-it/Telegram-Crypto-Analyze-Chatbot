import os
import time
import logging
import requests
from typing import Optional, Dict

# Configure module logger
logger = logging.getLogger(__name__)

def fetch_etherscan_contract_source(
    contract_address: str,
    api_key: Optional[str] = None,
    max_retries: int = 3,
    retry_delay: float = 1.0,
    timeout: float = 10.0
) -> Optional[Dict[str, str]]:
    """
    Fetches the Solidity source code and metadata from Etherscan API for a given contract address.
    
    Args:
        contract_address (str): The Ethereum contract address to query.
        api_key (Optional[str]): Etherscan API key. Falls back to ETHERSCAN_API_KEY environment variable.
        max_retries (int): Maximum retries for handling rate limit (429/Max rate limit) errors.
        retry_delay (float): Wait time in seconds between retries.
        timeout (float): Request timeout in seconds.
        
    Returns:
        Optional[Dict[str, str]]: A dictionary containing 'SourceCode', 'ContractName', 
            and 'CompilerVersion'. Returns None if the request failed or if the source is not found.
    """
    api_key = api_key or os.getenv("ETHERSCAN_API_KEY")
    if not api_key:
        logger.warning("No Etherscan API key provided. Requests may be severely rate-limited or rejected.")

    url = "https://api.etherscan.io/v2/api"
    params = {
        "chainid": "1",  # 1 for Ethereum Mainnet handling V2 structural requirement
        "module": "contract",
        "action": "getsourcecode",
        "address": contract_address
    }
    
    if api_key:
        params["apikey"] = api_key
    
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()
            
            # Etherscan responds with status="1" on success, "0" on error
            status = data.get("status")
            message = data.get("message", "").lower()
            result = data.get("result", "")
            
            if status == "0":
                # Handle Etherscan specific rate limits which return status 0 and a "Max rate limit reached" message
                if "rate limit" in message or (isinstance(result, str) and "rate limit" in result.lower()):
                    if attempt < max_retries:
                        logger.warning(f"Rate limited by Etherscan. Retrying in {retry_delay} seconds (Attempt {attempt + 1}/{max_retries})...")
                        time.sleep(retry_delay)
                        # Exponential backoff can be added here if needed (e.g., retry_delay *= 2)
                        continue
                    else:
                        logger.error("Max retries reached. Etherscan rate limits persisting.")
                        return None
                else:
                    logger.error(f"Etherscan API Error: Message='{message}', Result='{result}'")
                    return None
            
            # Successful fetch usually returns a list under "result"
            if not isinstance(result, list) or len(result) == 0:
                logger.error(f"Unexpected result format from Etherscan: {result}")
                return None
                
            contract_data = result[0]
            
            # Ensure the contract actually has verified source code
            source_code = contract_data.get("SourceCode", "").strip()
            if not source_code:
                # Etherscan often returns empty SourceCode for unverified contracts
                logger.warning(f"No source code found or contract not verified for address {contract_address}")
                return None
                
            return {
                "SourceCode": source_code,
                "ContractName": contract_data.get("ContractName", ""),
                "CompilerVersion": contract_data.get("CompilerVersion", "")
            }
            
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request failed: {req_err}")
            # If it's a network issue (like connection drop or HTTP 429), retry
            if attempt < max_retries:
                time.sleep(retry_delay)
                continue
            return None
        except ValueError as val_err:
            logger.error(f"Failed to parse JSON response: {val_err}")
            return None
            
    return None

if __name__ == "__main__":
    # Test script setup
    logging.basicConfig(level=logging.INFO)
    
    # We test with Tether (USDT) contract address which is publicly verified
    test_address = "0xdAC17F958D2ee523a2206206994597C13D831ec7"
    
    logger.info(f"Fetching source code for {test_address}...")
    result = fetch_etherscan_contract_source(test_address)
    
    if result:
        print(f"\nSuccessfully fetched {test_address} metadata:")
        print(f"Contract Name: {result.get('ContractName')}")
        print(f"Compiler Version: {result.get('CompilerVersion')}")
        
        # Displaying a small snippet of the source code
        source = result.get('SourceCode', '')
        print("\nSource Code Snippet:")
        print(f"{source[:300]}\n...")
    else:
        print(f"\nFailed to fetch contract source.")
