import asyncio
from collections import defaultdict
from datetime import datetime, timedelta
from html import escape

import aiohttp

from config.config import CLOUD_SAVER_HOST, CLOUD_SAVER_USERNAME, CLOUD_SAVER_PASSWORD, CLOUD_TYPE_MAP


class CloudSaver:
    # 会话最大存活时间：1小时
    _SESSION_MAX_AGE = timedelta(hours=1)

    def __init__(self):
        self.username = CLOUD_SAVER_USERNAME
        self.password = CLOUD_SAVER_PASSWORD
        self.host = CLOUD_SAVER_HOST
        self._session = None
        self._session_created_at = None
        self._token = None
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
                except Exception:
                    pass

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

        return self._session

    async def _get_token(self):
        """获取认证令牌，如果令牌过期则重新获取"""
        if self._token is None:
            session = await self._get_session()
            async with session.post(
                f'{self.host}/api/user/login',
                json={'username': self.username, 'password': self.password}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._token = data.get('data', {}).get('token')
        return self._token

    async def close(self):
        """关闭会话并清理资源"""
        if self._session and not self._session.closed:
            try:
                await self._session.close()
                await asyncio.sleep(0.1)
            except Exception:
                pass
            finally:
                self._session = None
                self._session_created_at = None
                self._token = None

    async def get(self, url, params=None):
        token = await self._get_token()
        session = await self._get_session()
        async with session.get(
            url=f'{self.host}/{url}',
            params=params,
            headers={'Authorization': f'Bearer {token}'}
        ) as resp:
            data = await resp.json()
            return data

    async def search(self, search_content):
        return await self.get('/api/search', {'keyword': search_content})

    async def format_links_by_channel(self, data):
        result = []

        for channel_data in data:
            channel_name = channel_data.get("channelInfo", {}).get("name", "未知频道")
            # 按网盘类型分组，每组存 (title, link) 列表
            cloudtype_links = defaultdict(list)

            for item in channel_data.get("list", []):
                title = item.get("title", "无标题")
                for link in item.get("cloudLinks", []):
                    url = link.get("link")
                    raw_type = link.get("cloudType", "").upper()
                    if url:
                        cloudtype_links[raw_type].append((title, url))

            if not cloudtype_links:
                continue

            lines = [f"📡 <b>{escape(channel_name)}</b>"]

            for raw_type, items in cloudtype_links.items():
                cloud_type_name = self.cloud_type_map.get(raw_type, raw_type)
                lines.append(f"\n🔸 <b>{cloud_type_name}</b>")
                for title, url in items:
                    lines.append(f'🔗 <a href="{escape(url)}">{escape(title)}</a>')

            result.append('\n'.join(lines))
        return result

    async def format_links_by_cloud_type(self, data, links_valid: dict, preferred_clouds=None):
        result = []
        # 按网盘类型分组，每组存 (title, link) 列表
        cloudtype_links = defaultdict(list)

        for channel_data in data:
            for item in channel_data.get("list", []):
                title = item.get("title", "无标题")
                for link in item.get("cloudLinks", []):
                    url = link.get("link")
                    raw_type = link.get("cloudType", "").upper()
                    if url:
                        cloudtype_links[raw_type].append((title, url))

        for cloud_type, resources in cloudtype_links.items():
            cloud_type_name = self.cloud_type_map.get(cloud_type)
            # 如果用户配置了常用云盘，跳过不在配置中的网盘类型
            if preferred_clouds is not None and cloud_type_name not in preferred_clouds:
                continue

            # 过滤掉无效状态的链接，只保留"有效"或"状态未知"的链接
            valid_resources = [
                resource for resource in resources
                if links_valid.get(resource[1], '状态未知') in ('有效', '状态未知')
            ]

            for i in range(0, len(valid_resources), 25):
                lines = [f"☁️ <b>{self.cloud_type_map.get(cloud_type)}</b>（cs资源）"]
                chunk_data = valid_resources[i:i + 25]
                for resource in chunk_data:
                    lines.append(f'🔗 <a href="{resource[1]}">{resource[0].replace('<', '[').replace('>', ']')}</a> （{links_valid.get(resource[1], '状态未知')}）')

                result.append('\n'.join(lines))
        return result