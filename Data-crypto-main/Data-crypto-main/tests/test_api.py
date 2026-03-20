import json
import pytest
import asyncio
from httpx import AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

# Import app FastAPI từ module main
from app.main import app

# Cấu hình Pytest để cho phép chạy các async function tự động
pytestmark = pytest.mark.asyncio

@pytest.fixture
async def async_client():
    """Fixture cung cấp Test Client bất đồng bộ cho ứng dụng FastAPI"""
    async with AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

async def test_api_scan_workflow(async_client):
    """
    Test Kịch bản: Yêu cầu quét Token từ Bot. 
    Yêu cầu Pass:
    - AI trả về kết quả dưới 30 giây (Do ta Mock thì tốn < 1s)
    - Redis Cache và Postgres SQL gọi được hàm lưu dữ liệu
    - Tránh rỗng / sai cấu trúc API.
    """
    test_user_id = "123e4567-e89b-12d3-a456-426614174000"
    test_contract = "0x1234567890123456789012345678901234567890"

    mock_token_info = {
        "address": test_contract,
        "name": "TestToken",
        "symbol": "TST",
        "decimals": 18,
        "total_supply": 1000000
    }
    
    mock_ai_response = {
        "choices": [{"message": {"content": "Phân tích rủi ro an toàn."}}]
    }

    # ----- KHỞI TẠO MOCKING (Giả lập Dịch vụ Bị Tính Phí) -----
    
    # 1. Mock Redis
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Giả lập chưa có trong Cache (Cache Miss)
    
    # 2. Mock Database Pool (asyncpg)
    mock_db_pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_transaction = AsyncMock()
    
    # Setup chain context manager cho async with: db_pool.acquire() và conn.transaction()
    mock_db_pool.acquire.return_value.__aenter__.return_value = mock_conn
    mock_conn.transaction.return_value.__aenter__.return_value = mock_transaction

    # 3. Tiến hành Patch vào các thành phần global trong app/main.py
    with patch("app.main.redis_client", mock_redis), \
         patch("app.main.db_pool", mock_db_pool), \
         patch("app.main.blockchain_fetcher") as mock_blockchain, \
         patch("app.main.ai_connector") as mock_ai:
             
        # Cấu hình Mock Blockchain trả giá trị ngay lập tức
        mock_blockchain.get_token_info = AsyncMock(return_value=mock_token_info)
        
        # Cấu hình Mock AI trả giá trị ngay lập tức (không tốn tiền API thật)
        mock_ai.analyze_contract = AsyncMock(return_value=mock_ai_response)

        # ----- THỰC THI (ACTION) -----
        request_payload = {
            "user_id": test_user_id,
            "contract_address": test_contract
        }

        # Bắt đầu tính thời gian
        start_time = asyncio.get_event_loop().time()
        
        response = await async_client.post("/api/v1/scan", json=request_payload)
        
        end_time = asyncio.get_event_loop().time()
        elapsed_time = end_time - start_time

        # ----- KIỂM TRA (ASSERTIONS) -----
        
        # 1. API phải trả về HTTP 200 OK
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "success"
        
        # 2. Xử lý phải dưới 30 giây (Do mocking, thường ms < 1s)
        assert elapsed_time < 30.0, "API mất quá nhiều thời gian phản hồi (vượt ngưỡng 30s)!"
        
        # 3. Phải gọi hàm quét blockchain 1 lần với địa chỉ đúng khớp
        mock_blockchain.get_token_info.assert_called_once_with(test_contract)
        
        # 4. Phải gọi hàm phân tích AI 1 lần
        mock_ai.analyze_contract.assert_called_once()
        
        # 5. Phải gọi hàm update Cache (thời gian lưu 300 giây ~ 5 phút)
        # Bắt đối số arguments truyền vào redis_client.setex
        mock_redis.setex.assert_called_once()
        call_args = mock_redis.setex.call_args[0]
        assert call_args[0] == f"token_scan:{test_contract.lower()}"
        assert call_args[1] == 300  # TTL 5 phút
        
        # 6. Mắc chốt kiểm tra hàm DataBase Insert chạy 2 lệnh SQL UPSERT và INSERT
        # Mỗi dấu 'execute' tương đương một lần chèn
        assert mock_conn.execute.call_count == 2
