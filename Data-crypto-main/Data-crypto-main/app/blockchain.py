import asyncio
import os
import logging
from web3 import AsyncWeb3, AsyncHTTPProvider
from eth_utils import to_checksum_address

logger = logging.getLogger(__name__)

# Địa chỉ của Multicall3 Contract trên Ethereum Mainnet
MULTICALL3_ADDRESS = "0xcA11bde05977b3631167028862bE2a173976CA11"

# ABI thu gọn cho Multicall3 và Token ERC20 chuẩn
MULTICALL3_ABI = [
    {
        "inputs": [
            {
                "components": [
                    {"internalType": "address", "name": "target", "type": "address"},
                    {"internalType": "bytes", "name": "callData", "type": "bytes"}
                ],
                "internalType": "struct Multicall3.Call[]",
                "name": "calls",
                "type": "tuple[]"
            }
        ],
        "name": "aggregate",
        "outputs": [
            {"internalType": "uint256", "name": "blockNumber", "type": "uint256"},
            {"internalType": "bytes[]", "name": "returnData", "type": "bytes[]"}
        ],
        "stateMutability": "payable",
        "type": "function"
    }
]

ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [], "name": "totalSupply", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
]

class BlockchainFetcher:
    def __init__(self):
        # Lấy RPC URL từ biến môi trường. Ví dụ: Alchemy, Infura, Ankr
        rpc_url = os.getenv("ETHEREUM_RPC_URL", "https://eth.public-rpc.com")
        
        # SỬ DỤNG AsyncHTTPProvider để không chặn event loop (Non-blocking I/O)
        self.w3 = AsyncWeb3(AsyncHTTPProvider(rpc_url))
        self.multicall_contract = self.w3.eth.contract(
            address=to_checksum_address(MULTICALL3_ADDRESS), 
            abi=MULTICALL3_ABI
        )

    async def get_token_info(self, token_address: str):
        """
        Sử dụng Multicall3 để nhóm 4 request (name, symbol, decimals, totalSupply) lại thành 1 request duy nhất.
        """
        try:
            checksum_address = to_checksum_address(token_address)
            
            # Khởi tạo contract tạm để chuẩn bị calldata
            token_contract = self.w3.eth.contract(address=checksum_address, abi=ERC20_ABI)
            
            # 1. Mã hóa encodeABI() cho từng hàm cần gọi
            name_calldata = token_contract.encodeABI(fn_name="name", args=[])
            symbol_calldata = token_contract.encodeABI(fn_name="symbol", args=[])
            decimals_calldata = token_contract.encodeABI(fn_name="decimals", args=[])
            supply_calldata = token_contract.encodeABI(fn_name="totalSupply", args=[])

            # 2. Xây dựng mảng calls cho Multicall
            calls = [
                (checksum_address, name_calldata),
                (checksum_address, symbol_calldata),
                (checksum_address, decimals_calldata),
                (checksum_address, supply_calldata),
            ]

            # 3. Thực thi async aggregate call (Gộp 4 call thành 1 rpc call)
            _, return_data = await self.multicall_contract.functions.aggregate(calls).call()

            # 4. Decode kết quả (returnData) trả về từ Multicall
            # web3.py decode_function_result trả về tuple, nên cần lấy phần tử [0]
            name = token_contract.functions.name().decode_function_result(return_data[0])[0]
            symbol = token_contract.functions.symbol().decode_function_result(return_data[1])[0]
            decimals = token_contract.functions.decimals().decode_function_result(return_data[2])[0]
            total_supply = token_contract.functions.totalSupply().decode_function_result(return_data[3])[0]

            return {
                "address": token_address,
                "name": name,
                "symbol": symbol,
                "decimals": decimals,
                "total_supply": total_supply
            }
            
        except Exception as e:
            logger.error(f"Error fetching token info via Multicall: {e}")
            raise e
