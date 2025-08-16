import json
import logging

import requests

logger = logging.getLogger(__name__)

async def openapi_chat(role: str, prompt: str, host: str, api_key: str, model: str):
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": role},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "top_p": 1,
        "stream": False,
        "response_format": {'type': 'json_object'}
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"{api_key}",
    }
    try:
        resp = requests.post(url=host, headers=headers, json=data, timeout=90)
        if not resp.ok:
            logger.error(f'[{resp.status_code}] ai chat error: {resp.text}')
            print(prompt)
            return
        json_data = resp.json()
        result = json_data['choices'][0]['message']['content']
        return result

    except Exception as e:
        logger.error(f'ai chat error: {e}')
