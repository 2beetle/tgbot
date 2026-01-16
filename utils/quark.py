import asyncio
import logging
import re
from urllib.parse import urlparse, parse_qs

import aiohttp

logger = logging.getLogger(__name__)

class Quark:
    def __init__(self, cookies=None):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) quark-cloud-drive/3.14.2 Chrome/112.0.5615.165 Electron/24.1.3.8 Safari/537.36 Channel/pckk_other_ch"
        self.cookies = cookies
        self.headers = {
            "cookie": self.cookies,
            "content-type": "application/json",
            "user-agent": self.user_agent,
        }
    async def extract_quark_share_info(self, url: str):
        match = re.search(r'https://pan\.quark\.cn/s/([a-zA-Z0-9]+)', url)
        quark_id = match.group(1) if match else None

        parsed = urlparse(url)
        query_params = parse_qs(parsed.query)
        pwd = query_params.get('pwd', [""])[0]

        return quark_id, pwd

    async def get_quark_id_stoken_pdir_fid(self, url, session: aiohttp.ClientSession):
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

        async with session.post(
                "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc",
                headers={
                    'Content-Type': 'application/json',
                },
                json={
                    "pwd_id": quark_id,
                    "passcode": pass_code,
                    "support_visit_limit_private_share": True
                },
        ) as stoken_resp:
            json_data = await stoken_resp.json()
            if not stoken_resp.ok:
                logger.error(f'Failed to get quark stoken {url}, error: {await stoken_resp.text()}')
                return quark_id, None, pdir_fid, json_data.get('message', '状态未知')

            try:
                stoken = json_data['data']['stoken']
            except Exception as e:
                logger.error(f'Failed to get quark stoken {url}, error: {e}')
                return quark_id, None, pdir_fid, '状态未知'
            return quark_id, stoken, pdir_fid, None

    async def get_quark_dir_detail(self, quark_id, stoken, pdir_fid, include_dir=True, size=40):
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f'https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail',
                params={
                    'pr': 'ucpro',
                    'fr': 'pc',
                    'uc_param_str': '',
                    '_size': size,
                    'pdir_fid': pdir_fid,
                    'pwd_id': quark_id,
                    'stoken': stoken,
                    'ver': 2,
                    "_sort": "file_type:asc,updated_at:desc"
                }
            ) as sub_resp:
                data = await sub_resp.json()
                if not sub_resp.ok:
                    logger.error(f'Failed to get quark sub {quark_id}/{pdir_fid}, error: {data}')
                    return []
                if include_dir:
                    return data['data']['list']
                else:
                    return [file for file in data['data']['list'] if not file.get('dir')]

    async def check_link(self, session: aiohttp.ClientSession, link: str):
        quark_id, stoken, pdir_fid, error = await self.get_quark_id_stoken_pdir_fid(url=link, session=session)
        if error is not None:
            return link, error
        async with session.get(
                "https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail",
                params={
                    "pr": "ucpro",
                    "fr": "pc",
                    "uc_param_str": "",
                    "_size": 5,
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

    async def get_path_file_map(self, paths: list):
        files = []
        file_paths = paths[:50]
        while True:
            url = f"https://drive-pc.quark.cn/1/clouddrive/file/info/path_list"
            querystring = {"pr": "ucpro", "fr": "pc"}
            payload = {"file_path": file_paths, "namespace": "0"}
            async with aiohttp.ClientSession() as session:
                async with await session.post(url, params=querystring, json=payload, headers=self.headers) as resp:
                    response = await resp.json()
                    if response["code"] == 0:
                        files += response["data"]
                        file_paths = file_paths[50:]
                    else:
                        logger.error(f"获取目录ID：失败, {response['message']}")
                        break
                    if len(file_paths) == 0:
                        break
        return dict(zip(paths, files))

    async def get_path_pdir_fid(self, path):
        if path:
            path = re.sub(r"/+", "/", path)
            if path == "/":
                return {"fid": 0, "name": "", 'path': path}
            else:
                dir_names = path.split("/")
                if dir_names[0] == "":
                    dir_names.pop(0)
                path_fids = []
                current_path = ""
                for dir_name in dir_names:
                    current_path += "/" + dir_name
                    path_fids.append(current_path)
                if path_file_map := await self.get_path_file_map(path_fids):
                    paths = [
                        {"fid": file["fid"], "name": path.split("/")[-1], 'path': path}
                        for path, file in path_file_map
                    ]
                    return paths
                else:
                    return None
        else:
            logger.error(f'path {path} is empty')
            return None

    async def get_quark_clouddrive_files(self, pdir_fid, size=30):
        async def recursive_get_quark_clouddrive_files(pdir_fid, session, size, page=1, files=None):
            if files is None:
                files = []
            url = f"https://drive-pc.quark.cn/1/clouddrive/file/sort"
            querystring = {
                "pr": "ucpro",
                "fr": "pc",
                "uc_param_str": "",
                "pdir_fid": pdir_fid,
                "_page": page,
                "_size": size,
                "_fetch_total": "1",
                "_fetch_sub_dirs": "0",
                "_sort": "file_type:asc,updated_at:desc",
                "_fetch_full_path": 0,
                "fetch_all_file": 1,  # 跟随Web端，作用未知
                "fetch_risk_file_name": 1,  # 如无此参数，违规文件名会被变 ***
            }
            async with await session.get(url, params=querystring, headers=self.headers) as resp:
                response = await resp.json()
                if response["code"] != 0:
                    return []
                if response["data"]["list"]:
                    files.extend(response["data"]["list"])

                if len(files) >= response["metadata"]["_total"]:
                    return files
                else:
                    return await recursive_get_quark_clouddrive_files(pdir_fid, session, size, page+1, files)

        async with aiohttp.ClientSession() as session:
            result = await recursive_get_quark_clouddrive_files(pdir_fid, session, size, 1, [])

        if isinstance(result, list):
            return result
        else:
            return []


    async def delete_files(self, filelist: list):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f'https://drive-pc.quark.cn/1/clouddrive/file/delete?pr=ucpro&fr=pc&uc_param_str=',
                headers=self.headers,
                json={
                    "action_type": 2,
                    "filelist": filelist,
                    "exclude_fids": []
                }
            ) as sub_resp:
                data = await sub_resp.json()
                if not sub_resp.ok:
                    logger.error(f'Failed to delete files: {filelist}, error: {data}')
                    return None
                return data


async def main():
    quark = Quark(cookies='b-user-id=2b859cab-f785-f931-30fa-df07da411ff3; _UP_A4A_11_=wb96a11b485744259bef147e03a5cd3f; __sdid=AASkfqL4DlbS/7P2kkvTjgNRahK3OvcAJ0CWQEUjo2pQSlqYuACgL8sxTKQFiGweMzeJ8SonxgwOpXefcdo/sMy44eYAo0epbBOQOuQ7doLsLQ==; isg=BNraO9TSZnoeEuVo6oE4otNnK4b8C17l2yrDoORbLG04V3-RzJrL9VduIyNLh9Z9; _UP_F7E_8D_=OJeFCNbmQjm%2F3dMtooKz5EPwKLOVbxJPcg0RzQPI6Knpe%2FVlExDLvwWk3%2BqxkwVyhdZ%2Bc09AyraclvYdENl26pP6NZpJjHSFAga2josF9WI5KqmBMZjstSyxXmZd2p0oVFkfbqd%2FhVjlt0AbNkJqehFHs%2BQ%2FpshPrgvAKVxvsq4i6PDzvwNnqu7rSXFm5RjbW1%2FmvBLvMwKTOk2wEvbokFCfwAd1vIZU3jqYRQqSOImsE%2BlICX7X3bnSe%2BfKM3Zv2UZosU2CPO%2B1Iq86JO9nn%2FDYH6B%2FNHWts0k6QXf1G5ISlI%2FcYWnMe2QDdOIIh794r8W58Q%2B8dF%2F5NYnDCuCRKgZGr%2FUOk3sLe1kCgrk%2By8w80vdxOCQMN6P6GbeZVhMFSjr6E2PYGvGzVjEvMmznaYgK6I8jY9WVzigJOC%2BMHN%2BzVjEvMmznaZXRA%2FkTlwOLBTMqB7aZ91np%2B2IQpk63KWzaL7EpoajxeN5%2FTNSk2xc%3D; _UP_D_=pc; _UP_30C_6A_=st9cd620112savvjy9dotw0da33tal2b; _UP_TS_=sg1f164684aeb2016f3088369728ffd6746; _UP_E37_B7_=sg1f164684aeb2016f3088369728ffd6746; _UP_TG_=st9cd620112savvjy9dotw0da33tal2b; _UP_335_2B_=1; __pus=a7a78b1a90b688dfe7841e4bf2f98300AATYi/G+Qq7OARLPylNw0GynbNPPtSIJ465qoZjqcFqI9kpepQI0F2odEzE2QmRPM7PK1xqc4t3BONUmvArVGDZi; __kp=75e66880-8bd3-11f0-bef7-4517a1b89c67; __kps=AASjR2fXaMQGjkqOmoZ7mP8y; __ktd=8CQ/17ZlNp4OW6fTU/82Gg==; __uid=AASjR2fXaMQGjkqOmoZ7mP8y; tfstk=gwiredNw2kcX5T5XVjEF30cmOeE8YkRsrDNQKvD3F7VuFuMnuvMweJGSKWuUiXpRVuARxWDtMzNoOu1eYjruJ4NQNWrEpfJX1htseYELVCO6f6170TETEW2hOoX0FkyupDUkcYELxIO-fXzSebp22yruxKr0L85uxMc3ixVYpJfuKgvqnSFcqJVhrnV0d8ShEXqH3xVYKkVntzvqnSe3xWc_WXcR0Szk34K6i51JHzViESShbOe_rBHRRGjiz8zrxYV2ULo4UzP_k-2jEckiEceEvdbUTvgoN-hebIrm4bouuk-FDuMZobzqzBS4kqDtxruv_NHtEbugS0x2UXlmBVEoqBI7w2DmxSikdMPi5AE4HDOAqWum-0a8v_Az30kZY2Sy_6eDNKoKKT73r-e41KJVeezX7UhLO37dJr8Y3599BwQLr_y41KhAJwUR_-P6EY5..; __puus=12b95c5fbaf1cd00169b922736c44ab8AAQ6j7M6ljISsTkfnBTT7sD+zyzuFDcyO+DWgwPp73nV72cW9xdVvYEfaMym6BcE6/GmHtRfzJjTfxToR7I51+ly94BRR3y2JMvpCwCIdo0gAaGWUwxpNEXyy86L4VLJlo0lWhjJFkBqh40v5Sgo4/MFaWbx83Lb5SLN5uX1IUZvrvM8h8ME2SZqsjdnY5QZ56kf3EiUVptaJEBhKlsl+e7k')
    import pprint, json

    # 测试获取路径文件映射
    path_file_map = await quark.get_path_file_map(paths=['/tv/大主宰 (2023)/Season 01'])
    for path, file in path_file_map.items():
        files = await quark.get_quark_clouddrive_files(pdir_fid=file['fid'])
        print(json.dumps(files, indent=4, ensure_ascii=False))

    # 测试分享链接
    print('分享文件')
    async with aiohttp.ClientSession() as http_session:
        quark_id, stoken, pdir_fid, _ = await quark.get_quark_id_stoken_pdir_fid(
            url="https://pan.quark.cn/s/ab6b5ed38f98/fe73cef3b3c64a85b07cc7287531ebe8",
            session=http_session
        )
        dir_details = await quark.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False)
        print(json.dumps(dir_details, indent=4, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())