import requests
import json

def check_thinking():
    url = "http://localhost:11434/api/generate"
    model = "qwen3:0.6b"
    prompt = "Why is the sky blue? Please think step by step."
    
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    print(f"Querying Ollama model '{model}'...")
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        content = result.get("response", "")
        
        print("\n--- Raw Response Start ---")
        print(content)
        print("--- Raw Response End ---\n")
        
        if "<think>" in content:
            print("✅ Thinking block detected!")
        else:
            print("❌ No thinking block detected in the output.")
            
    except requests.exceptions.RequestException as e:
        print(f"Error querying Ollama: {e}")

if __name__ == "__main__":
    check_thinking()
