import re
from .llm_client import llm_client
from .config import SYSTEM_PROMPT
from .auditor_engine import auditor_engine

class DeepScanAgent:
    def __init__(self):
        self.llm = llm_client
        self.auditor = auditor_engine

    def process_query(self, query: str, model_preference: str = "groq"):
        print(f"DEBUG: Processing Query -> {query} (Model: {model_preference})")
        try:
            # 1. Intent Detection (Simple Rule-based for now)
            if self._is_contract_scan(query):
                print("DEBUG: Intent -> Contract Scan")
                return self._handle_contract_scan(query, model_preference)
            
            if "market" in query.lower() or "bitcoin" in query.lower():
                print("DEBUG: Intent -> Market Analysis")
                return self._handle_market_analysis(query, model_preference)

            # Default: General Chat
            print("DEBUG: Intent -> General Chat")
            return self._handle_general_chat(query, model_preference)
        except Exception as e:
            print(f"DEBUG: Agent Error -> {e}")
            import traceback
            traceback.print_exc()
            raise e

    def _is_contract_scan(self, query):
        is_address = re.match(r"^0x[a-fA-F0-9]{40}$", query.strip())
        is_code = "pragma solidity" in query or "contract " in query or "interface " in query
        return is_address or is_code

    def _clean_text(self, text):
        """Removes markdown symbols like *, #, `, etc. to return plain text."""
        if not text:
            return ""
        # Remove bold/italic markers (*, _)
        text = re.sub(r'[\*_`~]', '', text)
        # Remove headers (#)
        text = re.sub(r'#+', '', text)
        # Remove links [text](url) -> text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        return text.strip()

    def _handle_contract_scan(self, query, model_preference):
        try:
            result = self.auditor.analyze_contract(query, model_preference=model_preference)
        except Exception as e:
            result = {"error": f"Error during contract scan: {str(e)}"}
        
        return result

    def _handle_market_analysis(self, query, model_preference):
        try:
            prompt = f"{SYSTEM_PROMPT}\nUser Question: {query}\nProvide a market analysis based on your knowledge base."
            response = self.llm.generate(prompt, model_preference=model_preference) # Groq is faster
            message = self._clean_text(response)
        except Exception as e:
            message = f"Error generating analysis with {model_preference}: {str(e)}"
        
        return {
            "type": "MARKET_ANALYSIS",
            "message": message
        }

    def _handle_general_chat(self, query, model_preference):
        try:
            prompt = f"{SYSTEM_PROMPT}\nUser Question: {query}"
            response = self.llm.generate(prompt, model_preference=model_preference) # Prefer Groq (Llama 3)
            message = self._clean_text(response)
        except Exception as e:
            message = f"Error generating response with {model_preference}: {str(e)}"
        
        return {
            "type": "CHAT",
            "message": message
        }

# Singleton
agent = DeepScanAgent()
