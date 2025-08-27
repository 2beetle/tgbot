import html
import json
import logging
import os.path

from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from api.base import command
from api.common import cancel_conversation_callback
from config.config import get_allow_roles_command_map
from db.models.log import OperationLog, OperationType
from db.models.qas import QuarkAutoDownloadConfig
from db.models.user import User
from utils.command_middleware import depends
from utils.common import get_random_letter_number_id
from utils.qas import QuarkAutoDownload
from utils.the_movie_db import TheMovieDB

logger = logging.getLogger(__name__)

HOST_SET, API_TOKEN_SET, SAVE_PATH_PREFIX_SET, MOVIE_SAVE_PATH_PREFIX_SET, PATTERN_SET, REPLACE_SET = range(6)

QAS_ADD_TASK_EXTRA_SAVE_PATH_SET, QAS_ADD_TASK_PATTERN_SET, QAS_ADD_TASK_REPLACE_SET, QAS_ADD_TASK_ARIA2_SET = range(4)

QAS_TASK_UPDATE_IF_DEFAULT_URL_SET, QAS_TASK_UPDATE_SELECT_NEW_URL_SET, QAS_TASK_UPDATE_SELECT_SHARE_URL_SET, QAS_TASK_UPDATE_PATTERN_SET, QAS_TASK_UPDATE_REPLACE_SET, QAS_TASK_UPDATE_ARIA2_SET = range(6)

async def host_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("请输入你 QAS 服务的 Host：")
    return HOST_SET

async def host_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    host = str(update.message.text)
    if host and host.endswith('/'):
        host = host[:-1]
    context.user_data.update({
        "configuration": {
            "qas": {
                'host': host
            }
        }
    })
    await update.message.reply_text("请输入你 QAS 服务的 Api Token：", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
    ]]))
    return  API_TOKEN_SET

async def api_token_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    context.user_data["configuration"]['qas'].update({
        'api_token': update.message.text
    })
    await update.message.reply_text("请输入你 QAS 服务的 TV Save Path 前缀：(开头不要带/，会自动补充)", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
    ]]))
    return SAVE_PATH_PREFIX_SET


async def save_path_prefix_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    save_path_prefix = '/' + str(update.message.text)
    if save_path_prefix.endswith('/'):
        save_path_prefix = save_path_prefix[:-1]
    context.user_data["configuration"]['qas'].update({
        'save_path_prefix': save_path_prefix
    })
    await update.message.reply_text("请输入你 QAS 服务的 MOVIE Save Path 前缀：(开头不要带/，会自动补充)",
                                    reply_markup=InlineKeyboardMarkup([[
                                        InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
                                    ]]))
    return MOVIE_SAVE_PATH_PREFIX_SET


async def movie_save_path_prefix_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    movie_save_path_prefix = '/' + str(update.message.text)
    if movie_save_path_prefix.endswith('/'):
        movie_save_path_prefix = movie_save_path_prefix[:-1]
    context.user_data["configuration"]['qas'].update({
        'movie_save_path_prefix': movie_save_path_prefix
    })
    await update.message.reply_text(
        "请输入你 QAS 服务的 Pattern：",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"默认 => .*.(mp4|mkv)", callback_data=f"qas_pattern_input.*.(mp4|mkv)")
                ],
                [
                    InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
                ]
            ]
        )
    )
    return PATTERN_SET


async def pattern_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if update.message:
        context.user_data["configuration"]['qas'].update({
            'pattern': update.message.text
        })
    return await ask_replace(update, context, session, user)


async def pattern_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    pattern = query.data.split('qas_pattern_input')[1]
    await query.message.reply_text(f"使用默认Pattern：{pattern}")
    context.user_data["configuration"]['qas'].update({
        'pattern': pattern
    })
    return await ask_replace(update, context, session, user)


async def ask_replace(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.effective_message.reply_text(
        "请输入你 QAS 服务的 Replace：",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("默认 => {SXX}E{E}.{EXT}", callback_data="qas_replace_input:{SXX}E{E}.{EXT}")
                ],
                [
                    InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
                ]
            ]
        )
    )
    return REPLACE_SET


async def replace_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if update.message:
        context.user_data["configuration"]['qas'].update({
            'replace': update.message.text if update.message.text else "{SXX}E{E}.{EXT}"
        })
    return await upsert_qas_configuration_finish(update, context, session, user)


async def replace_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    replace = query.data.split(':')[1]
    await query.message.reply_text(f"使用默认Replace：{replace}")
    context.user_data["configuration"]['qas'].update({
        'replace': replace
    })
    return await upsert_qas_configuration_finish(update, context, session, user)


async def upsert_qas_configuration_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    host = context.user_data["configuration"]["qas"]["host"]
    api_token = context.user_data["configuration"]["qas"]["api_token"]
    save_path_prefix = context.user_data["configuration"]["qas"]["save_path_prefix"]
    movie_save_path_prefix = context.user_data["configuration"]["qas"]["movie_save_path_prefix"]
    pattern = context.user_data["configuration"]["qas"]["pattern"]
    replace = context.user_data["configuration"]["qas"]["replace"]

    count = session.query(QuarkAutoDownloadConfig).filter(QuarkAutoDownloadConfig.user_id == user.id).count()
    if count > 0:
        session.query(QuarkAutoDownloadConfig).filter(QuarkAutoDownloadConfig.user_id == user.id).update({
            QuarkAutoDownloadConfig.host: host,
            QuarkAutoDownloadConfig.api_token: api_token,
            QuarkAutoDownloadConfig.save_path_prefix: save_path_prefix,
            QuarkAutoDownloadConfig.movie_save_path_prefix: movie_save_path_prefix,
            QuarkAutoDownloadConfig.pattern: pattern,
            QuarkAutoDownloadConfig.replace: replace
        })
    else:
        session.add(
            QuarkAutoDownloadConfig(
                host=host,
                api_token=api_token,
                save_path_prefix=save_path_prefix,
                movie_save_path_prefix=movie_save_path_prefix,
                pattern=pattern,
                replace=replace,
                user_id=user.id
            )
        )
    session.commit()

    message = f"""
<b>Host：</b> {host}
<b>Api Token：</b> {api_token}
<b>TV Save Path 前缀：</b> {save_path_prefix}
<b>MOVIE Save Path 前缀：</b> {movie_save_path_prefix}
<b>Pattern：</b> <code>{pattern}</code>
<b>Replace：</b> <code>{replace}</code>

操作完成
        """
    await update.effective_message.reply_text(message, parse_mode="html")
    return ConversationHandler.END


@command(name='qas_add_task', description="QAS 新增任务", args="{quark share url} {tv name}")
async def qas_add_task(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if len(context.args) < 2:
        await update.message.reply_text("缺少参数")

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    if not qas_config:
        await update.message.reply_text("尚未添加 QAS 配置，请使用 /upsert_configuration 命令进行配置")
    quark_share_url = context.args[0]
    task_name = context.args[1]
    context.user_data.update({
        'qas_add_task': {
            "shareurl": {},
            "taskname": task_name,
            "pattern": qas_config.pattern,
            "replace": qas_config.replace,
        }
    })
    if not quark_share_url.endswith('/'):
        quark_share_url += '/'
    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    fid_files = await qas.get_fid_files(quark_share_url)
    tree_paragraphs = await qas.get_tree_paragraphs(fid_files)
    for _ in tree_paragraphs:
        file_name = _.split('\n')[0].split('__')[0]
        fid = _.split('\n')[0].split('__')[1]
        url = quark_share_url + fid
        tmp_url_id = get_random_letter_number_id()
        context.user_data['qas_add_task']['shareurl'][tmp_url_id] = url
        await update.message.reply_text(
            text=_,
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"选择 {file_name}", callback_data=f"qas_add_task_state:{tmp_url_id}")
                ]
            ])
        )


async def qas_add_task_select_resource_type(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    url_id = query.data.split(":")[1]
    await update.message.reply_text(
        text="请选择资源类型",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"📺 电视节目", callback_data=f"qas_add_task_tv:{url_id}")
            ],
            [
                InlineKeyboardButton(f"🎬 电影", callback_data=f"qas_add_task_movie:{url_id}")
            ]
        ])
    )

async def qas_add_task_select_tv(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    task_name = context.user_data['qas_add_task']['taskname']
    url_id = query.data.split(":")[1]
    context.user_data['qas_add_task']['shareurl'] = context.user_data['qas_add_task']['shareurl'][url_id]
    tv_list = await TheMovieDB().search_tv(task_name, count=5)
    if not tv_list:
        await update.effective_message.reply_text("tmdb 查询不到相关信息，请重新运行添加任务指令并输入不同剧名")
        return
    for tv in tv_list:
        tv_info_tmp_id = get_random_letter_number_id()
        tv_name = tv.get('name')
        tv_year = f"({tv.get('first_air_date').split('-')[0]})"
        context.user_data['qas_add_task'][tv_info_tmp_id] = {
            "resource_name": tv_name,
            "resource_year": tv_year,
            "resource_type": "tv"
        }
        await query.message.reply_photo(
            photo=tv.get('photo_url'),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"选择 {tv_name} {tv_year}", callback_data=f"qas_add_task_pattern_input:{tv_info_tmp_id}")
                ]
            ])
        )

async def qas_add_task_select_movie(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    task_name = context.user_data['qas_add_task']['taskname']
    url_id = query.data.split(":")[1]
    context.user_data['qas_add_task']['shareurl'] = context.user_data['qas_add_task']['shareurl'][url_id]
    movie_list = await TheMovieDB().search_movie(task_name, count=5)
    if not movie_list:
        await update.effective_message.reply_text("tmdb 查询不到相关信息，请重新运行添加任务指令并输入不同剧名")
        return
    for movie in movie_list:
        movie_info_tmp_id = get_random_letter_number_id()
        movie_name = movie.get('name')
        movie_year = f"({movie.get('first_air_date').split('-')[0]})"
        context.user_data['qas_add_task'][movie_info_tmp_id] = {
            "resource_name": movie_name,
            "resource_year": movie_year,
            "resource_type": "movie"
        }
        await query.message.reply_photo(
            photo=movie.get('photo_url'),
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"选择 {movie_name} {movie_year}", callback_data=f"qas_add_task_pattern_input:{movie_info_tmp_id}")
                ]
            ])
        )


async def qas_add_task_start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    tv_info_id = query.data.split(":")[1]
    resource_name = context.user_data['qas_add_task'][tv_info_id]['resource_name']
    resource_year = context.user_data['qas_add_task'][tv_info_id]['resource_year']
    resource_type = context.user_data['qas_add_task'][tv_info_id]['resource_type']
    context.user_data['qas_add_task']['resource_name'] = f'{resource_name} {resource_year}'
    context.user_data['qas_add_task']['taskname'] = resource_name

    if resource_type == 'tv':
        context.user_data['qas_add_task'].update({
            'savepath': os.path.join(qas_config.save_path_prefix, context.user_data['qas_add_task']['resource_name'])
        })

        await update.effective_message.reply_text(
            text="AI 根据分享链接中的文件内容生成筛选 4K 资源正则中..."
        )
        qas_config = session.query(QuarkAutoDownloadConfig).filter(
            QuarkAutoDownloadConfig.user_id == user.id
        ).first()
        qas = QuarkAutoDownload(api_token=qas_config.api_token)
        params = await qas.ai_generate_params(context.user_data['qas_add_task']['shareurl'])
        context.user_data['qas_add_task']['ai_params'] = params

        await update.effective_message.reply_text(
            text=f"拓展 save path ({context.user_data['qas_add_task']['savepath']})：",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"❌ 不拓展 save path", callback_data=f"qas_add_task_save_path_button:")
                ],
                [
                    InlineKeyboardButton(f"❌ 取消新增操作", callback_data=f"cancel_qas_update_task")
                ]
            ])
        )
        return QAS_ADD_TASK_EXTRA_SAVE_PATH_SET
    elif resource_type == 'movie':
        context.user_data['qas_add_task'].update({
            'savepath': os.path.join(qas_config.movie_save_path_prefix, context.user_data['qas_add_task']['resource_name'])
        })
        context.user_data['qas_add_task']['pattern'] = '*.(mp4|mkv|iso|ass|srt)'
        context.user_data['qas_add_task']['replace'] = f'{context.user_data['qas_add_task']['resource_name']}.{{EXT}}'
        return await qas_add_task_pattern_ask_aria2(update, context, session, user)
    return None


async def qas_add_task_extra_save_path_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if update.message:
        if update.message.text.startswith("/"):
            update.message.text = update.message.text[1:]
        context.user_data['qas_add_task']['savepath'] = os.path.join(context.user_data['qas_add_task']['savepath'], update.message.text)

    return await qas_add_task_pattern_ask_pattern(update, context, session, user)


async def qas_add_task_extra_save_path_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    await update.effective_message.reply_text(f"不拓展 save path")
    return await qas_add_task_pattern_ask_pattern(update, context, session, user)


async def qas_add_task_pattern_ask_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    params = context.user_data['qas_add_task']['ai_params']
    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Pattern</b>：\n<b>默认 Pattern</b>：{context.user_data['qas_add_task']['pattern']}\n<b>AI生成 Pattern</b>：{params.get('pattern')}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"默认 Pattern",
                                     callback_data=f"qas_add_task_pattern_button:")
            ],
            [
                InlineKeyboardButton(f"AI生成 Pattern",
                                     callback_data=f"qas_add_task_pattern_button:ai_params")
            ],
            [
                InlineKeyboardButton(f"❌ 取消新增操作", callback_data=f"cancel_qas_update_task")
            ]
        ]),
        parse_mode=ParseMode.HTML
    )
    return QAS_ADD_TASK_PATTERN_SET


async def qas_add_task_pattern_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if update.message:
        context.user_data['qas_add_task']['pattern'] = update.message.text
    return await qas_add_task_pattern_ask_replace(update, context, session, user)


async def qas_add_task_pattern_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, params = update.callback_query.data.split(':')
    if params:
        pattern = context.user_data['qas_add_task']['ai_params'].get("pattern")
        context.user_data['qas_add_task']['pattern'] = pattern
        await update.effective_message.reply_text(f"任务Pattern使用 Ai 生成 Pattern：{pattern}")
    else:
        pattern = context.user_data['qas_add_task']['pattern']
        await update.effective_message.reply_text(f"任务Pattern使用默认配置：{pattern}")

    return await qas_add_task_pattern_ask_replace(update, context, session, user)


async def qas_add_task_pattern_ask_replace(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    params = context.user_data['qas_add_task']['ai_params']
    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Replace</b>：\n默认 Replace: {context.user_data['qas_add_task']['replace']}\nAI生成 Replace：{params.get('replace')}",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"默认 Replace", callback_data=f"qas_add_task_replace_button:")
            ],
            [
                InlineKeyboardButton(f"AI生成 Replace",
                                     callback_data=f"qas_add_task_replace_button:ai_params")
            ],
            [
                InlineKeyboardButton(f"❌ 取消新增操作", callback_data=f"cancel_qas_update_task")
            ]
        ]),
        parse_mode=ParseMode.HTML
    )
    return QAS_ADD_TASK_REPLACE_SET


async def qas_add_task_replace_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if update.message:
        context.user_data['qas_add_task']['replace'] = update.message.text
    return await qas_add_task_pattern_ask_aria2(update, context, session, user)


async def qas_add_task_replace_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, params = update.callback_query.data.split(':')
    if params:
        replace = context.user_data['qas_add_task']['ai_params'].get("replace")
        context.user_data['qas_add_task']['replace'] = replace
        await update.effective_message.reply_text(f"任务Replace使用 Ai 生成 Replace：{replace}")
    else:
        replace = context.user_data['qas_add_task']['replace']
        await update.effective_message.reply_text(f"任务Replace使用默认配置：{replace}")

    return await qas_add_task_pattern_ask_aria2(update, context, session, user)


async def qas_add_task_pattern_ask_aria2(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.effective_message.reply_text(
        text="是否开启 aria2下载：",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"开启 aira2 下载 ✅", callback_data=f"qas_add_task_aria2_button:true")
            ],
            [
                InlineKeyboardButton(f"关闭 aira2 下载 ❌", callback_data=f"qas_add_task_aria2_button:false")
            ]
        ])
    )
    return QAS_ADD_TASK_ARIA2_SET


async def qas_add_task_aria2_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, aria2 = update.callback_query.data.split(':')
    if aria2 == 'false':
        context.user_data['qas_add_task'].update({
            'addition': {
                'aria2': {
                    'auto_download': False
                }
            }
        })
        await update.effective_message.reply_text(f"关闭 aira2 下载 ❌")
    else:
        context.user_data['qas_add_task'].update({
            'addition': {
                'aria2': {
                    'auto_download': True
                }
            }
        })
        await update.effective_message.reply_text(f"开启 aira2 下载 ✅")

    return await qas_add_task_finish(update, context, session, user)


async def qas_add_task_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    qas = QuarkAutoDownload(api_token=qas_config.api_token)

    resp = await qas.add_job(
        host=qas_config.host,
        task_name=context.user_data['qas_add_task']['taskname'],
        share_url=context.user_data['qas_add_task']['shareurl'],
        save_path=context.user_data['qas_add_task']['savepath'],
        pattern=context.user_data['qas_add_task']['pattern'],
        replace=context.user_data['qas_add_task']['replace']
    )

    if resp.ok:
        save_path = resp.json().get('data').get('savepath')
        # 修改 aria2
        data = await qas.data(host=qas_config.host)
        for index, task in enumerate(data.get("tasklist", [])):
            if task.get("savepath") == save_path:
                data["tasklist"][index]['ignore_extension'] = True
                if context.user_data['qas_add_task']['addition'].get('aria2', {}).get('auto_download', True) == False:
                    data["tasklist"][index]["addition"]["aria2"]["auto_download"] = False
                else:
                    data["tasklist"][index]["addition"]["aria2"]["auto_download"] = True
                break
        await qas.update(host=qas_config.host, data=data)
        message = f"""
    新增任务成功：
    📌 <b>任务名称</b>：{data['tasklist'][index]['taskname']}
    📁 <b>保存路径</b>：<code>{data['tasklist'][index]['savepath']}</code>
    🔗 <b>分享链接</b>：<a href="{data['tasklist'][index]['shareurl']}">点我打开</a>
    🎯 <b>匹配规则</b>：<code>{data['tasklist'][index]['pattern']}</code>
    🔁 <b>替换模板</b>：<code>{data['tasklist'][index]['replace']}</code>

    📦 <b>扩展设置</b>：
    - 🧲 <b>Aria2 自动下载</b>：{"✅ 开启" if data['tasklist'][index]["addition"]["aria2"]["auto_download"] else "❌ 关闭"}
    - 🧬 <b>Emby 匹配</b>：{"✅ 开启" if data['tasklist'][index]["addition"].get("emby", {}).get("try_match") else "❌ 关闭"}（Media ID: {data['tasklist'][index]["addition"].get("emby", {}).get("media_id", "")}）

    🌐 <a href="{qas_config.host}"><b>你的 QAS 服务</b></a>
            """
        await update.effective_message.reply_text(
            text=message,
            parse_mode="html",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"▶️ 运行此任务", callback_data=f"qas_run_script:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🛠️ 更新此任务", callback_data=f"qas_update_task:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🗑 删除此任务", callback_data=f"qas_delete_task:{index}")
                    ]
                ])
        )

        context.user_data.pop("qas_add_task")

    else:
        await update.effective_message.reply_text(
            text="添加任务失败"
        )

    return ConversationHandler.END


@command(name='qas_list_task', description="列出 QAS 任务", args="{任务名称}")
async def qas_list_task(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    def is_subsequence(small, big):
        it = iter(big)
        return all(ch in it for ch in small)

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    if not qas_config:
        await update.effective_message.reply_text("尚未添加 QAS 配置，请使用 /upsert_configuration 命令进行配置")

    if len(context.args) > 0:
        task_name = ' '.join(context.args)
    else:
        task_name = None

    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    data = await qas.data(host=qas_config.host)
    task_list = [task for task in data.get("tasklist", []) if not (task_name and not is_subsequence(task_name, task["taskname"]))]

    if len(task_list) == 0:
        await update.effective_message.reply_text(
            text=f"未查询到 <b>{task_name}</b> 相关任务",
            parse_mode="html",
        )

    else:
        for index, task in enumerate(data.get("tasklist", [])):
            if task not in task_list:
                continue
            task_text = f"""
🆔 <b>ID</b>：{index}
📌 <b>任务名称</b>：{task.get('taskname')}
📁 <b>保存路径</b>：{task.get('savepath')}
🔗 <b>分享链接</b>：<a href="{task.get('shareurl')}">点我打开</a>
🎯 <b>匹配规则</b>：<code>{data['tasklist'][index]['pattern']}</code>
🔁 <b>替换模板</b>：<code>{data['tasklist'][index]['replace']}</code>
🧲 <b>Aria2 自动下载</b>：{"✅ 开启" if data['tasklist'][index]["addition"]["aria2"]["auto_download"] else "❌ 关闭"}
"""
            if task.get('shareurl_ban'):
                task_text += f"🚫：{task.get('shareurl_ban')}"
            else:
                task_text += f"✅：正常"
            await update.effective_message.reply_text(
                text=task_text,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"▶️ 运行此任务", callback_data=f"qas_run_script:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🛠️ 更新此任务", callback_data=f"qas_update_task:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🗑 删除此任务", callback_data=f"qas_delete_task:{index}")
                    ]
                ]),
                parse_mode=ParseMode.HTML,
            )


# @command(name='qas_update_task', description="更新 QAS 任务", args="{qas task id}")
async def qas_update_task(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer(text="获取任务信息")
    task_id = int(query.data.split(':')[1])
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    if not qas_config:
        await update.effective_message.reply_text("尚未添加 QAS 配置，请使用 /upsert_configuration 命令进行配置")

    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    data = await qas.data(host=qas_config.host)
    task_info = data.get("tasklist", [])[task_id]
    task_info.update({'id': task_id})
    context.user_data.update({
        'qas_update_task': task_info
    })

    await query.message.reply_text(
        text="请输入分享链接：",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"保留旧链接", callback_data=f"qas_update_task_share_url_input")
                ],
                [
                    InlineKeyboardButton(f"❌ 取消更新操作", callback_data=f"cancel_qas_update_task"),
                ]
            ]
        )
    )

    return QAS_TASK_UPDATE_IF_DEFAULT_URL_SET


async def qas_task_update_select_default_url_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    quark_share_url = update.message.text
    if not quark_share_url.endswith('/'):
        quark_share_url += '/'

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    qas = QuarkAutoDownload(api_token=qas_config.api_token)

    fid_files = await qas.get_fid_files(quark_share_url)
    if not fid_files:
        await update.effective_message.reply_text("链接状态异常, 更新操作已取消")
        return ConversationHandler.END
    tree_paragraphs = await qas.get_tree_paragraphs(fid_files)
    for _ in tree_paragraphs:
        file_name = _.split('\n')[0].split('__')[0]
        fid = _.split('\n')[0].split('__')[1]
        url = quark_share_url + fid
        tmp_url_id = get_random_letter_number_id()
        context.user_data.update({
            tmp_url_id: url
        })
        await update.message.reply_text(
            text=_,
            reply_markup=InlineKeyboardMarkup(
                [[
                    InlineKeyboardButton(f"选择 {file_name}",
                                         callback_data=f"qas_task_update_select_new_url_set:{tmp_url_id}")
                ]]
            )
        )
    return QAS_TASK_UPDATE_SELECT_NEW_URL_SET


async def qas_task_update_select_default_url_set_buton(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    await update.effective_message.reply_text("任务分享链接不修改")
    return await qas_task_update_url_ask_pattern(update, context, session, user)


async def qas_task_update_select_new_url_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    tmp_url_id = query.data.split(':')[1]
    context.user_data['qas_update_task']['shareurl'] = context.user_data[tmp_url_id]

    await update.effective_message.reply_text(f"任务分享链接修改为：{context.user_data[tmp_url_id]}")
    return await qas_task_update_url_ask_pattern(update, context, session, user)


async def qas_task_update_url_ask_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):

    await update.effective_message.reply_text(
        text="AI 根据分享链接中的文件内容生成筛选 4K 资源正则中..."
    )
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    qas = QuarkAutoDownload(api_token=qas_config.api_token)

    session.add(
        OperationLog(
            user_id=user.id,
            operation=OperationType.READ,
            description=f"用户{user.tg_id} - {user.username} 使用ai feature"
        )
    )
    session.commit()

    params = await qas.ai_generate_params(context.user_data['qas_update_task']['shareurl'])
    context.user_data['qas_update_task']['ai_params'] = params

    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Pattern</b>：\n<b>旧Pattern</b>: <code>{context.user_data['qas_update_task']['pattern']}</code>\n<b>AI生成Pattern</b>: <code>{params.get('pattern')}</code>\n<b>默认Pattern</b>: <code>{qas_config.pattern}</code>",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"保留旧Pattern", callback_data=f"qas_update_task_pattern_set:")
                ],
                [
                    InlineKeyboardButton(f"AI Generated Pattern",
                                         callback_data=f"qas_update_task_pattern_set:ai_params"),
                ],
                [
                    InlineKeyboardButton(f"使用默认 Pattern",
                                         callback_data=f"qas_update_task_pattern_set:default"),
                ],
                [
                    InlineKeyboardButton(f"❌ 取消更新操作", callback_data=f"cancel_qas_update_task")
                ]
            ]
        ),
        parse_mode=ParseMode.HTML,
    )
    return QAS_TASK_UPDATE_PATTERN_SET


async def qas_task_update_pattern_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if update.message:
        context.user_data['qas_update_task']['pattern'] = update.message.text
    return await qas_task_update_pattern_ask_replace(update, context, session, user)


async def qas_task_update_pattern_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, pattern = update.callback_query.data.split(':')
    if pattern == 'ai_params':
        pattern = context.user_data['qas_update_task']['ai_params'].get("pattern")
        context.user_data['qas_update_task']['pattern'] = pattern
        await update.effective_message.reply_text(f"任务Pattern使用 Ai 生成 Pattern：{pattern}")
    elif pattern == 'default':
        qas_config = session.query(QuarkAutoDownloadConfig).filter(
            QuarkAutoDownloadConfig.user_id == user.id
        ).first()
        context.user_data['qas_update_task']['pattern'] = qas_config.pattern
        await update.effective_message.reply_text(f"使用默认 Pattern：{qas_config.pattern}")
    else:
        await update.effective_message.reply_text("任务Pattern不修改")

    return await qas_task_update_pattern_ask_replace(update, context, session, user)


async def qas_task_update_pattern_ask_replace(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    params = context.user_data['qas_update_task']['ai_params']
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    await update.effective_message.reply_text(
        text= f"请输入或选择 <b>Replace</b>：\n<b>旧Replace</b>: <code>{context.user_data['qas_update_task']['replace']}</code>\n<b>AI生成Replace</b>: <code>{params.get('replace')}</code>\n<b>默认Replace</b>: <code>{qas_config.replace}</code>",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(f"保留旧Replace", callback_data=f"qas_update_task_replace_set:")
                ],
                [
                    InlineKeyboardButton(f"AI Generated Replace",
                                         callback_data=f"qas_update_task_replace_set:ai_params"),
                ],
                [
                    InlineKeyboardButton(f"使用默认 Replace",
                                         callback_data=f"qas_update_task_replace_set:default"),
                ],
                [
                    InlineKeyboardButton(f"❌ 取消更新操作", callback_data=f"cancel_qas_update_task")
                ]
            ]
        ),
        parse_mode=ParseMode.HTML
    )
    return QAS_TASK_UPDATE_REPLACE_SET

async def qas_task_update_replace_set_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if update.message:
        context.user_data['qas_update_task']['replace'] = update.message.text
    return await qas_task_update_pattern_ask_aria2(update, context, session, user)


async def qas_task_update_replace_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, replace = update.callback_query.data.split(':')
    if replace == 'ai_params':
        replace = context.user_data['qas_update_task']['ai_params'].get("replace")
        context.user_data['qas_update_task']['replace'] = replace
        await update.effective_message.reply_text(f"任务Replace使用 Ai 生成 Replace：{replace}")
    elif replace == 'default':
        qas_config = session.query(QuarkAutoDownloadConfig).filter(
            QuarkAutoDownloadConfig.user_id == user.id
        ).first()
        context.user_data['qas_update_task']['replace'] = qas_config.replace
        await update.effective_message.reply_text(f"使用默认 Replace：{qas_config.replace}")
    else:
        await update.effective_message.reply_text("任务Replace不修改")

    return await qas_task_update_pattern_ask_aria2(update, context, session, user)


async def qas_task_update_pattern_ask_aria2(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.effective_message.reply_text(
        text="是否开启 aria2下载：",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"开启 aira2 下载 ✅", callback_data=f"qas_update_task_aria2_set:true")
            ],
            [
                InlineKeyboardButton(f"关闭 aira2 下载 ❌", callback_data=f"qas_update_task_aria2_set:false")
            ]
        ])
    )
    return QAS_TASK_UPDATE_ARIA2_SET


async def qas_update_task_aria2_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, aria2 = update.callback_query.data.split(':')
    if aria2 == 'false':
        aria2_auto_download = False
        await update.effective_message.reply_text(f"关闭 aira2 下载 ❌")
    else:
        aria2_auto_download = True
        await update.effective_message.reply_text(f"开启 aira2 下载 ✅")

    if not context.user_data['qas_update_task'].get('addition'):
        context.user_data['qas_update_task'].update({
            "addition": {
                'aria2': {
                    'auto_download': aria2_auto_download
                }
            }
        })
    else:
        context.user_data['qas_update_task']['addition'].update({
            'aria2': {
                'auto_download': aria2_auto_download
            }
        })

    return await qas_task_update_finish(update, context, session, user)


async def qas_task_update_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    task_in_update = context.user_data['qas_update_task']
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    data = await qas.data(host=qas_config.host)

    for index, task in enumerate(data.get("tasklist", [])):
        if index == int(task_in_update.get("id")):
            for k, v in task_in_update.items():
                data['tasklist'][index][k] = v
            data['tasklist'][index].pop('id')
            data['tasklist'][index].pop('ai_params')
            if 'shareurl_ban' in data['tasklist'][index]:
                data['tasklist'][index].pop('shareurl_ban')
            data['tasklist'][index]['startfid'] = ''
            data["tasklist"][index]['ignore_extension'] = True
            break
    await qas.update(host=qas_config.host, data=data)
    message = f"""
    更新任务成功：
    📌 <b>任务名称</b>：{data['tasklist'][index]['taskname']}
    📁 <b>保存路径</b>：<code>{data['tasklist'][index]['savepath']}</code>
    🔗 <b>分享链接</b>：<a href="{data['tasklist'][index]['shareurl']}">点我打开</a>
    🎯 <b>匹配规则</b>：<code>{data['tasklist'][index]['pattern']}</code>
    🔁 <b>替换模板</b>：<code>{data['tasklist'][index]['replace']}</code>

    📦 <b>扩展设置</b>：
    - 🧲 <b>Aria2 自动下载</b>：{"✅ 开启" if data['tasklist'][index]["addition"]["aria2"]["auto_download"] else "❌ 关闭"}
    - 🧬 <b>Emby 匹配</b>：{"✅ 开启" if data['tasklist'][index]["addition"].get("emby", {}).get("try_match") else "❌ 关闭"}（Media ID: {data['tasklist'][index]["addition"].get("emby", {}).get("media_id", "")}）

    🌐 <a href="{qas_config.host}"><b>你的 QAS 服务</b></a>
    """
    await update.effective_message.reply_text(
        text=message,
        parse_mode="html",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"▶️ 运行此任务", callback_data=f"qas_run_script:{index}")
            ],
            [
                InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{index}")
            ],
            [
                InlineKeyboardButton(f"🛠️ 更新此任务", callback_data=f"qas_update_task:{index}")
            ],
            [
                InlineKeyboardButton(f"🗑 删除此任务", callback_data=f"qas_delete_task:{index}")
            ]
        ])
    )

    context.user_data.pop("qas_update_task")
    return ConversationHandler.END


@command(name='qas_delete_task', description="QAS 删除任务", args="{task id}")
async def qas_delete_task(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if len(context.args) < 1:
        await update.message.reply_text("缺少任务 ID 参数")

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    if not qas_config:
        await update.message.reply_text("尚未添加 QAS 配置，请使用 /upsert_configuration 命令进行配置")
    qas_task_id = context.args[0]
    context.user_data['qas_delete_task_id'] = qas_task_id
    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    data = await qas.data(host=qas_config.host)
    for index, task in enumerate(data.get("tasklist", [])):
        if index == int(qas_task_id):
            break
    await update.effective_message.reply_text(
        text=f"确定删除任务 {data['tasklist'][index]['taskname']} 吗?",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("确定 ✅", callback_data=f"qas_delete_task_confirm:"),
                InlineKeyboardButton("取消 ❌", callback_data=f"qas_delete_task_cancel:")
            ]
        ])
    )


async def qas_delete_task_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    qas_delete_task_id = query.data.split(":")[1]
    context.args = [qas_delete_task_id]
    return await qas_delete_task(update, context, session, user)


async def qas_delete_task_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    qas_deleted_task_id = int(context.user_data['qas_delete_task_id'])
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    data = await qas.data(host=qas_config.host)
    task_name = data['tasklist'][qas_deleted_task_id]['taskname']
    data['tasklist'].pop(int(qas_deleted_task_id))
    await qas.update(host=qas_config.host, data=data)
    await update.effective_message.reply_text(
        text=f"删除 QAS 任务 {task_name} 成功",
    )
    context.user_data['qas_delete_task_id'] = -1


async def qas_delete_task_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    context.user_data['qas_delete_task_id'] = -1
    await update.effective_message.reply_text(
        text=f"取消删除 QAS 任务",
    )


@command(name='qas_run_script', description="QAS 运行任务", args="{task id}")
async def qas_run_script(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    await update.effective_message.reply_text(
        text="任务运行中，请稍后..."
    )
    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    data = await qas.data(host=qas_config.host)
    if len(context.args) < 1:
        task_list = data["tasklist"]
    else:
        task_list = [data["tasklist"][int(context.args[0])]]
    run_script_result = await qas.run_script_now(host=qas_config.host, task_list=task_list)
    lines = [_.replace('data: ', '') for _ in run_script_result.split('\n') if _]
    await update.effective_message.reply_text(
        text="\n".join(lines)
    )


async def qas_run_script_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    context.args = [int(query.data.split(":")[1])]
    return await qas_run_script(update, context, session, user)


@command(name='qas_view_task_regex', description="QAS 查看任务正则匹配效果", args="{task id}")
async def qas_view_task_regex(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if len(context.args) < 1:
        await update.effective_message.reply_text(
            text="缺少任务 id 参数"
        )

    await update.effective_message.reply_text(
        text=f"查看任务 {int(context.args[0])} 正则匹配效果中，请稍等..."
    )
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    qas = QuarkAutoDownload(api_token=qas_config.api_token)
    data = await qas.data(host=qas_config.host)
    index = int(context.args[0])

    regex_preview = await qas.get_share_detail(host=qas_config.host, data={
        "shareurl": data['tasklist'][index]['shareurl'],
        "stoken": "",
        "task": data['tasklist'][index]
    })

    data_list = regex_preview.get("data", {}).get("list", [])
    start_update_time_stamp = None
    start_fid = data['tasklist'][index].get('startfid')
    if start_fid:
        for d in data_list:
            if d.get('fid') == start_fid:
                start_update_time_stamp = int(d.get('l_updated_at'))
                break
    sorted_items = sorted(data_list, key=lambda it: str(it.get("file_name_hl", "")))
    lines = [f"任务 <b>{data['tasklist'][index]['taskname']}</b> 正则匹配预览："]
    for i, it in enumerate(sorted_items):
        file_name = html.escape(str(it.get("file_name", "")))
        if it.get("file_name_saved", ""):
            replace_text = html.escape(str(it.get("file_name_saved", ""))) + " （💾已经转存）"
        elif it.get("file_name_re", ""):
            if start_update_time_stamp and int(it.get('l_updated_at')) < start_update_time_stamp:
                replace_text = html.escape(str(it.get("file_name_re", ""))) + " （🟠 未转存，但是更新时间早于「文件起始」更新时间，不会转存）"
            else:
                replace_text = html.escape(str(it.get("file_name_re", ""))) + " （🟢 将会转存）"
        else:
            replace_text = '❌'

        lines.append(f"<b>{i + 1}</b>: {file_name} => <b>{replace_text}</b>")

    await update.effective_message.reply_text(
        text="\n".join(lines),
        parse_mode="html",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"▶️ 运行此任务", callback_data=f"qas_run_script:{index}")
            ],
            [
                InlineKeyboardButton(f"🛠️ 更新此任务", callback_data=f"qas_update_task:{index}")
            ],
            [
                InlineKeyboardButton(f"🗑 删除此任务", callback_data=f"qas_delete_task:{index}")
            ]
        ])
    )


async def qas_view_task_regex_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    context.args = [int(query.data.split(":")[1])]
    return await qas_view_task_regex(update, context, session, user)


handlers = [
    # 插入 qas 配置
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(host_input),
                pattern=r"^upsert_qas_configuration"
            )
        ],
        states={
            HOST_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(host_set)
                )
            ],
            API_TOKEN_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(api_token_set)
                )
            ],
            SAVE_PATH_PREFIX_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(save_path_prefix_set)
                )
            ],
            MOVIE_SAVE_PATH_PREFIX_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(movie_save_path_prefix_set)
                )
            ],
            PATTERN_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(pattern_set_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(pattern_set_button),
                        pattern=r"^qas_pattern_input.*$"
                )
            ],
            REPLACE_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(replace_set_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(replace_set_button),
                        pattern=r"^qas_replace_input:.*$"
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_upsert_configuration$")
        ],
    ),
    # add qas task
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_start),
                pattern=r"^qas_add_task_pattern_input:.*$"
            )
        ],
        states={
            QAS_ADD_TASK_EXTRA_SAVE_PATH_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_extra_save_path_set_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_extra_save_path_set_button),
                        pattern=r"^qas_add_task_save_path_button:.*$"
                )
            ],
            QAS_ADD_TASK_PATTERN_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_pattern_set_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_pattern_set_button),
                        pattern=r"^qas_add_task_pattern_button:.*$"
                )
            ],
            QAS_ADD_TASK_REPLACE_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_replace_set_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_replace_set_button),
                        pattern=r"^qas_add_task_replace_button:.*$"
                )
            ],
            QAS_ADD_TASK_ARIA2_SET: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_aria2_set_button),
                        pattern=r"^qas_add_task_aria2_button:.*$"
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_qas_update_task$")
        ],
    ),
    # update qas task
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_update_task),
                pattern=r"^qas_update_task:.*$"
            )
        ],
        states={
            QAS_TASK_UPDATE_IF_DEFAULT_URL_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_select_default_url_set_text)
                ),
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_select_default_url_set_buton),
                    pattern=r"^qas_update_task_share_url_input$"
                )
            ],
            QAS_TASK_UPDATE_SELECT_NEW_URL_SET: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_select_new_url_set_button),
                        pattern=r"^qas_task_update_select_new_url_set:.*$"
                )
            ],
            QAS_TASK_UPDATE_PATTERN_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_pattern_set_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_pattern_set_button),
                        pattern=r"^qas_update_task_pattern_set:.*$"
                )
            ],
            QAS_TASK_UPDATE_REPLACE_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_replace_set_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_replace_set_button),
                        pattern=r"^qas_update_task_replace_set:.*$"
                )
            ],
            QAS_TASK_UPDATE_ARIA2_SET: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_update_task_aria2_set_button),
                        pattern=r"^qas_update_task_aria2_set:.*$"
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_qas_update_task$")
        ],
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_select_resource_type),
            pattern=r"^qas_add_task_state:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_select_tv),
            pattern=r"^qas_add_task_tv:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_select_movie),
            pattern=r"^qas_add_task_movie:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_delete_task_handler),
            pattern=r"^qas_delete_task:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_delete_task_confirm_handler),
            pattern=r"^qas_delete_task_confirm:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_delete_task_cancel_handler),
            pattern=r"^qas_delete_task_cancel:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_run_script'))(qas_run_script_handler),
            pattern=r"^qas_run_script:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_run_script'))(qas_view_task_regex_handler),
            pattern=r"^qas_view_task_regex:.*$"
    )
]