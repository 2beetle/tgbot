import logging
import os

import requests

logger = logging.getLogger(__name__)

class PanSou(object):
    def __init__(self):
        self.host = os.getenv('PANSOU_HOST')
        self.cloud_type_map = {
            "quark": "夸克网盘",
            "ALIPAN": "阿里云盘",
            "ALIYUN": "阿里云盘",
            "123PAN": "123网盘",
            "PAN123": "123网盘",
            "XUNLEI": "迅雷云盘",
            "WETRANSFER": "WeTransfer",
            "baidu": "百度网盘",
            "UC": "UC网盘",
        }

    async def search(self, keyword):
        resp = requests.post(
            self.host + "/api/search",
            json={
              "kw": keyword,
              "refresh": False,
              "res": "merge",
              "src": "all",
              "cloud_types": ["baidu", "quark"]
            }
        )
        if not resp.ok:
            logger.error(f"PANSOU search error: {resp.text}")
        else:
            return resp.json()

    async def format_links_by_cloud_type(self, result: dict, links_valid: dict):
        messages = list()
        for cloud_type, resources in result.get('merged_by_type').items():
            for i in range(0, len(resources), 25):
                lines = [f"☁️ <b>{self.cloud_type_map.get(cloud_type)}</b>（pansou资源）"]
                chunk_data = resources[i:i + 25]
                for resource in chunk_data:
                    lines.append(f'🔗 <a href="{resource.get('url')}">{resource.get('note')}（{links_valid.get(resource[1], '状态未知')}）</a>')

                messages.append('\n'.join(lines))
        return messages


if __name__ == '__main__':
    p = PanSou()
    print(p.format_links_by_cloud_type(p.search(keyword="").get('data')))