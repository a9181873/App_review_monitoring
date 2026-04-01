import config
import requests

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

def test():
    resp = requests.post(
        GEMINI_API_URL,
        params={"key": config.GEMINI_API_KEY},
        headers={"Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": "hello"}]}]},
        timeout=10,
    )
    print("Status:", resp.status_code)
    print("Response:", resp.text)

if __name__ == "__main__":
    test()
