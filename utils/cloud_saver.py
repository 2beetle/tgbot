from collections import defaultdict
from html import escape

import requests

from config.config import CLOUD_SAVER_HOST, CLOUD_SAVER_USERNAME, CLOUD_SAVER_PASSWORD


class CloudSaver:
    def __init__(self):
        self.username = CLOUD_SAVER_USERNAME
        self.password = CLOUD_SAVER_PASSWORD
        self.host = CLOUD_SAVER_HOST
        self.cloud_type_map = {
            "QUARK": "夸克网盘",
            "ALIPAN": "阿里云盘",
            "ALIYUN": "阿里云盘",
            "123PAN": "123网盘",
            "PAN123": "123网盘",
            "XUNLEI": "迅雷云盘",
            "WETRANSFER": "WeTransfer",
            "BAIDUPAN": "百度网盘",
            "UC": "UC网盘",
        }

    def get(self, url, params=None):
        token = requests.post(
            f'{self.host}/api/user/login',
            json={'username': self.username, 'password': self.password}
        ).json().get('data').get('token')
        return requests.get(
            url=f'{self.host}/{url}',
            params=params,
            headers={'Authorization': f'Bearer {token}'}
        )

    async def search(self, search_content):
        return self.get('/api/search', {'keyword': search_content})

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

    async def format_links_by_cloud_type(self, data, links_valid: dict):
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
            for i in range(0, len(resources), 25):
                lines = [f"☁️ <b>{self.cloud_type_map.get(cloud_type)}</b>（cs资源）"]
                chunk_data = resources[i:i + 25]
                for resource in chunk_data:
                    lines.append(f'🔗 <a href="{resource[1]}">{resource[0]}</a> （{links_valid.get(resource[1], '状态未知')}）')

                result.append('\n'.join(lines))
        return result