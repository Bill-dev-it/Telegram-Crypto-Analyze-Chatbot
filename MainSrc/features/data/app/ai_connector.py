import os
import aiohttp
import asyncio
import logging
from tenacity import retry, retry_if_exception_type, wait_exponential, stop_after_attempt

logger = logging.getLogger(__name__)

class AIConnector:
    def __init__(self):
        self.groq_api_key = os.getenv("GROQ_API_KEY", "")
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.groq_url = "https://api.groq.com/openai/v1/chat/completions"
        self.gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={self.gemini_api_key}"

    @retry(
        # Sử dụng Tenacity tự động thử lại nếu gặp lỗi Timeout
        retry=retry_if_exception_type((asyncio.TimeoutError, aiohttp.ClientError)),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(3), # Thử lại tối đa 3 lần
        reraise=True
    )
    async def _analyze_with_groq(self, session: aiohttp.ClientSession, code: str):
        headers = {
            "Authorization": f"Bearer {self.groq_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "llama3-70b-8192", 
            "messages": [
                {"role": "user", "content": f"Analyze this contract for crypto risk:\n{code}"}
            ]
        }
        # Đặt timeout ngắn hơn (ví dụ 10s) cho mỗi request để kích hoạt cơ chế retry của Tenacity
        timeout = aiohttp.ClientTimeout(total=10)
        async with session.post(self.groq_url, headers=headers, json=payload, timeout=timeout) as response:
            if response.status == 429:
                return "QUOTA_EXCEEDED"
            response.raise_for_status()
            return await response.json()

    async def _analyze_with_gemini(self, session: aiohttp.ClientSession, code: str):
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "contents": [{
                "parts": [{"text": f"Analyze this smart contract for crypto risk:\n{code}"}]
            }]
        }
        async with session.post(self.gemini_url, headers=headers, json=payload) as response:
            response.raise_for_status()
            return await response.json()

    async def _run_analysis(self, code: str):
        async with aiohttp.ClientSession() as session:
            try:
                # 1. Gọi Groq API theo mặc định
                groq_response = await self._analyze_with_groq(session, code)
                
                # 2. Xử lý trường hợp Groq hết Quota (chuyển sang gọi Gemini Flash)
                if groq_response == "QUOTA_EXCEEDED":
                    logger.warning("Groq limit exceeded/out of quota. Switching to Gemini Flash API...")
                    return await self._analyze_with_gemini(session, code)
                
                return groq_response
            except Exception as e:
                logger.error(f"Error during AI analysis: {str(e)}")
                raise e

    async def analyze_contract(self, code: str):
        """Hàm chính gọi AI để kiểm tra mã code."""
        try:
            # 3. Đảm bảo nếu sau 30 giây không có phản hồi, trả về 'Hệ thống bận'
            # Sử dụng asyncio.wait_for bao phủ toàn bộ quá trình bao gồm cả retry
            return await asyncio.wait_for(self._run_analysis(code), timeout=30.0)
        except asyncio.TimeoutError:
            return "Hệ thống bận"
        except Exception as e:
            return f"Lỗi hệ thống: {str(e)}"