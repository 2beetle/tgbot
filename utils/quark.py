import asyncio
import logging
import re
from urllib.parse import urlparse, parse_qs

import aiohttp
import requests

logger = logging.getLogger(__name__)

class Quark:
    def __init__(self):
        pass

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

        if pdir_fid == 'share' or pdir_fid == quark_id:
            pdir_fid = 0

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
            return quark_id, None, pdir_fid, stoken_resp.json().get('message', '状态未知')
        stoken = stoken_resp.json()['data']['stoken']
        return quark_id, stoken, pdir_fid, None

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

    async def check_link(self, session: aiohttp.ClientSession, link: str):
        quark_id, stoken, pdir_fid, error = await self.get_quark_id_stoken_pdir_fid(url=link)
        if error is not None:
            return link, error
        async with session.get(
                "https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail",
                params={
                    "pr": "ucpro",
                    "fr": "pc",
                    "uc_param_str": "",
                    "_size": 40,
                    "pdir_fid": pdir_fid,
                    "pwd_id": quark_id,
                    "stoken": stoken,
                    "ver": 2,
                },
        ) as resp:
            if resp.ok:
                return link, "有效"
            else:
                logger.error(f"link {link} (quark_id: {quark_id}, stoken: {stoken}, pdir_fid: {pdir_fid}) check fail: {await resp.text()}")
                data = await resp.json()
                return link, data.get("message")

    async def links_valid(self, links: list):
        result = dict()
        async with aiohttp.ClientSession() as session:
            tasks = [self.check_link(session, link) for link in links]
            results = await asyncio.gather(*tasks)
            result.update(dict(results))
        return result


if __name__ == '__main__':
    quark = Quark()
    result = asyncio.run(quark.links_valid(['https://pan.quark.cn/s/30be6ed6692c#/list/share', 'https://pan.quark.cn/s/186d42868348#/list/share', 'https://pan.quark.cn/s/3b84769ebcbf']))
    print(result)