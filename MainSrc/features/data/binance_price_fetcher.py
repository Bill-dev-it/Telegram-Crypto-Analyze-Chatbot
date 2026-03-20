import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional

# Configure module logger
logger = logging.getLogger(__name__)

def get_binance_ticker_price(
    symbol: str, 
    base_url: str = "https://api.binance.com", 
    endpoint: str = "/api/v3/ticker/price",
    max_retries: int = 3,
    timeout: float = 5.0
) -> Optional[float]:
    """
    Fetches the real-time price for a given symbol from the Binance Spot API.
    
    Args:
        symbol (str): The trading pair symbol (e.g., 'BTCUSDT').
        base_url (str, optional): The base URL for the Binance API. Defaults to "https://api.binance.com".
        endpoint (str, optional): The endpoint for the ticker price. Defaults to "/api/v3/ticker/price".
        max_retries (int, optional): Maximum number of retries for failed requests. Defaults to 3.
        timeout (float, optional): Request timeout in seconds. Defaults to 5.0.
        
    Returns:
        Optional[float]: The current price as a float, or None if the request failed after retries.
    """
    symbol = symbol.upper().replace("-", "").replace("/", "").replace("_", "")
    
    # If the user just passed a raw coin ticker like 'BTC' or 'ETH' (3-5 chars), automatically append 'USDT'
    if len(symbol) in [2, 3, 4, 5] and not any(symbol.endswith(quote) for quote in ["USDT", "USDC", "BUSD", "FDUSD", "EUR", "TRY"]):
        symbol += "USDT"
        
    url = f"{base_url}{endpoint}"
    params = {"symbol": symbol}

    # Configure session with retry strategy
    session = requests.Session()
    retry_strategy = Retry(
        total=max_retries,
        backoff_factor=1.0,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    try:
        response = session.get(url, params=params, timeout=timeout)
        response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
        
        data = response.json()
        if "price" in data:
            return float(data["price"])
        else:
            logger.error(f"Unexpected response format from Binance API: {data}")
            return None
            
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while fetching {symbol} price: {http_err} - Response: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection error occurred while fetching {symbol} price: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"Timeout occurred while fetching {symbol} price: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"An unexpected error occurred while fetching {symbol} price: {req_err}")
    except ValueError as val_err:
        logger.error(f"Failed to parse price data for {symbol}: {val_err}")
        
    return None

if __name__ == "__main__":
    # Basic logging setup for testing
    logging.basicConfig(level=logging.INFO)
    
    # Test the function
    symbol = "BTCUSDT"
    price = get_binance_ticker_price(symbol)
    if price is not None:
        print(f"Current {symbol} price: {price}")
    else:
        print(f"Failed to fetch {symbol} price.")
