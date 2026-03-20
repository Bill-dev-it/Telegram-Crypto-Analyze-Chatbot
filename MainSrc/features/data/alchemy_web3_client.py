import os
import logging
from typing import Optional
from web3 import Web3
from web3.exceptions import InvalidAddress

# Configure module logger
logger = logging.getLogger(__name__)

# Standard ERC-20 ABI for totalSupply function
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"name": "", "type": "uint256"}],
        "payable": False,
        "stateMutability": "view",
        "type": "function",
    }
]

class AlchemyWeb3Client:
    """
    A Web3 client to connect to the Ethereum network via an Alchemy RPC URL.
    """
    def __init__(self, rpc_url: Optional[str] = None):
        """
        Initializes the Web3 connection using the provided RPC URL or falls back to
        the ALCHEMY_RPC_URL environment variable.
        
        Args:
            rpc_url (Optional[str]): The Alchemy Ethereum RPC URL.
            
        Raises:
            ValueError: If the RPC URL is not provided and ALCHEMY_RPC_URL is not set.
            ConnectionError: If the Web3 connection fails.
        """
        self.rpc_url = rpc_url or os.getenv("ALCHEMY_RPC_URL")
        
        if not self.rpc_url:
            raise ValueError("Alchemy RPC URL must be provided or set in ALCHEMY_RPC_URL env var")
            
        self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
        
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to Alchemy RPC at {self.rpc_url}")
            
        logger.info("Successfully connected to Alchemy Ethereum RPC.")

    def get_latest_block_number(self) -> int:
        """
        Fetches the latest block number from the connected Ethereum node.
        
        Returns:
            int: The latest block number.
        """
        try:
            return self.w3.eth.block_number
        except Exception as e:
            logger.error(f"Failed to fetch latest block number: {e}")
            raise

    def get_token_total_supply(self, token_address: str) -> int:
        """
        Fetches the total supply of a given ERC-20 token.
        
        Args:
            token_address (str): The contract address of the ERC-20 token.
            
        Returns:
            int: The total supply of the token in its smallest generic unit (e.g., wei).
            
        Raises:
            ValueError: If the provided address is invalid.
        """
        try:
            checksum_address = self.w3.to_checksum_address(token_address)
        except InvalidAddress as e:
            logger.error(f"Invalid token address provided: {token_address}")
            raise ValueError(f"Invalid token address: {e}")
            
        try:
            contract = self.w3.eth.contract(address=checksum_address, abi=ERC20_ABI)
            return contract.functions.totalSupply().call()
        except Exception as e:
            logger.error(f"Failed to fetch total supply for {token_address}: {e}")
            raise

if __name__ == "__main__":
    # Configure basic logging for demo
    logging.basicConfig(level=logging.INFO)
    
    # You must provide ALCHEMY_RPC_URL as an environment variable or pass it to the class.
    # e.g. export ALCHEMY_RPC_URL="https://eth-mainnet.g.alchemy.com/v2/YOUR_API_KEY"
    try:
        client = AlchemyWeb3Client()
        
        block_num = client.get_latest_block_number()
        print(f"Latest Block: {block_num}")
        
        # Example: Tether USD (USDT) on Ethereum
        usdt_address = "0xdac17f958d2ee523a2206206994597C13D831ec7"
        supply = client.get_token_total_supply(usdt_address)
        print(f"USDT Total Supply (in smallest units): {supply}")
    except ValueError as val_err:
        print(f"Configuration Error: {val_err}")
    except ConnectionError as conn_err:
        print(f"Connection Error: {conn_err}")
    except Exception as e:
        print(f"An error occurred: {e}")
