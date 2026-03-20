import logging
import requests
from typing import Optional, Dict, Any

# Configure module logger
logger = logging.getLogger(__name__)

def check_goplus_token_security(
    contract_address: str,
    chain_id: int = 1,
    timeout: float = 5.0
) -> Optional[Dict[str, Any]]:
    """
    Fetches token security data from the GoPlus Token Security API.
    
    Args:
        contract_address (str): The token contract address to query.
        chain_id (int, optional): The blockchain ID (1 for Ethereum, 56 for BSC, etc.). Defaults to 1.
        timeout (float, optional): Request timeout in seconds. Defaults to 5.0.
        
    Returns:
        Optional[Dict[str, Any]]: A structured dictionary containing token security info:
            - is_honeypot (bool or None)
            - buy_tax (float or None)
            - sell_tax (float or None)
            - owner_address (str or None)
            Returns None if the request failed or if the token is not found.
    """
    # GoPlus requires the address to be lowercased to reliably fetch from the result map
    contract_address_lower = contract_address.lower()
    
    url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}"
    params = {
        "contract_addresses": contract_address_lower
    }
    
    try:
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        # GoPlus uses 'code' == 1 to indicate success
        if data.get("code") != 1:
            logger.error(f"GoPlus API Error: {data.get('message')}")
            return None
            
        result = data.get("result", {})
        if not result or contract_address_lower not in result:
            logger.warning(f"No security data found for token: {contract_address}")
            return None
            
        token_data = result[contract_address_lower]
        
        # Safely parse the response fields, falling back to None if missing or empty
        # GoPlus frequently returns values as strings '0', '1', '0.05', or ""
        
        # Parse Honeypot
        is_honeypot_str = token_data.get("is_honeypot", "")
        if is_honeypot_str == "1":
            is_honeypot = True
        elif is_honeypot_str == "0":
            is_honeypot = False
        else:
            is_honeypot = None
            
        # Parse Buy Tax
        buy_tax_str = token_data.get("buy_tax", "")
        try:
            buy_tax = float(buy_tax_str) if buy_tax_str else None
        except ValueError:
            buy_tax = None
            
        # Parse Sell Tax
        sell_tax_str = token_data.get("sell_tax", "")
        try:
            sell_tax = float(sell_tax_str) if sell_tax_str else None
        except ValueError:
            sell_tax = None
            
        # Owner Address
        owner_address = token_data.get("owner_address")
        if owner_address == "" or owner_address == "0x0000000000000000000000000000000000000000":
            owner_address = None

        return {
            "is_honeypot": is_honeypot,
            "buy_tax": buy_tax,
            "sell_tax": sell_tax,
            "owner_address": owner_address
        }

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while checking security for {contract_address}: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection error occurred while checking security for {contract_address}: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"Timeout occurred while checking security for {contract_address}: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"An unexpected error occurred while checking security for {contract_address}: {req_err}")
    except ValueError as val_err:
        logger.error(f"Failed to parse JSON response: {val_err}")

    return None

if __name__ == "__main__":
    # Test script setup
    logging.basicConfig(level=logging.INFO)
    
    # We test with PEPE token address (Ethereum)
    test_address = "0x6982508145454Ce325dDbE47a25d4ec3d2311933"
    
    logger.info(f"Checking token security for {test_address}...")
    security_info = check_goplus_token_security(test_address)
    
    if security_info:
        print(f"\nSecurity details for {test_address}:")
        for key, val in security_info.items():
            print(f"  {key}: {val}")
    else:
        print(f"\nFailed to retrieve security info.")
