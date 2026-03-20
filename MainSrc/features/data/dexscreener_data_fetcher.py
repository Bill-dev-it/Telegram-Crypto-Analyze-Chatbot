import logging
import requests
from typing import Optional, Dict, Any

# Configure module logger
logger = logging.getLogger(__name__)

def fetch_dexscreener_token_data(
    token_address: str, 
    timeout: float = 5.0
) -> Optional[Dict[str, Optional[float]]]:
    """
    Fetches real-time token metrics (price, liquidity, volume) for a given token address 
    from the DexScreener API.
    
    Args:
        token_address (str): The contract address of the token (e.g., '0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2').
        timeout (float, optional): Request timeout in seconds. Defaults to 5.0.
        
    Returns:
        Optional[Dict[str, Optional[float]]]: A dictionary containing metric data if successful,
            or None if an error occurs. 
            Returns: 'priceUsd', 'liquidity.usd', 'volume.h24', 'marketCap' keys mapping to float or None.
    """
    url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
    
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()  # Catch HTTP errors
        data = response.json()
        
        pairs = data.get("pairs")
        if not pairs or not isinstance(pairs, list) or len(pairs) == 0:
            logger.warning(f"No pairs found for token address: {token_address}")
            return None
            
        # Often a token has multiple pairs. We pick the one with the highest USD liquidity
        # to get the most accurate and primary liquid market.
        best_pair = max(
            pairs, 
            key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0)
        )

        # Safely extract required fields
        price_usd_str = best_pair.get("priceUsd")
        
        liquidity_dict = best_pair.get("liquidity", {})
        liquidity_usd = liquidity_dict.get("usd")
        
        volume_dict = best_pair.get("volume", {})
        volume_h24 = volume_dict.get("h24")
        
        # Market Cap / FDV
        market_cap = best_pair.get("marketCap")
        if market_cap is None:
            market_cap = best_pair.get("fdv")
        
        # Social and info fields
        info_dict = best_pair.get("info", {})
        websites = info_dict.get("websites", [])
        socials = info_dict.get("socials", [])
        
        return {
            "priceUsd": float(price_usd_str) if price_usd_str is not None else None,
            "liquidity.usd": float(liquidity_usd) if liquidity_usd is not None else None,
            "volume.h24": float(volume_h24) if volume_h24 is not None else None,
            "marketCap": float(market_cap) if market_cap is not None else None,
            "websites": websites,
            "socials": socials
        }

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while fetching {token_address} data: {http_err} - Response: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection error occurred while fetching {token_address} data: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"Timeout occurred while fetching {token_address} data: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"An unexpected error occurred while fetching {token_address} data: {req_err}")
    except ValueError as val_err:
        logger.error(f"Failed to parse JSON response for {token_address}: {val_err}")
    except Exception as e:
        logger.error(f"Unexpected error when processing {token_address}: {e}")
        
    return None

if __name__ == "__main__":
    # Demo basic configuration to see output
    logging.basicConfig(level=logging.INFO)
    
    # Example using Ethereum's Wrapped ETH (WETH) address
    test_address = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
    result = fetch_dexscreener_token_data(test_address)
    
    if result is not None:
        print(f"Data for {test_address}:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print(f"Failed to fetch data for {test_address}.")
