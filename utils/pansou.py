import asyncio
import logging
import os
from datetime import datetime, timedelta

import aiohttp

from config.config import CLOUD_TYPE_MAP

logger = logging.getLogger(__name__)

class PanSou(object):
    # 会话最大存活时间：1小时
    _SESSION_MAX_AGE = timedelta(hours=1)

    def __init__(self):
        self.host = os.getenv('PANSOU_HOST')
        self._session = None
        self._session_created_at = None
        self.cloud_type_map = CLOUD_TYPE_MAP

    async def _get_session(self):
        """获取或创建会话，支持会话过期自动重建"""
        # 检查会话是否需要重新创建
        need_new_session = (
            self._session is None or
            self._session_created_at is None or
            self._session.closed or
            datetime.now() - self._session_created_at > self._SESSION_MAX_AGE
        )

        if need_new_session:
            # 关闭旧会话（如果存在）
            if self._session and not self._session.closed:
                try:
                    await self._session.close()
                except Exception as e:
                    logger.warning(f"关闭旧会话时出错: {e}")

            # 创建新会话，添加超时和连接器配置
            timeout = aiohttp.ClientTimeout(
                total=30,        # 总超时 30 秒
                connect=10,      # 连接超时 10 秒
                sock_read=20     # 读取超时 20 秒
            )

            connector = aiohttp.TCPConnector(
                limit=100,           # 最大连接数
                limit_per_host=30,   # 每个主机的最大连接数
                ttl_dns_cache=300,   # DNS 缓存 5 分钟
                force_close=False,   # 使用 HTTP keep-alive
                enable_cleanup_closed=True  # 清理关闭的连接
            )

            self._session = aiohttp.ClientSession(
                timeout=timeout,
                connector=connector
            )
            self._session_created_at = datetime.now()
            logger.debug("已创建新的 HTTP 会话")

        return self._session

    async def close(self):
        """关闭会话并清理资源"""
        if self._session and not self._session.closed:
            try:
                await self._session.close()
                # 等待连接器完全关闭
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"关闭会话时出错: {e}")
            finally:
                self._session = None
                self._session_created_at = None

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