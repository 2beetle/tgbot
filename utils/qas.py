import asyncio
import datetime
import json
import logging
import pprint
import re
from datetime import timedelta
from typing import Tuple
from urllib.parse import urlparse, parse_qs

import aiohttp
import pytz

from config.config import TIME_ZONE, AI_API_KEYS, AI_MODEL, AI_API_KEY, AI_HOST
from utils.ai import openapi_chat

logger = logging.getLogger(__name__)


class QuarkAutoDownload:
    # 会话最大存活时间：1小时
    _SESSION_MAX_AGE = timedelta(hours=1)

    def __init__(self, api_token):
        self.api_token = api_token
        self._session = None
        self._session_created_at = None

    async def _get_session(self):
        """获取或创建会话，支持会话过期自动重建"""
        # 检查会话是否需要重新创建
        need_new_session = (
            self._session is None or
            self._session_created_at is None or
            self._session.closed or
            datetime.datetime.now() - self._session_created_at > self._SESSION_MAX_AGE
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
                total=180,        # 总超时 180 秒
                connect=30,      # 连接超时 30 秒
                sock_read=40     # 读取超时 40 秒
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
            self._session_created_at = datetime.datetime.now()
            logger.debug("已创建新的 QAS HTTP 会话")

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

    async def data(self, host):
        async with await self._get_session() as session:
            async with session.get(f'{host}/data?token={self.api_token}') as resp:
                if not resp.ok:
                    logger.error(f'Failed to get data {host}, error: {resp.reason}')
                    return None
                else:
                    data = await resp.json()
                    return data.get('data')

    async def add_job(self, host, task_name, share_url, save_path, pattern, replace):
        async with await self._get_session() as session:
            async with session.post(
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
            ) as resp:
                if not resp.ok:
                    logger.error(f'Failed to add task {task_name}, error: {resp.text}')
                return await resp.json()

    async def update(self, host, data):
        async with await self._get_session() as session:
            async with session.post(
                f'{host}/update?token={self.api_token}',
                headers={
                    'Content-Type': 'application/json',
                },
                json=data
            ) as resp:
                if not resp.ok:
                    logger.error(f'Failed to update data {host}, error: {resp.text}')
                else:
                    logger.info(f'Success to update data {host}, data: {data}')
                    return await resp.json()

    async def get_share_detail(self, host, data):
        async with await self._get_session() as session:
            async with session.post(
                f'{host}/get_share_detail?token={self.api_token}',
                headers={
                    'Content-Type': 'application/json',
                },
                json=data
            ) as resp:
                if not resp.ok:
                    logger.error(f'Failed to get_share_detail {host}, error: {resp.text}')
                else:
                    logger.info(f'Success to get_share_detail {host}, data: {data}')
                    return await resp.json()

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

        try:
            async with await self._get_session() as session:
                async with session.post(
                    "https://drive-h.quark.cn/1/clouddrive/share/sharepage/token?pr=ucpro&fr=pc",
                    headers={
                        'Content-Type': 'application/json',
                    },
                    json={
                        "pwd_id": quark_id,
                        "passcode": pass_code,
                        "support_visit_limit_private_share": True
                    }
                ) as stoken_resp:
                    if not stoken_resp.ok:
                        logger.error(f'Failed to get quark stoken {url}, error: {await stoken_resp.text()}')
                        return quark_id, None, pdir_fid
                    data = await stoken_resp.json()
                    stoken = data['data']['stoken']
                return quark_id, stoken, pdir_fid
        except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
            logger.error(f'获取夸克分享token失败 {url}, 错误: {e}')
            return quark_id, None, pdir_fid

    async def get_quark_dir_detail(self, quark_id, stoken, pdir_fid, include_dir=True):
        async with await self._get_session() as session:
            try:
                async with session.get(
                    f'https://drive-h.quark.cn/1/clouddrive/share/sharepage/detail',
                    params={
                        'pr': 'ucpro',
                        'fr': 'pc',
                        'uc_param_str': '',
                        '_size': 20,
                        'pdir_fid': pdir_fid,
                        'pwd_id': quark_id,
                        'stoken': stoken,
                        'ver': 2
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
            except (aiohttp.ClientError, asyncio.TimeoutError, KeyError) as e:
                logger.error(f'获取夸克目录详情失败 {quark_id}/{pdir_fid}, 错误: {e}')
                return []

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

    async def get_fid_files(self, url: str, include_dir: bool = False):
        async def recursive_get_fid_files(fid, file_name, quark_id, stoken, fid_files, include_dir):
            dir_files = list()
            files = await self.get_quark_dir_detail(quark_id=quark_id, stoken=stoken, pdir_fid=fid)
            for file in files:
                if file['dir'] is True:
                    try:
                        await recursive_get_fid_files(file['fid'], file['file_name'], quark_id, stoken, fid_files, include_dir)
                    except Exception as e:
                        logger.warning(f'递归获取子目录失败 {file["file_name"]}, 跳过该目录。错误: {e}')
                    if include_dir:
                        dir_files.append({
                            "file_name": file['file_name'],
                            "dir": file['dir'],
                            "last_update_at": datetime.datetime.fromtimestamp(int(file['last_update_at']) / 1000,
                                                                              tz=datetime.UTC
                                                                              ).astimezone(pytz.timezone(TIME_ZONE)),
                        })
                else:
                    dir_files.append({
                        "file_name": file['file_name'],
                        "dir": file['dir'],
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
        await recursive_get_fid_files(0, "root", quark_id, stoken, fid_files, include_dir)
        return fid_files

    async def build_unicode_tree_paragraph(self, folder_name: str, files: list) -> str:
        lines = [f"{folder_name}"]
        for i, file in enumerate(sorted(files, key=lambda x: x['file_name'])):
            is_last = i == len(files) - 1
            prefix = '└──' if is_last else '├──'
            icon = '📂' if file['dir'] is True else '🎥'
            lines.append(f"{prefix} {icon} {file['file_name']}")
        return '\n'.join(lines)

    async def get_tree_paragraphs(self, fid_files: dict) -> list[str]:
        result = []
        for key, files in fid_files.items():
            if key == 'root__0':
                continue
            paragraph = await self.build_unicode_tree_paragraph(key, files)
            result.append(paragraph)
        return result

    async def ai_recommend_folder(self, fid_files: dict, session, user_id) -> str | None:
        """AI 分析各目录及其文件，推荐包含最新集视频文件的文件夹，返回推荐的 fid"""
        # 构建目录摘要
        folders_info = {}
        for key, files in fid_files.items():
            if key == 'root__0':
                continue
            folder_name = key.split('__')[0]
            fid = key.split('__')[1]
            file_names = [f['file_name'] for f in files if not f.get('dir')]
            folders_info[fid] = {
                'folder_name': folder_name,
                'file_count': len(file_names),
                'files': file_names[:30],  # 最多取30个文件名避免 prompt 过长
            }

        if not folders_info:
            return None

        prompt = f"""以下是一个夸克网盘分享链接下的各个文件夹及其包含的文件列表：
{json.dumps(folders_info, ensure_ascii=False, indent=2)}

请分析各文件夹的内容，找出最可能包含最新集视频文件的文件夹。判断依据（按优先级排序）：
1. 文件夹名称中的季数编号（如 S01、Season 1、第一季等），季数最大的文件夹优先
2. 文件名中的集数编号（如 E01、EP01、第01集等），集数最大的文件所在文件夹优先
3. 文件名中包含高清标识（如 4K、2160p、1080p）的文件夹优先

只返回JSON格式结果：{{"recommended_fid": "推荐文件夹的fid", "reason": "推荐原因（简短）"}}"""

        try:
            ai_result = await openapi_chat(
                role="你是一个影视资源分析专家，善于从文件列表中判断哪个文件夹包含最新最全的视频资源",
                prompt=prompt,
                session=session,
                user_id=user_id
            )
            if not ai_result:
                return None

            ai_result = ai_result.strip()
            if ai_result.startswith("```json"):
                ai_result = ai_result[7:]
            if ai_result.endswith("```"):
                ai_result = ai_result[:-3]

            result = json.loads(ai_result)
            recommended_fid = result.get('recommended_fid')
            reason = result.get('reason', '')
            logger.info(f"AI 推荐文件夹: fid={recommended_fid}, 原因: {reason}")
            return recommended_fid, reason
        except Exception as e:
            logger.error(f"AI 推荐文件夹失败: {e}")
            return None

    async def ai_generate_replace(self, url: str, session, user_id, prompt) -> dict:
        quark_id, stoken, pdir_fid = await self.get_quark_id_stoken_pdir_fid(url=url)
        dir_details = await self.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False)
        files = [
            {
               "file_name": dir_detail['file_name'],
               "video_max_resolution": dir_detail.get('video_max_resolution'),
            }
            for dir_detail in dir_details
        ]
        # 优化提示信息，专注于Replace生成
        enhanced_prompt = f"""{prompt}

基于以下文件列表生成合适的Replace替换模板：
{files}

你的任务：
1. 分析文件列表中的文件名格式和结构
2. 根据用户要求生成能正确提取文件信息的Pattern（如果需要）
3. 生成相应的Replace替换模板，确保与Pattern匹配格式兼容

Replace生成规则：
- 如果Pattern提取了季数(S)和集数(E)，Replace应该为 `S{{SXX}}E{{E}}.{{EXT}}`
- 如果Pattern只提取了集数(E)，Replace应该为 `S01E{{E}}.{{EXT}}` (默认第一季)
- 如果Pattern没有提取季集信息，Replace应该为 `{{ORIGINAL_NAME}}.{{EXT}}`
- 对于电影，Replace通常为 `{{TITLE}}.{{EXT}}`

常用变量：
- `{{SXX}}`: 季数，格式化为两位数
- `{{E}}`: 集数，保持原始格式
- `{{EXT}}`: 文件扩展名
- `{{TITLE}}`: 电影/剧集标题
- `{{ORIGINAL_NAME}}`: 原始文件名（不含扩展名）

必须执行的注意事项：
1. Replace模板必须与Pattern的提取组兼容
2. 使用传统的反向引用语法：\1, \2 等，而不是${{1}}或{{1}}
3. Pattern中不要使用命名分组
4. 只返回JSON格式结果：{{"pattern": "...", "replace": "..."}}"""
        ai_analysis = await openapi_chat(
            role="你是一个编写正则表达式的专家，善于从元素列表中通过编写正则提取到想要的元素",
            prompt=enhanced_prompt,
            session=session,
            user_id=user_id
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

    async def ai_generate_params(self, url: str, session, user_id, prompt) -> dict:
        quark_id, stoken, pdir_fid = await self.get_quark_id_stoken_pdir_fid(url=url)
        dir_details = await self.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False)
        files = [
            {
               "file_name": dir_detail['file_name'],
               "video_max_resolution": dir_detail.get('video_max_resolution'),
            }
            for dir_detail in dir_details
        ]
        prompt = rf"""\
用户要求：\
{prompt}\

你需要做：
1. 请从以下文件列表中根据文件的file_name编写正则表达式只提取符合<用户要求>的文件并且还需要提取符合<用户要求>的文件的 file_name 中的季数和集数和文件后缀，如果file_name中没有季数的信息，则只需要提取集数
{files}
2. 根据编写的正则匹配式匹配到file_name并提取到 file_name 中的季数和集数和文件后缀后，用于生成新 file_name，如果前面的正则没有提取到季数的信息，则默认为第一季

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
            session=session,
            user_id=user_id
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
        async with await self._get_session() as session:
            async with session.post(
                f'{host}/run_script_now?token={self.api_token}',
                json={
                    "tasklist": task_list
                }
            ) as resp:
                if not resp.ok:
                    logger.error(f'Failed to run script {host}, error: {resp.reason}')
                else:
                    return await resp.text()

    async def ai_classify_seasons(self, url: str, session, user_id) -> Tuple[dict, dict]:
        quark_id, stoken, pdir_fid = await self.get_quark_id_stoken_pdir_fid(url=url)
        dir_details = await self.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=True)
        dirname_fid_map = dict()
        for dir_detail in dir_details:
            if dir_detail['dir'] is True:
                dirname_fid_map[dir_detail['file_name']] = dir_detail['fid']

        logger.info(f"整理前文件夹 fid：{dirname_fid_map}")

        prompt = f"""
以下是一个字典，其中字典的key为文件夹名称，现在需要你帮我提取出其中文件夹名称与电视剧季数有关的数据:
{dirname_fid_map}
要求：
1. 文件夹名称与电视剧季数无关的需要排除
2. 匹配到与电视剧季数相关的文件夹名称后需要重命名为「Season {{季数}}」，其中{{季数}}为两个数字，例如如第一季为Season 01，第三季为Season 03，第十一季为Season 11
3. 输出一个字典，key为重命名前的文件夹名称，value为重命名后的电视剧季数

例子：
1. 
输入：
{{
    '纸钞屋S01': 'e6b8a848e57c4988b719facff5a1b45f',
    '纸钞屋S02': '569e17e641fc46638c2b9ea06f278d12',
    '纸钞屋S03': 'b696a6df6bfb447f9c638858bdbcd3e4',
    '纸钞屋S04': '94f8753593f647f1af26089230d79e76',
    '纸钞屋S05': 'f0529a63ac464e299e39b0caa3001df3',
    '相关图片': "f0529a63ac464e299e39bdddd001df3"
}}
输出：
{{
    '纸钞屋S01': 'Season 01',
    '纸钞屋S02': 'Season 02',
    '纸钞屋S03': 'Season 03',
    '纸钞屋S04': 'Season 04',
    '纸钞屋S05': 'Season 05'
}}

2. 
输入：
{{
    '龙族第二季': 'e6b8a848e57c4988b719facff5a1b45f',
    '龙族第五季': '569e17e641fc46638c2b9ea06f278d12',
    '更新提醒': "f0529a63ac464e299e39bdddd001df3"
}}
 
输出：
{{
    '龙族第二季': 'Season 02',
    '龙族第五季': 'Season 05',
}}
 
"""
        ai_analysis = await openapi_chat(
            role="你是一个影视剧季数分类专家，善于从多个文件夹列表中找到和影视剧季数相关的文件夹",
            prompt=prompt,
            session=session,
            user_id=user_id
        )

        # 清理可能的非JSON内容
        ai_analysis = ai_analysis.strip()
        if ai_analysis.startswith("```json"):
            ai_analysis = ai_analysis[7:]
        if ai_analysis.endswith("```"):
            ai_analysis = ai_analysis[:-3]

        extract_seasons = json.loads(ai_analysis)
        extract_seasons = dict(sorted(extract_seasons.items(), key=lambda x: int(x[1].split()[1])))
        logger.info(f"ai识别文件夹季数结果：{extract_seasons}")

        seasons_fid = dict()

        for dirname, fid in dirname_fid_map.items():
            if dirname in extract_seasons:
                seasons_fid.update({
                    extract_seasons[dirname]: fid
                })

        logger.info(f"整理后结果 {seasons_fid}")
        return seasons_fid, extract_seasons

    @classmethod
    async def extract_all_two_digit_numbers(cls, text):
      """提取所有数字并转为两位格式"""
      numbers = re.findall(r'\d+', text)
      return [num.zfill(2)[-2:] for num in numbers]



if __name__ == '__main__':
    qas = QuarkAutoDownload(api_token='')
    print(asyncio.run())