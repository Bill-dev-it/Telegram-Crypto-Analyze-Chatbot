import os
import logging
import requests
from typing import Optional

# Configure module logger
logger = logging.getLogger(__name__)

def fetch_moralis_native_balance(
    wallet_address: str,
    api_key: Optional[str] = None,
    chain: str = "eth",
    timeout: float = 5.0
) -> Optional[float]:
    """
    Fetches the native balance (e.g., ETH) for a given wallet address using the Moralis API.
    
    Args:
        wallet_address (str): The wallet address to query.
        api_key (Optional[str]): Moralis API key. Falls back to MORALIS_API_KEY environment variable.
        chain (str, optional): The blockchain to query (e.g., 'eth', 'bsc', 'polygon'). Defaults to 'eth'.
        timeout (float, optional): Request timeout in seconds. Defaults to 5.0.
        
    Returns:
        Optional[float]: The wallet's native balance parsed as a float (e.g., in ETH) 
            or None if the request failed.
    """
    # Fallback to fetching API key from environment
    api_key = api_key or os.getenv("MORALIS_API_KEY")
    
    if not api_key:
        logger.warning("No Moralis API key provided. Set MORALIS_API_KEY env var.")
        return None

    # Moralis v2.2 endpoint for wallet native balance
    url = f"https://deep-index.moralis.io/api/v2.2/{wallet_address}/balance"
    
    headers = {
        "accept": "application/json",
        "X-API-Key": api_key
    }
    
    params = {
        "chain": chain
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        # Moralis returns balance in Wei as a string
        balance_wei_str = data.get("balance")
        
        if balance_wei_str is None:
            logger.error(f"Unexpected response format from Moralis API: {data}")
            return None
            
        # Convert Wei to ETH (10^18)
        balance_eth = float(balance_wei_str) / (10 ** 18)
        return balance_eth

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while fetching balance for {wallet_address}: {http_err} - Response: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection error occurred while fetching balance for {wallet_address}: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"Timeout occurred while fetching balance for {wallet_address}: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"An unexpected error occurred while fetching balance for {wallet_address}: {req_err}")
    except ValueError as val_err:
        logger.error(f"Failed to parse JSON response or float conversion: {val_err}")

    return None

if __name__ == "__main__":
    # Test script setup
    logging.basicConfig(level=logging.INFO)
    
    # Example wallet address (Vitalik's public address)
    test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    
    logger.info(f"Fetching ETH balance for {test_address}...")
    
    # To run this successfully, ensure you prefix the command with:
    # MORALIS_API_KEY=your_key_here python moralis_balance_fetcher.py
    eth_balance = fetch_moralis_native_balance(test_address)
    
    if eth_balance is not None:
        print(f"\nBalance for {test_address}: {eth_balance} ETH")
    else:
        print(f"\nFailed to retrieve balance.")
