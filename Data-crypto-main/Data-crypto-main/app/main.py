import os
import json
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import redis.asyncio as redis
import asyncpg
import polars as pl
from dotenv import load_dotenv

# Import các components nội bộ
from .blockchain import BlockchainFetcher
from .ai_connector import AIConnector

# Tải biến môi trường từ file .env
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Crypto Risk Analysis API", version="1.0.0")

# Global instances
blockchain_fetcher = None
ai_connector = None
redis_client = None
db_pool = None

@app.on_event("startup")
async def startup_event():
    global blockchain_fetcher, ai_connector, redis_client, db_pool
    
    logger.info("Starting up FastAPI application...")
    
    # 1. Khởi tạo các hệ thống Connector
    blockchain_fetcher = BlockchainFetcher()
    ai_connector = AIConnector()
    
    # 2. Khởi tạo kết nối Redis (Cache)
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis_client = redis.from_url(redis_url, decode_responses=True)
    
    # 3. Khởi tạo kết nối PostgreSQL bằng asyncpg (Non-blocking DB driver)
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:secure_password@db:5432/crypto_risk")
    try:
        db_pool = await asyncpg.create_pool(db_url)
        logger.info("Đã kết nối PostgreSQL thành công.")
    except Exception as e:
        logger.error(f"Lỗi kết nối PostgreSQL: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down Application...")
    if redis_client:
        await redis_client.close()
    if db_pool:
        await db_pool.close()

class ScanRequest(BaseModel):
    user_id: str  # UID mã định danh (UUID) của người dùng từ bảng Users
    contract_address: str

@app.post("/api/v1/scan")
async def scan_contract(req: ScanRequest):
    """
    Endpoint chính để quét Smart Contract kết hợp: Web3 -> Polars -> AI -> PostgreSQL -> Redis.
    """
    contract_address = req.contract_address

    # BƯỚC 1: Caching LAYER
    # Kiểm tra Token đã từng quét trong 5 phút qua chưa?
    cache_key = f"token_scan:{contract_address.lower()}"
    cached_data = await redis_client.get(cache_key)
    
    if cached_data:
        logger.info(f"Cache hit: {contract_address}")
        return {
            "status": "success",
            "source": "cache",
            "data": json.loads(cached_data)
        }
        
    logger.info(f"Cache miss: {contract_address}. Tiến hành tải thông tin live...")
    
    # BƯỚC 2: BLOCKCHAIN LAYER
    # Sử dụng hàm lấy dữ liệu từ Blockchain (Sử dụng Web3 Multicall) để lấy name, symbol, decimals.
    try:
        token_info = await blockchain_fetcher.get_token_info(contract_address)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Lỗi Blockchain Fetching: {str(e)}")

    # BƯỚC 3: PROCESSING LAYER
    # Sử dụng Polars thay vì Pandas để xử lý Data Frame với tốc độ siêu tốc
    try:
        df = pl.DataFrame([token_info])
        
        # Xử lý làm sạch, Transform Data bằng cú pháp Polars
        df_processed = df.with_columns([
            # Chú thích rõ các trường hợp Token cực lớn vượt quá Range BigInt tiêu chuẩn, chuyển kiểu Utf8
            pl.col("total_supply").cast(pl.Utf8).alias("supply_string"), 
            # Điền thêm thông tin mạng hoặc cắm thêm cờ cảnh báo rủi ro nếu cần
            pl.lit("Ethereum").alias("chain_network")
        ])
        
        # Biến Data Frame về lại Dict để làm cấu trúc Prompt
        processed_data = df_processed.to_dicts()[0]
    except Exception as e:
        logger.error(f"Lỗi xử lý Data bằng Polars: {e}")
        processed_data = token_info # Fallback

    # BƯỚC 4: AI LAYER
    # Gửi dữ liệu Contract cho hệ thống AI phân tích
    prompt_data = json.dumps(processed_data, indent=2)
    ai_result = await ai_connector.analyze_contract(prompt_data)
    
    # Nếu hệ thống Timeout (Sau 30s) hoặc có lỗi thì trả về 'Hệ thống bận'
    if ai_result == "Hệ thống bận":
        return {
            "status": "error",
            "message": "Hệ thống bận"
        }
    
    # System có thể parse "risk score" từ phản hồi của Groq/Gemini theo Format định sẵn
    risk_score_mock = 50.0 
    
    response_data = {
        "token_info": processed_data,
        "ai_analysis": ai_result,
        "risk_score": risk_score_mock
    }
    
    # BƯỚC 5: DATABASE LAYER
    # Lưu dữ liệu vào PostgreSQL bằng trình kết nối Asyncpg nhanh với Transaction
    try:
        async with db_pool.acquire() as conn:
            async with conn.transaction():
                # Upsert dữ liệu vào bảng Tokens, dùng last_scanned_at thay vì scanned_at
                await conn.execute("""
                    INSERT INTO tokens (contract_address, name, symbol, network, risk_score)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (contract_address) DO UPDATE
                    SET risk_score = EXCLUDED.risk_score, last_scanned_at = CURRENT_TIMESTAMP
                """, processed_data["address"], processed_data["name"], processed_data["symbol"], 'Ethereum', risk_score_mock)
                
                # Lưu thông tin quét vào bảng ScanHistory (Result dạng JSONB)
                result_json_str = json.dumps(response_data)
                await conn.execute("""
                    INSERT INTO scan_history (user_id, token_address, result_json)
                    VALUES ($1::uuid, $2, $3::jsonb)
                """, req.user_id, processed_data["address"], result_json_str)
                
    except Exception as e:
        logger.error(f"Lỗi lưu trữ Database PostgreSQL: {e}")
    
    # CASHING LAYER (CẬP NHẬT TRẠNG THÁI CUỐI)
    # Lưu dữ liệu phân tích này vào cache trong vòng 5 PHÚT = 300 giây
    await redis_client.setex(cache_key, 300, json.dumps(response_data))

    return {
        "status": "success",
        "source": "live_analysis",
        "data": response_data
    }
