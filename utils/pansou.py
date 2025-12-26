import logging
import os

import aiohttp

from config.config import CLOUD_TYPE_MAP

logger = logging.getLogger(__name__)

class PanSou(object):
    def __init__(self):
        self.host = os.getenv('PANSOU_HOST')
        self._session = None
        self.cloud_type_map = CLOUD_TYPE_MAP

    async def _get_session(self):
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()
            self._session = None

    async def search(self, keyword):
        session = await self._get_session()
        async with session.post(
            self.host + "/api/search",
            json={
              "kw": keyword,
              "refresh": False,
              "res": "merge",
              "src": "all",
              "cloud_types": ["baidu", "quark"]
            }
        ) as resp:
            if resp.status != 200:
                error_text = await resp.text()
                logger.error(f"PANSOU search error: {error_text}")
                return None
            return await resp.json()

    async def format_links_by_cloud_type(self, result: dict, links_valid: dict, preferred_clouds=None):
        messages = list()
        for cloud_type, resources in result.get('merged_by_type').items():
            cloud_type_name = self.cloud_type_map.get(cloud_type)
            # 如果用户配置了常用云盘，跳过不在配置中的网盘类型
            if preferred_clouds is not None and cloud_type_name not in preferred_clouds:
                continue
            # 过滤掉无效状态的链接，只保留"有效"或"状态未知"的链接
            valid_resources = [
                resource for resource in resources
                if links_valid.get(resource.get('url'), '状态未知') in ('有效', '状态未知')
            ]

            for i in range(0, len(valid_resources), 25):
                lines = [f"☁️ <b>{self.cloud_type_map.get(cloud_type)}</b>（pansou资源）"]
                chunk_data = valid_resources[i:i + 25]
                for resource in chunk_data:
                    lines.append(f'🔗 <a href="{resource.get('url')}">{resource.get('note').replace('<', '[').replace('>', ']')}</a> （{links_valid.get(resource.get('url'), '状态未知')}）')

                messages.append('\n'.join(lines))
        return messages


if __name__ == '__main__':
    p = PanSou()
    print(p.format_links_by_cloud_type(p.search(keyword="").get('data')))