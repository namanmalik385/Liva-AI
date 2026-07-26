import os
import json
import re
import requests
from dotenv import load_dotenv
from services.prompt_builder import build_full_llm_request
from services.report_analysis_prompt import build_report_analysis_request

load_dotenv()  # reads .env file and loads variables into environment

API_KEY = os.environ.get("FIREWORKS_API_KEY")
API_URL = "https://api.fireworks.ai/inference/v1/chat/completions"
MODEL = "accounts/fireworks/models/gpt-oss-120b"

def _clean_json_response(raw_text):
    """Strips markdown fences if the model added them despite instructions."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned


def get_liver_analysis(user_id):
    if not API_KEY:
        return {"error": "FIREWORKS_API_KEY not set in environment"}

    prompt = build_full_llm_request(user_id)
    if prompt is None:
        return {"error": "User not found or no data available"}

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
        "model": MODEL,
        "max_tokens": 2048,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": "You are a medical analysis assistant. Provide responses in valid JSON format only."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        print(f"API response status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return {"error": f"API request failed: {e}"}

    try:
        response_json = response.json()
        print(f"API response: {response_json}")
        raw_content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        print(f"Unexpected API response structure: {e}")
        print(f"Response was: {response.text}")
        return {"error": "Unexpected API response structure", "details": str(e)}

    cleaned = _clean_json_response(raw_content)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM JSON: {e}")
        print(f"Raw response was: {raw_content}")
        return {"error": "Failed to parse LLM response", "raw": raw_content}


def get_report_analysis(analysis_context):

    if not API_KEY:
        return {"error": "FIREWORKS_API_KEY not set"}

    prompt = build_report_analysis_request(analysis_context)

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_KEY}"
    }

    payload = {
        "model": MODEL,
        "max_tokens": 2048,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": "You are a medical analysis assistant. Provide responses in valid JSON format only."},
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post(API_URL, headers=headers, data=json.dumps(payload), timeout=30)
        response.raise_for_status()
        print(f"API response status: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"API request failed: {e}")
        return {"error": f"API request failed: {e}"}

    try:
        response_json = response.json()
        raw_content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as e:
        print(f"Unexpected API response structure: {e}")
        print(f"Response was: {response.text}")
        return {"error": "Unexpected API response structure", "details": str(e)}

    cleaned = _clean_json_response(raw_content)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"Failed to parse LLM JSON: {e}")
        print(f"Raw response was: {raw_content}")
        return {
            "error": "Failed to parse LLM response",
            "raw": raw_content
        }
    


if __name__ == "__main__":
    result = get_liver_analysis(user_id=1)
    print(json.dumps(result, indent=2))
