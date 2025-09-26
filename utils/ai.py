import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

def get_ai_config_from_db(session=None, user_id: int = None) -> Optional[dict]:
    """从数据库获取AI配置（适配新的表结构）"""
    if not session or not user_id:
        return None

    try:
        from api.ai_config import get_user_ai_config
        return get_user_ai_config(session, user_id)
    except Exception as e:
        logger.error(f"从数据库获取AI配置失败: {e}")
        return None

def get_ai_config(session=None, user_id: int = None, provider: str = None) -> dict:
    """获取AI配置（只读数据库配置，不再使用默认配置）"""
    config = None

    # 从数据库获取配置
    if session and user_id:
        db_config = get_ai_config_from_db(session, user_id)
        if db_config:
            # 如果指定了提供商，使用该提供商的配置
            if provider:
                if provider in db_config and db_config[provider].get('api_key'):
                    config = db_config[provider].copy()
                    config['provider'] = provider
            else:
                # 使用默认提供商
                default_provider = db_config.get('default_provider', 'kimi')
                if default_provider in db_config and db_config[default_provider].get('api_key'):
                    config = db_config[default_provider].copy()
                    config['provider'] = default_provider

    # 如果没有配置，返回空配置
    if not config:
        config = {
            'provider': provider or 'kimi',
            'api_key': None,
            'host': '',
            'model': '',
            'is_default': False
        }

    return config

async def openapi_chat(role: str, prompt: str, host: str = None, api_key: str = None, model: str = None, session=None, user_id: int = None):
    """
    发送AI聊天请求

    Args:
        role: 系统角色提示
        prompt: 用户提示
        host: API主机地址（可选，如果不提供则从配置中获取）
        api_key: API密钥（可选，如果不提供则从配置中获取）
        model: 模型名称（可选，如果不提供则从配置中获取）
        session: 数据库会话（可选，用于获取用户配置）
        user_id: 用户ID（可选，用于获取用户配置）
    """
    # 如果缺少必要参数，尝试从配置中获取
    if not host or not api_key or not model:
        config = get_ai_config(session, user_id)
        if not config or not config.get('api_key'):
            logger.error("AI配置缺失或API密钥未设置")
            return None

        host = host or config.get('host')
        api_key = api_key or config.get('api_key')
        model = model or config.get('model')

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
        "Authorization": f"Bearer {api_key}",
    }
    try:
        resp = requests.post(url=host, headers=headers, json=data, timeout=90)
        if not resp.ok:
            logger.error(f'[{resp.status_code}] ai chat error: {resp.text}')
            print(prompt)
            return None
        json_data = resp.json()
        result = json_data['choices'][0]['message']['content']
        return result

    except Exception as e:
        logger.error(f'ai chat error: {e}')
        return None
