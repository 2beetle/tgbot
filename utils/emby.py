import asyncio
import logging
import pprint
from datetime import datetime, timedelta

import aiohttp

logger = logging.getLogger(__name__)

class Emby:
    # 会话最大存活时间：1小时
    _SESSION_MAX_AGE = timedelta(hours=1)

    def __init__(self, host, token):
        self.host = host
        self.token = token
        self._session = None
        self._session_created_at = None

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
            logger.debug("已创建新的 Emby HTTP 会话")

        return self._session

    async def close(self):
        """关闭会话并清理资源"""
        if self._session and not self._session.closed:
            try:
                await self._session.close()
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"关闭会话时出错: {e}")
            finally:
                self._session = None
                self._session_created_at = None

    async def get_access_token(self, username, password):
        user_id = await self.get_id_by_username(username)
        authentication_data = await self.authenticate_by_id_pwd(user_id, password)
        access_token = authentication_data['AccessToken']
        return access_token

    async def list_resource(self, resource_name):
        async with await self._get_session() as session:
            async with session.get(
                f"{self.host}/emby/Items",
                params={
                    'Recursive': True,
                    'SearchTerm': resource_name,
                    'IncludeItemTypes': "Series",
                    'EnableImages': True,
                    'api_key': self.token,
                }
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    logger.error(f"Emby.list_resource: {error_text}")
                    return None

    async def get_image_url_by_item_id(self, item_id):
        return f"{self.host}/emby/Items/{item_id}/Images/Primary/0?api_key={self.token}"

    async def get_remote_image_url_by_item_id(self, item_id):
        async with await self._get_session() as session:
            async with session.get(
                f"{self.host}/emby/Items/{item_id}/RemoteImages",
                params={
                    'api_key': self.token,
                    'Type': 'Primary',
                }
            ) as resp:
                data = await resp.json()
                images = data['Images']
                return [img.get('Url') for img in images if img['ProviderName'] == 'TheMovieDb'][0]

    async def get_admin_user_id(self):
        async with await self._get_session() as session:
            async with session.get(
                f"{self.host}/emby/Users/Query",
                params={
                    'api_key': self.token,
                }
            ) as resp:
                data = await resp.json()
                for user in data['Items']:
                    if user['Policy']['IsAdministrator']:
                        return user['Id']
                return None

    async def get_metadata_by_user_id_item_id(self, user_id, item_id):
        async with await self._get_session() as session:
            async with session.get(
                f"{self.host}/emby/Users/{user_id}/Items/{item_id}",
                params={
                    'api_key': self.token,
                }
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    logger.error(f"Emby.get_metadata_by_user_id_item_id: {error_text}")
                    return None

    async def refresh_library(self, item_id: int):
        async with await self._get_session() as session:
            async with session.post(
                f"{self.host}/emby/Items/{item_id}/Refresh",
                params={
                    "Recursive": True,
                    "MetadataRefreshMode": "FullRefresh",
                    "ImageRefreshMode": "FullRefresh",
                    "ReplaceAllMetadata": True,
                    "ReplaceAllImages": True,
                    "api_key": self.token,
                }
            ) as resp:
                if resp.status == 200:
                    return True
                else:
                    error_text = await resp.text()
                    logger.error(f"Emby.refresh_library: {error_text}")
                    return None

    async def get_id_by_username(self, username):
        async with await self._get_session() as session:
            async with session.get(
                f"{self.host}/emby/Users/Query",
                params={
                    'api_key': self.token,
                }
            ) as resp:
                data = await resp.json()
                for user in data['Items']:
                    if user['Name'] == username:
                        return user['Id']
                return None

    async def authenticate_by_id_pwd(self, user_id, user_pwd):
        async with await self._get_session() as session:
            async with session.post(
                f"{self.host}/emby/Users/{user_id}/Authenticate",
                params={
                    'api_key': self.token,
                },
                json={
                    "Pw": user_pwd,
                }
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    logger.error(f"Emby.authenticate_by_id_pwd: {error_text}")
                    return None

    async def list_notification(self, access_token):
        async with await self._get_session() as session:
            async with session.get(
                f"{self.host}/emby/Notifications/Services/Configured",
                params={
                    "X-Emby-Token": access_token
                }
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    error_text = await resp.text()
                    logger.error(f"Emby.list_notification: {error_text}")
                    return None

    async def update_notification(self, access_token: str, notification_id: str, event_id: str, operation: str):
        notifications = await self.list_notification(access_token)
        notification = None
        for _ in notifications:
            if _['Id'] == notification_id:
                notification = _
                break
        if notification is None:
            logger.error(f"Notification {notification_id} not found")
            return None
        if operation == 'open':
            if event_id not in notification['EventIds']:
                notification['EventIds'].append(event_id)
        elif operation == 'close':
            if event_id in notification['EventIds']:
                notification['EventIds'].remove(event_id)
        async with await self._get_session() as session:
            async with session.post(
                f"{self.host}/emby/Notifications/Services/Configured",
                params={
                    "X-Emby-Token": self.token
                },
                json=notification
            ) as resp:
                if resp.status == 204:
                    return resp
                else:
                    error_text = await resp.text()
                    logger.error(f"Emby.update_notification: {error_text}")
                    return None


if __name__ == '__main__':
    emby = Emby(host='', token='')
    data = asyncio.run(emby.get_admin_user_id())
    pprint.pprint(data)
