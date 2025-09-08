import asyncio
import datetime
import json
import logging
import pprint
import re
from urllib.parse import urlparse, parse_qs

import pytz
import requests

from config.config import TIME_ZONE, AI_API_KEYS
from utils.ai import openapi_chat

logger = logging.getLogger(__name__)


class QuarkAutoDownload:
    def __init__(self, api_token):
        self.api_token = api_token

    async def data(self, host):
        resp = requests.get(
            f'{host}/data?token={self.api_token}'
        )
        if not resp.ok:
            logger.error(f'Failed to get data {host}, error: {resp.reason}')
        else:
            return resp.json().get('data')

    async def add_job(self, host, task_name, share_url, save_path, pattern, replace):
        resp = requests.post(
            f'{host}/api/add_task?token={self.api_token}',
            headers={
                'Content-Type': 'application/json',
            },
            json={
                'taskname': task_name,
                'shareurl': share_url,
                'savepath': save_path,
                'pattern': pattern,
                'replace': replace
            }
        )
        if not resp.ok:
            logger.error(f'Failed to add task {task_name}, error: {resp.text}')
        return resp

    async def update(self, host, data):
        resp = requests.post(
            f'{host}/update?token={self.api_token}',
            headers={
                'Content-Type': 'application/json',
            },
            json=data
        )
        if not resp.ok:
            logger.error(f'Failed to update data {host}, error: {resp.text}')
        else:
            logger.info(f'Success to update data {host}, data: {data}')
            return resp.json()

    async def get_share_detail(self, host, data):
        resp = requests.post(
            f'{host}/get_share_detail?token={self.api_token}',
            headers={
                'Content-Type': 'application/json',
            },
            json=data
        )
        if not resp.ok:
            logger.error(f'Failed to get_share_detail {host}, error: {resp.text}')
        else:
            logger.info(f'Success to get_share_detail {host}, data: {data}')
            return resp.json()

    async def extract_quark_share_info(self, url: str):
        match = re.search(r'https://pan\.quark\.cn/s/([a-zA-Z0-9]+)', url)
        quark_id = match.group(1) if match else None

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        pwd = query_params.get('pwd', [""])[0]

        return quark_id, pwd

    async def get_quark_id_stoken_pdir_fid(self, url):
        quark_id, pass_code = await self.extract_quark_share_info(url)
        match = re.search(r'/([^/]+)-[^/]*$', url)
        if match:
            pdir_fid = match.group(1)
        else:
            pdir_fid = None

        if pdir_fid is None:
            if url.endswith('/'):
                pdir_fid = url.split('/')[-2]
            else:
                pdir_fid = url.split('/')[-1]
        stoken_resp = requests.post("https://drive-h.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc",
                             headers={
                                 'Content-Type': 'application/json',
                             },
                             json={
                                 "pwd_id": quark_id,
                                 "passcode": pass_code,
                                 "support_visit_limit_private_share": True
                             })
        if not stoken_resp.ok:
            logger.error(f'Failed to get quark stoken {url}, error: {stoken_resp.text}')
            return quark_id, None, pdir_fid
        stoken = stoken_resp.json()['data']['stoken']
        return quark_id, stoken, pdir_fid

    async def get_quark_dir_detail(self, quark_id, stoken, pdir_fid, include_dir=True):
        sub_resp = requests.get(f'https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail',
                                params={
                                    'pr': 'ucpro',
                                    'fr': 'pc',
                                    'uc_param_str': '',
                                    '_size': 40,
                                    'pdir_fid': pdir_fid,
                                    'pwd_id': quark_id,
                                    'stoken': stoken,
                                    'ver': 2
                                })
        if not sub_resp.ok:
            logger.error(f'Failed to get quark sub {quark_id}/{pdir_fid}, error: {sub_resp.json()}')
            return []
        if include_dir:
            return sub_resp.json()['data']['list']
        else:
            return [file for file in sub_resp.json()['data']['list'] if not file.get('dir')]

    async def get_quark_dir_structure(self, quark_id, stoken, pdir_fid):
        result = list()
        file_list = await self.get_quark_dir_detail(quark_id=quark_id, stoken=stoken, pdir_fid=pdir_fid)
        for file in file_list:
            if file['dir'] is True:
                include_items = await self.get_quark_dir_structure(quark_id=quark_id, stoken=stoken, pdir_fid=file['fid'])
            else:
                include_items = None
            result.append({
                "dir": file['dir'],
                "file_name": file['file_name'],
                "fid": file['fid'],
                "include_items_count": file.get('include_items_count', None),
                "include_items": include_items,
                "last_update_at": datetime.datetime.fromtimestamp(int(file['last_update_at'])/1000,
                                                                  tz=datetime.UTC
                                                                  ).astimezone(pytz.timezone(TIME_ZONE)),
            })
        return result

    async def get_fid_files(self, url: str):
        async def recursive_get_fid_files(fid, file_name, quark_id, stoken, fid_files):
            dir_files = list()
            files = await self.get_quark_dir_detail(quark_id=quark_id, stoken=stoken, pdir_fid=fid)
            for file in files:
                if file['dir'] is True:
                    await recursive_get_fid_files(file['fid'], file['file_name'], quark_id, stoken, fid_files)
                else:
                    dir_files.append({
                        "file_name": file['file_name'],
                        "last_update_at": datetime.datetime.fromtimestamp(int(file['last_update_at']) / 1000,
                                                                          tz=datetime.UTC
                                                                          ).astimezone(pytz.timezone(TIME_ZONE)),
                    })
            fid_files[f"{file_name}__{fid}"] = dir_files
            return dir_files

        logger.info(f"Getting fid files for {url}")
        quark_id, stoken, pdir_fid = await self.get_quark_id_stoken_pdir_fid(url)
        if stoken is None:
            return None
        fid_files = dict()
        await recursive_get_fid_files(0, "root", quark_id, stoken, fid_files)
        return fid_files

    async def build_unicode_tree_paragraph(self, folder_name: str, files: list) -> str:
        lines = [f"{folder_name}"]
        for i, file in enumerate(sorted(files, key=lambda x: x['file_name'])):
            is_last = i == len(files) - 1
            prefix = '└──' if is_last else '├──'
            lines.append(f"{prefix} {file['file_name']}")
        return '\n'.join(lines)

    async def get_tree_paragraphs(self, fid_files: dict) -> list[str]:
        result = []
        for key, files in fid_files.items():
            if key == 'root__0':
                continue
            paragraph = await self.build_unicode_tree_paragraph(key, files)
            result.append(paragraph)
        return result

    async def ai_generate_params(self, url: str) -> dict:
        quark_id, stoken, pdir_fid = await self.get_quark_id_stoken_pdir_fid(url=url)
        dir_details = await self.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False)
        files = [
            {
               "file_name": dir_detail['file_name'],
               "video_max_resolution": dir_detail['video_max_resolution'],
            }
            for dir_detail in dir_details if "video_max_resolution" in dir_detail
        ]
        prompt = rf"""
1. 请从以下文件列表中根据文件的file_name编写正则表达式只提取video_max_resolution为4k的文件并且还需要提取 file_name 中的季数和集数和文件后缀，如果file_name中没有季数的信息，则只需要提取集数
{files}
2. 根据编写的正则匹配式匹配到video_max_resolution为4k的文件的file_name并提取到 file_name 中的季数和集数和文件后缀后，用于生成新 file_name，如果前面的正则没有提取到季数的信息，则默认为第一季

以下是一些示例，请你按照示例的规则进行生成：
| pattern                                   | replace                    | 效果                                                                 |
|-------------------------------------------|-----------------------------|----------------------------------------------------------------------|
| `.*`                                      |                             | 无脑转存所有文件，不整理                                              |
| `\.mp4$`                                  |                             | 转存所有 `.mp4` 后缀的文件                                           |
| `^【电影TT】花好月圆(\d+)\.(mp4|mkv)`     | `\1.\2`                     | `【电影TT】花好月圆01.mp4 → 01.mp4`<br>`【电影TT】花好月圆02.mkv → 02.mkv` |
| `^(\d+)\.mp4`                             | `S02E\1.mp4`                | `01.mp4 → S02E01.mp4`<br>`02.mp4 → S02E02.mp4`                        |
| `^(\d+)\.mp4`                             | `TASKNAME.S02E\1.mp4`     | `01.mp4 → 任务名.S02E01.mp4`                                         |
| `^S(\d+).*EP(\d+).*.mp4`                             | `S\1E\2.mp4`     | `S02saxEP01.mp4 → 任务名.S02E01.mp4`                                         |

必须执行的注意事项：
1. 必须以示例的规则生成 pattern 和 replace
2. 在正则替换（replace）中，请使用 传统的 Python / sed / rename 工具风格，例如 \1、\\1 或 $1，**不要使用 ${{1:-01}}、{{group}}、{{1}} 等语法。
3. pattern中不要使用分组命名，如(?<episode>\d+)\
4. 回答中只需返回JSON格式的结果无需返回其他说明信息，包含两个字段：
    1. pattern: 能够匹配到video_max_resolution为4k的文件的file_name并且还能够提取 file_name 中的季数和集数的正则匹配式
    2. replace: 用于生成新 file_name，如果前面的正则没有提取到季数的信息，则默认为第一季
"""
        ai_analysis = await openapi_chat(
            role="你是一个编写正则表达式的专家，善于从元素列表中通过编写正则提取到想要的元素",
            prompt=prompt,
            host=AI_API_KEYS.get('kimi').get('host'),
            api_key=AI_API_KEYS.get('kimi').get('api_key'),
            model=AI_API_KEYS.get('kimi').get('model'),
        )

        # 清理可能的非JSON内容
        ai_analysis = ai_analysis.strip()
        if ai_analysis.startswith("```json"):
            ai_analysis = ai_analysis[7:]
        if ai_analysis.endswith("```"):
            ai_analysis = ai_analysis[:-3]

        generate_params = json.loads(ai_analysis)

        generate_params['replace'] = generate_params['replace'].replace("$", "\\")

        return generate_params

    async def run_script_now(self, host, task_list):
        resp = requests.post(
            f'{host}/run_script_now?token={self.api_token}',
            json={
                    "tasklist": task_list
                }
        )
        if not resp.ok:
            logger.error(f'Failed to run script {host}, error: {resp.reason}')
        else:
            return resp.text



if __name__ == '__main__':
    qas = QuarkAutoDownload(api_token='')
    # result = asyncio.run(qas.get_quark_id_stoken_pdir_fid('https://pan.qualk.cn/s/a6b7fdfb9a09'))
    url = "https://pan.qualk.cn/s/a6b7fdfb9a09"
    headers = {
        "Host": "pan.qualk.cn",
        "Sec-Fetch-Site": "none",
        "Connection": "keep-alive",
        "Sec-Fetch-Mode": "navigate",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/22F76 Safari/604.1",
        "Accept-Language": "zh-CN,zh-Hans;q=0.9",
        "Sec-Fetch-Dest": "document",
        "Accept-Encoding": "gzip, deflate, br"
    }
    resp = requests.get(url, headers=headers)
    print(resp.json())
    # # pprint.pprint(qas.data(host='https://quark-auto-save.beocean.net'))
    # url = 'https://pan.quark.cn/s/509d0c3f6b4e#/list/share/'
    # url = 'https://pan.quark.cn/s/cd43e673582a?pwd=QtMq#/list/share'
    # url = 'https://pan.quark.cn/s/3fa9436351de#/list/share/bcd673aa16d6485cb3780489fb5c7c99-%E3%80%90%E5%91%A8%E5%85%AD%E3%80%91%E5%87%A1%E4%BA%BA.%E4%BF%AE%E4%BB%99.%E4%BC%A0/'
    # url = 'https://pan.quark.cn/s/5cf6f43d4da5#/list/share/c87624b1a407448eb5b48fb9bd345bdc-D 罗大路'
    # # url = 'https://pan.quark.cn/s/e333817273ca#/list/share/c2149426584b458d97795d1902838507'
    # # url = 'https://pan.quark.cn/s/e333817273ca#/list/share'
    # params = asyncio.run(qas.ai_generate_params(url))
    # pprint.pprint(params)