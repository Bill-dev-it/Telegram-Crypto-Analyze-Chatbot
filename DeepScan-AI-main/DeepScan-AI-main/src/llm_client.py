import requests
import json
from .config import GROQ_API_KEY, GEMINI_API_KEY, GROQ_MODEL, GEMINI_MODEL

class LLMClient:
    def __init__(self):
        self.groq_key = GROQ_API_KEY
        self.gemini_key = GEMINI_API_KEY

    def generate(self, prompt, model_preference="groq"):
        """
        Generates text using the preferred model, falling back if necessary.
        """
        if model_preference == "groq":
            try:
                return self._call_groq(prompt)
            except Exception as e:
                print(f"Groq failed: {e}. Falling back to Gemini.")
                return self._call_gemini(prompt)
        
        return self._call_gemini(prompt)

    def _call_groq(self, prompt):
        if not self.groq_key:
            raise ValueError("Groq API Key missing")
            
        url = "https://api.groq.com/openai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.groq_key}",
            "Content-Type": "application/json"
        }
        data = {
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": "You are DeepScan AI."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        
        response = requests.post(url, headers=headers, json=data)
        if not response.ok:
            with open("web/backend/groq_error.txt", "w") as f:
                f.write(f"Status: {response.status_code}\n")
                f.write(response.text)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def _call_gemini(self, prompt):
        if not self.gemini_key:
            raise ValueError("Gemini API Key missing")
            
        # Using Gemini 1.5 Flash via REST API
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={self.gemini_key}"
        headers = { "Content-Type": "application/json" }
        data = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        
        try:
            return result["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return "Gemini returned no content."

# Singleton instance
llm_client = LLMClient()
