import json
import re
from .llm_client import llm_client
from .config import AUDIT_SYSTEM_PROMPT

class AuditorEngine:
    def __init__(self):
        self.llm = llm_client

    def _get_insufficient_data_response(self) -> dict:
        """Returns a deterministic response when only an address is provided without code."""
        return {
            "honeypot": { "detected": False, "confidence": 0.0, "evidence": "insufficient_data" },
            "unlimited_mint": { "detected": False, "confidence": 0.0, "evidence": "insufficient_data" },
            "pause_trading": { "detected": False, "confidence": 0.0, "evidence": "insufficient_data" },
            "owner_abuse": { "detected": False, "confidence": 0.0, "evidence": "insufficient_data" },
            "hidden_tax_modification": { "detected": False, "confidence": 0.0, "evidence": "insufficient_data" },
            "total_risk_score": 0,
            "normalized_risk_score": 0,
            "overall_risk_level": "LOW",
            "warning": "insufficient_data: Only contract address provided. Please provide source code for a full audit or integrate with a data provider."
        }

    def _extract_json(self, text: str) -> str:
        """Attempts to extract a JSON block from the LLM's raw text response."""
        # Find the first '{' and the last '}'
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end > start:
            return text[start:end+1]
        return text

    def analyze_contract(self, input_text: str, model_preference: str = "groq") -> dict:
        """
        Analyzes the given input. If it's just an address, returns insufficient data.
        If it contains Solidity code, runs the audit engine prompt.
        """
        # Simple heuristic to distinguish between a bare address and actual code
        is_only_address = re.match(r"^0x[a-fA-F0-9]{40}$", input_text.strip())
        
        if is_only_address:
            return self._get_insufficient_data_response()

        # Input contains code, run the audit
        prompt = f"{AUDIT_SYSTEM_PROMPT}\n\nUser provided code to audit:\n{input_text}"
        
        try:
            raw_response = self.llm.generate(prompt, model_preference=model_preference)
            json_str = self._extract_json(raw_response)
            
            # Additional cleanup in case the LLM returned markdown code blocks
            json_str = json_str.strip()
            if json_str.startswith("```json"):
                json_str = json_str[7:]
            if json_str.startswith("```"):
                json_str = json_str[3:]
            if json_str.endswith("```"):
                json_str = json_str[:-3]
                
            parsed_result = json.loads(json_str)
            return parsed_result
        except json.JSONDecodeError as e:
            print(f"DEBUG: Failed to parse JSON from LLM: {str(e)}")
            print(f"Raw Output: {raw_response}")
            # Fallback error response
            return {
                "error": "Failed to parse LLM output as JSON",
                "raw_output": raw_response
            }
        except Exception as e:
            print(f"DEBUG: Audit Engine Error -> {e}")
            return {
                "error": f"Internal execution error: {str(e)}"
            }

# Singleton instance
auditor_engine = AuditorEngine()
