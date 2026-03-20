import os
import logging
import requests
from typing import Optional

# Configure module logger
logger = logging.getLogger(__name__)

def analyze_solidity_with_groq(
    source_code: str,
    api_key: Optional[str] = None,
    model: str = "llama3-70b-8192",
    timeout: float = 10.0
) -> Optional[str]:
    """
    Sends Solidity source code to the Groq API (using Llama3) for analysis.
    
    Args:
        source_code (str): The Solidity source code to analyze.
        api_key (Optional[str]): Groq API key. Falls back to GROQ_API_KEY environment variable.
        model (str, optional): The AI model to use. Defaults to "llama3-70b-8192".
        timeout (float, optional): Request timeout in seconds. Defaults to 10.0.
        
    Returns:
        Optional[str]: The AI-generated analysis text, or None if the request failed.
    """
    api_key = api_key or os.getenv("GROQ_API_KEY")
    
    if not api_key:
        logger.warning("No Groq API key provided. Set GROQ_API_KEY env var.")
        return None

    url = "https://api.groq.com/openai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Creating a system prompt to guide the AI, followed by the actual source code
    prompt = (
        "You are an expert smart contract auditor and blockchain security analyst. "
        "Review the following Solidity source code for vulnerabilities, inefficiencies, "
        "and general code quality. Provide a concise, highly technical analysis.\n\n"
        "CRITICAL CHECK (PROXY CONTRACT RECOGNITION):\n"
        "Kiểm tra xem mã nguồn này có sử dụng mô hình Proxy (như EIP-1967, UUPS, Transparent) không?\n"
        "Nếu có, hãy tìm địa chỉ 'Implementation Contract' và giải thích cho người dùng rằng Admin có thể thay đổi toàn bộ chức năng của token này bất cứ lúc nào mà không cần sự đồng ý của họ.\n\n"
        f"Source Code:\n{source_code}"
    )

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.2  # Keep it relatively deterministic for technical analysis
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        data = response.json()
        
        # Parse the structured response
        choices = data.get("choices", [])
        if not choices:
            logger.error(f"Unexpected response format from Groq API (no choices returned): {data}")
            return None
            
        ai_response_text = choices[0].get("message", {}).get("content", "")
        return ai_response_text

    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while contacting Groq: {http_err} - Response: {response.text}")
    except requests.exceptions.ConnectionError as conn_err:
        logger.error(f"Connection error occurred while contacting Groq: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        logger.error(f"Timeout occurred while contacting Groq (configured {timeout}s): {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        logger.error(f"An unexpected error occurred while contacting Groq: {req_err}")
    except ValueError as val_err:
        logger.error(f"Failed to parse JSON response: {val_err}")

    return None

if __name__ == "__main__":
    # Test script setup
    logging.basicConfig(level=logging.INFO)
    
    # Example minimal Solidity contract to test with
    sample_solidity = '''
    pragma solidity ^0.8.0;
    
    contract SimpleStorage {
        uint256 storedData;
        
        function set(uint256 x) public {
            storedData = x;
        }
        
        function get() public view returns (uint256) {
            return storedData;
        }
    }
    '''
    
    logger.info("Sending sample contract to Groq for analysis...")
    
    # To run this successfully, ensure you prefix the command with:
    # GROQ_API_KEY=your_key_here python groq_ai_analyzer.py
    analysis = analyze_solidity_with_groq(sample_solidity)
    
    if analysis:
        print("\n--- AI Analysis ---\n")
        print(analysis)
    else:
        print("\nFailed to retrieve analysis from Groq.")
