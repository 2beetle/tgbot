import datetime
import html
import json
import logging
import os.path
import re

import aiohttp
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler, ConversationHandler, MessageHandler, filters

from api.base import command
from api.common import cancel_conversation_callback
from api.user_config import get_user_save_space_mode, get_user_quark_cookies
from config.config import get_allow_roles_command_map, TIME_ZONE
from db.models.log import OperationLog, OperationType
from db.models.qas import QuarkAutoDownloadConfig
from db.models.user import User
from utils.command_middleware import depends
from utils.common import get_random_letter_number_id
from utils.qas import QuarkAutoDownload
from utils.quark import Quark
from utils.the_movie_db import TheMovieDB
from utils.crypto import encrypt_sensitive_data, decrypt_sensitive_data
import pytz

logger = logging.getLogger(__name__)


def get_decrypted_api_token(qas_config):
    """从QAS配置中获取解密的API令牌"""
    if not qas_config or not qas_config.api_token:
        return None
    try:
        return decrypt_sensitive_data(qas_config.api_token)
    except Exception as e:
        logger.error(f"解密API令牌失败: {str(e)}")
        return None

HOST_SET, API_TOKEN_SET, SAVE_PATH_PREFIX_SET, MOVIE_SAVE_PATH_PREFIX_SET, PATTERN_SET, REPLACE_SET = range(6)
QAS_EDIT_FIELD_SELECT, QAS_EDIT_HOST, QAS_EDIT_API_TOKEN, QAS_EDIT_SAVE_PATH, QAS_EDIT_MOVIE_PATH, QAS_EDIT_PATTERN, QAS_EDIT_REPLACE = range(6, 13)

QAS_ADD_TASK_EXTRA_SAVE_PATH_SET, QAS_ADD_TASK_PATTERN_SET, QAS_ADD_TASK_PATTERN_REPLACE_GENERATE, QAS_ADD_TASK_REPLACE_SET, QAS_ADD_TASK_ARIA2_SET, QAS_ADD_TASK_IGNORE_EXTENSION_SET = range(6)

QAS_TASK_UPDATE_IF_DEFAULT_URL_SET, QAS_TASK_UPDATE_SELECT_NEW_URL_SET, QAS_TASK_UPDATE_SELECT_SHARE_URL_SET, QAS_TASK_UPDATE_PATTERN_SET, QAS_TASK_UPDATE_REPLACE_SET, QAS_TASK_UPDATE_ARIA2_SET = range(6)
QAS_TASK_UPDATE_FIELD_SELECT, QAS_TASK_UPDATE_SHARE_URL, QAS_TASK_UPDATE_SAVEPATH, QAS_TASK_UPDATE_PATTERN, QAS_TASK_UPDATE_PATTERN_GENERATE, QAS_TASK_UPDATE_REPLACE_GENERATE, QAS_TASK_UPDATE_REPLACE, QAS_TASK_UPDATE_ARIA2, QAS_TASK_UPDATE_IGNORE_EXTENSION = range(6, 15)

QAS_FIX_LINK_INPUT_URL, QAS_FIX_LINK_SELECT_URL, QAS_FIX_LINK_CONFIRM = range(15, 18)

async def host_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    # 检查是否已有配置
    existing_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    if existing_config:
        # 显示当前配置并让用户选择要修改的字段
        keyboard = [
            [InlineKeyboardButton("🌐 Host", callback_data="qas_edit_host")],
            [InlineKeyboardButton("🔑 Api Token", callback_data="qas_edit_api_token")],
            [InlineKeyboardButton("📁 TV Save Path", callback_data="qas_edit_save_path")],
            [InlineKeyboardButton("🎬 Movie Save Path", callback_data="qas_edit_movie_path")],
            [InlineKeyboardButton("🎯 Pattern", callback_data="qas_edit_pattern")],
            [InlineKeyboardButton("🔄 Replace", callback_data="qas_edit_replace")],
            [InlineKeyboardButton("✅ 完成修改", callback_data="qas_finish_edit")],
            [InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")]
        ]

        message = f"""
<b>当前 QAS 配置：</b>
🌐 <b>Host：</b> {existing_config.host}
🔑 <b>Api Token：</b> {'***' if existing_config.api_token else '未设置'}
📁 <b>TV Save Path：</b> {existing_config.save_path_prefix}
🎬 <b>Movie Save Path：</b> {existing_config.movie_save_path_prefix}
🎯 <b>Pattern：</b> <code>{existing_config.pattern}</code>
🔄 <b>Replace：</b> <code>{existing_config.replace}</code>

请选择要修改的字段：
        """

        await update.effective_message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="html"
        )
        return QAS_EDIT_FIELD_SELECT
    else:
        # 新配置，需要填写所有字段
        await update.effective_message.reply_text("请输入你 QAS 服务的 Host：")
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
                    InlineKeyboardButton(f"默认 => .*.(mp4|mkv|ass|srt)", callback_data=f"qas_pattern_input.*.(mp4|mkv|ass|srt)")
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
    await update.effective_message.reply_text(f"使用默认Pattern：{pattern}")
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
    await update.effective_message.reply_text(f"使用默认Replace：{replace}")
    context.user_data["configuration"]['qas'].update({
        'replace': replace
    })
    return await upsert_qas_configuration_finish(update, context, session, user)


# 部分修改相关函数
async def qas_field_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    # 初始化编辑数据结构
    if "qas_edit_data" not in context.user_data:
        context.user_data["qas_edit_data"] = {}

    field_map = {
        "qas_edit_host": ("host", "请输入你 QAS 服务的 Host：", QAS_EDIT_HOST),
        "qas_edit_api_token": ("api_token", "请输入你 QAS 服务的 Api Token：", QAS_EDIT_API_TOKEN),
        "qas_edit_save_path": ("save_path_prefix", "请输入你 QAS 服务的 TV Save Path 前缀：(开头不要带/，会自动补充)", QAS_EDIT_SAVE_PATH),
        "qas_edit_movie_path": ("movie_save_path_prefix", "请输入你 QAS 服务的 MOVIE Save Path 前缀：(开头不要带/，会自动补充)", QAS_EDIT_MOVIE_PATH),
        "qas_edit_pattern": ("pattern", "请输入你 QAS 服务的 Pattern：", QAS_EDIT_PATTERN),
        "qas_edit_replace": ("replace", "请输入你 QAS 服务的 Replace：", QAS_EDIT_REPLACE),
        "qas_finish_edit": ("finish", "", None)
    }

    action = query.data

    if action == "qas_finish_edit":
        # 完成编辑，准备保存
        existing_config = session.query(QuarkAutoDownloadConfig).filter(
            QuarkAutoDownloadConfig.user_id == user.id
        ).first()

        # 构建更新数据
        if "configuration" not in context.user_data:
            context.user_data["configuration"] = {}
        if "qas" not in context.user_data["configuration"]:
            context.user_data["configuration"]["qas"] = {}

        edit_data = context.user_data.get("qas_edit_data", {})

        # 只更新用户修改过的字段，处理现有配置不存在的情况
        if "host" in edit_data:
            context.user_data["configuration"]["qas"]["host"] = edit_data["host"]
        else:
            context.user_data["configuration"]["qas"]["host"] = existing_config.host if existing_config else ""

        if "api_token" in edit_data:
            context.user_data["configuration"]["qas"]["api_token"] = edit_data["api_token"]
        else:
            # 使用现有配置的解密API token
            decrypted_token = get_decrypted_api_token(existing_config) if existing_config else ""
            context.user_data["configuration"]["qas"]["api_token"] = decrypted_token or ""

        if "save_path_prefix" in edit_data:
            context.user_data["configuration"]["qas"]["save_path_prefix"] = edit_data["save_path_prefix"]
        else:
            context.user_data["configuration"]["qas"]["save_path_prefix"] = existing_config.save_path_prefix if existing_config else ""

        if "movie_save_path_prefix" in edit_data:
            context.user_data["configuration"]["qas"]["movie_save_path_prefix"] = edit_data["movie_save_path_prefix"]
        else:
            context.user_data["configuration"]["qas"]["movie_save_path_prefix"] = existing_config.movie_save_path_prefix if existing_config else ""

        if "pattern" in edit_data:
            context.user_data["configuration"]["qas"]["pattern"] = edit_data["pattern"]
        else:
            context.user_data["configuration"]["qas"]["pattern"] = existing_config.pattern if existing_config else ""

        if "replace" in edit_data:
            context.user_data["configuration"]["qas"]["replace"] = edit_data["replace"]
        else:
            context.user_data["configuration"]["qas"]["replace"] = existing_config.replace if existing_config else ""

        # 清理编辑数据
        context.user_data.pop("qas_edit_data", None)
        return await upsert_qas_configuration_finish(update, context, session, user)

    elif action in field_map:
        field_name, prompt_text, next_state = field_map[action]
        if field_name == "finish":
            return await qas_field_select_handler(update, context, session, user)

        # 保存当前编辑的字段状态
        context.user_data["qas_edit_current_field"] = next_state

        await update.effective_message.reply_text(
            prompt_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
            ]])
        )
        return next_state


async def qas_edit_field_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理编辑字段的输入"""
    if not update.message:
        return

    current_state = context.user_data.get("qas_edit_current_field")
    input_value = update.message.text

    # 根据不同的字段进行特殊处理
    if current_state == QAS_EDIT_HOST:
        if input_value and input_value.endswith('/'):
            input_value = input_value[:-1]
    elif current_state in [QAS_EDIT_SAVE_PATH, QAS_EDIT_MOVIE_PATH]:
        input_value = '/' + str(input_value)
        if input_value.endswith('/'):
            input_value = input_value[:-1]

    # 保存编辑的数据
    if "qas_edit_data" not in context.user_data:
        context.user_data["qas_edit_data"] = {}

    field_mapping = {
        QAS_EDIT_HOST: "host",
        QAS_EDIT_API_TOKEN: "api_token",
        QAS_EDIT_SAVE_PATH: "save_path_prefix",
        QAS_EDIT_MOVIE_PATH: "movie_save_path_prefix",
        QAS_EDIT_PATTERN: "pattern",
        QAS_EDIT_REPLACE: "replace"
    }

    field_name = field_mapping.get(current_state)
    if field_name:
        context.user_data["qas_edit_data"][field_name] = input_value

    # 回到字段选择界面
    return await qas_show_edit_menu(update, context, session, user)


async def qas_show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """显示编辑菜单"""
    existing_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    edit_data = context.user_data.get("qas_edit_data", {})

    # 显示当前配置和已修改的字段
    host = edit_data.get("host", existing_config.host)
    save_path = edit_data.get("save_path_prefix", existing_config.save_path_prefix)
    movie_path = edit_data.get("movie_save_path_prefix", existing_config.movie_save_path_prefix)
    pattern = edit_data.get("pattern", existing_config.pattern)
    replace = edit_data.get("replace", existing_config.replace)

    keyboard = [
        [InlineKeyboardButton("🌐 Host", callback_data="qas_edit_host")],
        [InlineKeyboardButton("🔑 Api Token", callback_data="qas_edit_api_token")],
        [InlineKeyboardButton("📁 TV Save Path", callback_data="qas_edit_save_path")],
        [InlineKeyboardButton("🎬 Movie Save Path", callback_data="qas_edit_movie_path")],
        [InlineKeyboardButton("🎯 Pattern", callback_data="qas_edit_pattern")],
        [InlineKeyboardButton("🔄 Replace", callback_data="qas_edit_replace")],
        [InlineKeyboardButton("✅ 完成修改", callback_data="qas_finish_edit")],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")]
    ]

    message = f"""
<b>当前 QAS 配置：</b>
🌐 <b>Host：</b> {host}
🔑 <b>Api Token：</b> {'***' if edit_data.get('api_token') or existing_config.api_token else '未设置'}
📁 <b>TV Save Path：</b> {save_path}
🎬 <b>Movie Save Path：</b> {movie_path}
🎯 <b>Pattern：</b> <code>{pattern}</code>
🔄 <b>Replace：</b> <code>{replace}</code>

请选择要修改的字段：
    """

    await update.effective_message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="html"
    )
    return QAS_EDIT_FIELD_SELECT


async def upsert_qas_configuration_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    host = context.user_data["configuration"]["qas"]["host"]
    api_token = context.user_data["configuration"]["qas"]["api_token"]
    save_path_prefix = context.user_data["configuration"]["qas"]["save_path_prefix"]
    movie_save_path_prefix = context.user_data["configuration"]["qas"]["movie_save_path_prefix"]
    pattern = context.user_data["configuration"]["qas"]["pattern"]
    replace = context.user_data["configuration"]["qas"]["replace"]

    # 加密敏感数据
    encrypted_api_token = encrypt_sensitive_data(api_token)

    # 查找现有配置
    existing_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    if existing_config:
        # 部分更新：只更新提供的字段
        update_data = {}
        if host != existing_config.host:
            update_data[QuarkAutoDownloadConfig.host] = host
        if encrypted_api_token != existing_config.api_token:
            update_data[QuarkAutoDownloadConfig.api_token] = encrypted_api_token
        if save_path_prefix != existing_config.save_path_prefix:
            update_data[QuarkAutoDownloadConfig.save_path_prefix] = save_path_prefix
        if movie_save_path_prefix != existing_config.movie_save_path_prefix:
            update_data[QuarkAutoDownloadConfig.movie_save_path_prefix] = movie_save_path_prefix
        if pattern != existing_config.pattern:
            update_data[QuarkAutoDownloadConfig.pattern] = pattern
        if replace != existing_config.replace:
            update_data[QuarkAutoDownloadConfig.replace] = replace

        if update_data:
            session.query(QuarkAutoDownloadConfig).filter(
                QuarkAutoDownloadConfig.user_id == user.id
            ).update(update_data)
            message = "QAS 配置已部分更新：\n"
        else:
            message = "QAS 配置没有变化：\n"
    else:
        # 新增配置
        session.add(
            QuarkAutoDownloadConfig(
                host=host,
                api_token=encrypted_api_token,
                save_path_prefix=save_path_prefix,
                movie_save_path_prefix=movie_save_path_prefix,
                pattern=pattern,
                replace=replace,
                user_id=user.id
            )
        )
        message = "QAS 配置已新增：\n"

    session.commit()

    # 显示当前配置状态
    current_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    message += f"""
<b>Host：</b> {current_config.host}
<b>Api Token：</b> {'***' if current_config.api_token else '未设置'}
<b>TV Save Path 前缀：</b> {current_config.save_path_prefix}
<b>MOVIE Save Path 前缀：</b> {current_config.movie_save_path_prefix}
<b>Pattern：</b> <code>{current_config.pattern}</code>
<b>Replace：</b> <code>{current_config.replace}</code>

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

    # 分离 query 参数（如 pwd），避免末尾补 / 时破坏参数
    parsed_url = re.split(r'(\?.*)', quark_share_url, maxsplit=1)
    base_url = parsed_url[0]
    query_string = parsed_url[1] if len(parsed_url) > 1 else ''

    if not base_url.endswith('/'):
        base_url += '/'

    # 提取链接根路径
    pattern = r"(https://pan\.quark\.cn/s/[^#]+#/list/share/)"
    match = re.search(pattern, base_url)
    if match:
        base_url = match.group(1)

    quark_share_url = base_url + query_string

    context.user_data.update({
        'qas_add_task': {
            "shareurl": {},
            "taskname": task_name,
            "pattern": qas_config.pattern,
            "replace": qas_config.replace,
            "is_multi_seasons": False,
            "quark_share_url_origin": quark_share_url,
            "ai_generate_pattern_texts": {
                'filename_with_4k': '文件名中带 4K 的文件'
            }
        }
    })

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    await update.message.reply_text(text='解析分享链接中，请稍后')

    qas = QuarkAutoDownload(api_token=api_token)
    fid_files = await qas.get_fid_files(quark_share_url, True)
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
    await update.effective_message.reply_text(
        text="请选择资源类型",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"📺 电视节目", callback_data=f"qas_add_task_tv:{url_id}")
            ],
            [
                InlineKeyboardButton(f"📺 电视节目(多季)", callback_data=f"qas_add_task_tv_multi_seasons:{url_id}")
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

async def qas_add_task_select_tv_multi_seasons(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    context.user_data['qas_add_task'].update({'is_multi_seasons': True})
    await qas_add_task_select_tv(update, context, session, user)

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
        context.user_data['qas_add_task']['pattern'] = '.*.(mp4|mkv|iso|ass|srt)'
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
    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Pattern</b>：\n<b>默认 Pattern</b>：<code>{context.user_data['qas_add_task']['pattern']}</code>\n",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"默认 Pattern",
                                     callback_data=f"qas_add_task_pattern_button:")
            ],
            [
                InlineKeyboardButton(f"通过AI生成Pattern",
                                     callback_data=f"qas_add_task_ai_generate_pattern_button:")
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


async def qas_add_task_ai_ask_pattern_replace_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
    quark_id, stoken, pdir_fid = await qas.get_quark_id_stoken_pdir_fid(url=context.user_data['qas_add_task']['shareurl'])
    dir_details = await qas.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False)

    files_text = '\n'.join([
        f"🎥 {dir_detail['file_name']}"
        for dir_detail in dir_details[:15]
    ])

    await update.effective_message.reply_text(
        text=f'📁 <a href="{context.user_data['qas_add_task']['shareurl']}">分享链接</a> 中的文件列表：\n\n{files_text}\n\n💡 请描述你希望匹配的文件类型或特征：',
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
               InlineKeyboardButton(f"文件名中带 4K 的文件",
                                    callback_data=f"qas_add_task_ai_generate_pattern_replace_button:filename_with_4k")
           ],
           [
               InlineKeyboardButton(f"❌ 取消新增操作",
                                    callback_data=f"cancel_qas_update_task")
           ]
        ])
    )

    return QAS_ADD_TASK_PATTERN_REPLACE_GENERATE


async def qas_add_task_ai_generate_pattern_replace_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.effective_message.reply_text(
        text="🤖 AI 根据分享链接中的文件内容生成正则中..."
    )
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
    params = await qas.ai_generate_params(
        url=context.user_data['qas_add_task']['shareurl'],
        session=session,
        user_id=user.id,
        prompt=update.message
    )
    context.user_data['qas_add_task']['ai_params'] = params

    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Pattern</b>：\n<b>默认 Pattern</b>：<code>{context.user_data['qas_add_task']['pattern']}</code>\n<b>AI 生成 Pattern</b>：<code>{context.user_data['qas_add_task']['ai_params']['pattern']}</code>\n",
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
                InlineKeyboardButton(f"通过AI生成Pattern",
                                     callback_data=f"qas_add_task_ai_generate_pattern_button:")
            ],
            [
                InlineKeyboardButton(f"❌ 取消新增操作", callback_data=f"cancel_qas_update_task")
            ]
        ]),
        parse_mode=ParseMode.HTML
    )
    return QAS_ADD_TASK_PATTERN_SET


async def qas_add_task_ai_generate_pattern_replace_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.effective_message.reply_text(
        text="🤖 AI 根据分享链接中的文件内容生成正则中..."
    )
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
    params = await qas.ai_generate_params(
        url=context.user_data['qas_add_task']['shareurl'],
        session=session,
        user_id=user.id,
        prompt={context.user_data['qas_add_task']['ai_generate_pattern_texts'][update.callback_query.data.split(':')[1]]}
    )
    context.user_data['qas_add_task']['ai_params'] = params

    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Pattern</b>：\n<b>默认 Pattern</b>：<code>{context.user_data['qas_add_task']['pattern']}</code>\n<b>AI 生成 Pattern</b>：<code>{context.user_data['qas_add_task']['ai_params']['pattern']}</code>\n",
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
                InlineKeyboardButton(f"通过AI生成Pattern",
                                     callback_data=f"qas_add_task_ai_generate_pattern_button:")
            ],
            [
                InlineKeyboardButton(f"❌ 取消新增操作", callback_data=f"cancel_qas_update_task")
            ]
        ]),
        parse_mode=ParseMode.HTML
    )
    return QAS_ADD_TASK_PATTERN_SET



async def qas_add_task_pattern_ask_replace(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    params = context.user_data['qas_add_task'].get('ai_params')
    if params:
        await update.effective_message.reply_text(
            text=f"请输入或选择 <b>Replace</b>：\n默认 Replace: <code>{context.user_data['qas_add_task']['replace']}</code>\nAI生成 Replace：<code>{params.get('replace')}</code>",
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
    else:
        await update.effective_message.reply_text(
            text=f"请输入或选择 <b>Replace</b>：\n默认 Replace: <code>{context.user_data['qas_add_task']['replace']}</code>\n",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"默认 Replace", callback_data=f"qas_add_task_replace_button:")
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

    return await qas_add_task_ask_ignore_extension(update, context, session, user)


async def qas_add_task_ask_ignore_extension(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.effective_message.reply_text(
        text="是否忽略后缀名匹配：",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton(f"忽略后缀名 ✅", callback_data=f"qas_add_task_ignore_extension_button:true")
            ],
            [
                InlineKeyboardButton(f"不忽略后缀名 ❌", callback_data=f"qas_add_task_ignore_extension_button:false")
            ]
        ])
    )
    return QAS_ADD_TASK_IGNORE_EXTENSION_SET


async def qas_add_task_ignore_extension_set_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, ignore_extension = update.callback_query.data.split(':')
    if ignore_extension == 'false':
        context.user_data['qas_add_task']['ignore_extension'] = False
        await update.effective_message.reply_text(f"不忽略后缀名 ❌")
    else:
        context.user_data['qas_add_task']['ignore_extension'] = True
        await update.effective_message.reply_text(f"忽略后缀名 ✅")

    return await qas_add_task_finish(update, context, session, user)


async def qas_add_task_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    async def qas_add_task(qas_instance, qas_config_instance, task_name: str, share_url: str, save_path: str, pattern: str, replace: str, aria2: bool, ignore_extension: bool, update: Update, context: ContextTypes.DEFAULT_TYPE):
        data = await qas_instance.add_job(
            host=qas_config_instance.host,
            task_name=task_name,
            share_url=share_url,
            save_path=save_path,
            pattern=pattern,
            replace=replace
        )

        if data:
            save_path = data.get('data').get('savepath')
            # 修改 aria2 和 ignore_extension
            data = await qas_instance.data(host=qas_config_instance.host)
            for index, task in enumerate(data.get("tasklist", [])):
                if task.get("savepath") == save_path:
                    data["tasklist"][index]['ignore_extension'] = ignore_extension
                    if aria2 is False:
                        data["tasklist"][index]["addition"]["aria2"]["auto_download"] = False
                    else:
                        data["tasklist"][index]["addition"]["aria2"]["auto_download"] = True
                    break
            await qas_instance.update(host=qas_config_instance.host, data=data)
            message = f"""
新增任务成功：
📌 <b>任务名称</b>：{data['tasklist'][index]['taskname']}
📁 <b>保存路径</b>：<code>{data['tasklist'][index]['savepath']}</code>
🔗 <b>分享链接</b>：<a href="{data['tasklist'][index]['shareurl']}">点我打开</a>
🎯 <b>匹配规则</b>：<code>{data['tasklist'][index]['pattern']}</code>
🔁 <b>替换模板</b>：<code>{data['tasklist'][index]['replace']}</code>

📦 <b>扩展设置</b>：
- 🧲 <b>Aria2 自动下载</b>：{"✅ 开启" if data['tasklist'][index]["addition"]["aria2"]["auto_download"] else "❌ 关闭"}
- 📄 <b>忽略后缀名</b>：{"✅ 开启" if data['tasklist'][index].get("ignore_extension") else "❌ 关闭"}
- 🧬 <b>Emby 匹配</b>：{"✅ 开启" if data['tasklist'][index]["addition"].get("emby", {}).get("try_match") else "❌ 关闭"}（Media ID: {data['tasklist'][index]["addition"].get("emby", {}).get("media_id", "")}）

🌐 <a href="{qas_config_instance.host}"><b>你的 QAS 服务</b></a>
                        """
            await update.effective_message.reply_text(
                text=message,
                parse_mode="html",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton(f"▶️ 运行此任务", callback_data=f"qas_run_script:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"📁 标记开始文件", callback_data=f"qas_tag_start_file:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🗑️ 删除对应路径云盘文件", callback_data=f"qas_delete_cloud_files:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🔧 修复资源链接", callback_data=f"qas_fix_link:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🛠️ 更新此任务", callback_data=f"qas_update_task:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🗑 删除此任务", callback_data=f"qas_delete_task:{index}")
                    ]
                ])
            )

        else:
            await update.effective_message.reply_text(
                text=f"添加任务{task_name}失败❌"
            )
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)

    if context.user_data['qas_add_task']['is_multi_seasons'] is True:
        await update.effective_message.reply_text(
            text=f"Ai分类季数中，请稍等"
        )
        seasons_fid, extract_seasons = await qas.ai_classify_seasons(context.user_data['qas_add_task']['shareurl'], session=session, user_id=user.id)
        await update.effective_message.reply_text(
            text=f"""
Ai识别季数完成，识别结果为：

<code>{json.dumps(extract_seasons, indent=2, ensure_ascii=False)}</code>

，即将创建任务""",
            parse_mode="html",
        )
        for season, fid in seasons_fid.items():
            season_num = await QuarkAutoDownload.extract_all_two_digit_numbers(season)
            replace = f"S{season_num[0]}E{{E}}.{{EXT}}"
            await qas_add_task(
                qas_instance=qas,
                qas_config_instance=qas_config,
                task_name=context.user_data['qas_add_task']['taskname'] + f" ({season})",
                share_url=context.user_data['qas_add_task']['quark_share_url_origin'] + fid,
                save_path=os.path.join(context.user_data['qas_add_task']['savepath'], season),
                pattern=context.user_data['qas_add_task']['pattern'],
                replace=replace,
                aria2=context.user_data['qas_add_task']['addition'].get('aria2', {}).get('auto_download', True),
                ignore_extension=context.user_data['qas_add_task'].get('ignore_extension', True),
                update=update,
                context=context
            )
    else:
        await qas_add_task(
            qas_instance=qas,
            qas_config_instance=qas_config,
            task_name=context.user_data['qas_add_task']['taskname'],
            share_url=context.user_data['qas_add_task']['shareurl'],
            save_path=context.user_data['qas_add_task']['savepath'],
            pattern=context.user_data['qas_add_task']['pattern'],
            replace=context.user_data['qas_add_task']['replace'],
            aria2=context.user_data['qas_add_task']['addition'].get('aria2', {}).get('auto_download', True),
            ignore_extension=context.user_data['qas_add_task'].get('ignore_extension', True),
            update=update,
            context=context
        )

    context.user_data.pop("qas_add_task")

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

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
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
📌 <b>任务名称</b>：{task.get('taskname', '未知')}
📁 <b>保存路径</b>：{task.get('savepath', '未知')}
🔗 <b>分享链接</b>：<a href="{task.get('shareurl')}">点我打开</a>
🎯 <b>匹配规则</b>：<code>{task.get('pattern', '未设置')}</code>
🔁 <b>替换模板</b>：<code>{task.get('replace', '未设置')}</code>
🧲 <b>Aria2 自动下载</b>：{"✅ 开启" if task.get('addition', {}).get('aria2', {}).get('auto_download') else "❌ 关闭"}
📄 <b>忽略后缀名</b>：{"✅ 开启" if task.get('ignore_extension') else "❌ 关闭"}
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
                        InlineKeyboardButton(f"📁 标记开始文件", callback_data=f"qas_tag_start_file:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🗑️ 删除对应路径云盘文件", callback_data=f"qas_delete_cloud_files:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🔧 修复资源链接", callback_data=f"qas_fix_link:{index}")
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


@command(name='qas_list_err_task', description="列出 QAS 异常任务", args="{任务名称}")
async def qas_list_err_task(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
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

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
    data = await qas.data(host=qas_config.host)
    task_list = [task for task in data.get("tasklist", []) if task.get('shareurl_ban')]

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
📌 <b>任务名称</b>：{task.get('taskname', '未知')}
📁 <b>保存路径</b>：{task.get('savepath', '未知')}
🔗 <b>分享链接</b>：<a href="{task.get('shareurl')}">点我打开</a>
🎯 <b>匹配规则</b>：<code>{task.get('pattern', '未设置')}</code>
🔁 <b>替换模板</b>：<code>{task.get('replace', '未设置')}</code>
🧲 <b>Aria2 自动下载</b>：{"✅ 开启" if task.get('addition', {}).get('aria2', {}).get('auto_download') else "❌ 关闭"}
📄 <b>忽略后缀名</b>：{"✅ 开启" if task.get('ignore_extension') else "❌ 关闭"}
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
                        InlineKeyboardButton(f"📁 标记开始文件", callback_data=f"qas_tag_start_file:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🗑️ 删除对应路径云盘文件", callback_data=f"qas_delete_cloud_files:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{index}")
                    ],
                    [
                        InlineKeyboardButton(f"🔧 修复资源链接", callback_data=f"qas_fix_link:{index}")
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
        return

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    qas = QuarkAutoDownload(api_token=api_token)
    data = await qas.data(host=qas_config.host)
    task_info = data.get("tasklist", [])[task_id]

    # 保存原始任务信息
    context.user_data.update({
        'qas_update_task_original': task_info.copy(),
        'qas_update_task': {'id': task_id},
        'qas_update_task_edit_data': {}
    })

    # 显示任务信息并让用户选择要修改的字段
    keyboard = [
        [InlineKeyboardButton("🔗 分享链接", callback_data="qas_task_update_share_url")],
        [InlineKeyboardButton("📁 保存路径", callback_data="qas_task_update_savepath")],
        [InlineKeyboardButton("🎯 Pattern", callback_data="qas_task_update_pattern")],
        [InlineKeyboardButton("🔄 Replace", callback_data="qas_task_update_replace")],
        [InlineKeyboardButton("🧲 Aria2 设置", callback_data="qas_task_update_aria2")],
        [InlineKeyboardButton("📄 忽略后缀名", callback_data="qas_task_update_ignore_extension")],
        [InlineKeyboardButton("✅ 完成更新", callback_data="qas_task_update_finish")],
        [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
    ]

    message = f"""
<b>当前任务信息：</b>
🆔 <b>ID：</b> {task_id}
📌 <b>任务名称：</b> {task_info.get('taskname')}
📁 <b>保存路径：</b> <code>{task_info.get('savepath')}</code>
🔗 <b>分享链接：</b> <a href="{task_info.get('shareurl')}">点我查看</a>
🎯 <b>Pattern：</b> <code>{task_info.get('pattern')}</code>
🔄 <b>Replace：</b> <code>{task_info.get('replace')}</code>
🧲 <b>Aria2 自动下载：</b> {"✅ 开启" if task_info.get('addition', {}).get('aria2', {}).get('auto_download') else "❌ 关闭"}
📄 <b>忽略后缀名：</b> {"✅ 开启" if task_info.get('ignore_extension') else "❌ 关闭"}

请选择要修改的字段：
    """

    await update.effective_message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="html"
    )
    return QAS_TASK_UPDATE_FIELD_SELECT


# QAS 任务部分更新相关函数
async def qas_task_update_field_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    action = query.data

    if action == "qas_task_update_finish":
        # 完成更新，准备保存
        return await qas_task_update_finish(update, context, session, user)
    elif action == "qas_task_update_share_url":
        # 修改分享链接
        context.user_data["qas_update_current_field"] = QAS_TASK_UPDATE_SHARE_URL
        await update.effective_message.reply_text(
            "请输入新的分享链接：",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")
            ]])
        )
        return QAS_TASK_UPDATE_SHARE_URL
    elif action == "qas_task_update_savepath":
        # 修改保存路径
        original_task = context.user_data.get("qas_update_task_original", {})
        current_savepath = original_task.get('savepath')

        context.user_data["qas_update_current_field"] = QAS_TASK_UPDATE_SAVEPATH
        await update.effective_message.reply_text(
            f"请输入新的保存路径：\n<b>当前保存路径</b>: <code>{current_savepath}</code>",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")
            ]]),
            parse_mode="html"
        )
        return QAS_TASK_UPDATE_SAVEPATH
    elif action == "qas_task_update_pattern":
        # 修改Pattern
        original_task = context.user_data.get("qas_update_task_original", {})
        qas_config = session.query(QuarkAutoDownloadConfig).filter(
            QuarkAutoDownloadConfig.user_id == user.id
        ).first()

        # 获取当前任务的分享链接
        share_url = original_task.get('shareurl')

        await update.effective_message.reply_text(
            f"请输入或选择 <b>Pattern</b>：\n"
            f"<b>当前Pattern</b>: <code>{original_task.get('pattern')}</code>\n"
            f"<b>默认Pattern</b>: <code>{qas_config.pattern}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("保留当前Pattern", callback_data="qas_task_update_pattern_keep")],
                [InlineKeyboardButton("使用默认Pattern", callback_data="qas_task_update_pattern_default")],
                [InlineKeyboardButton("通过AI生成Pattern", callback_data="qas_task_update_ai_generate_pattern")],
                [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
            ]),
            parse_mode="html"
        )
        return QAS_TASK_UPDATE_PATTERN
    elif action == "qas_task_update_replace":
        # 修改Replace
        original_task = context.user_data.get("qas_update_task_original", {})
        qas_config = session.query(QuarkAutoDownloadConfig).filter(
            QuarkAutoDownloadConfig.user_id == user.id
        ).first()

        # 获取当前任务的分享链接
        share_url = original_task.get('shareurl')

        await update.effective_message.reply_text(
            f"请输入或选择 <b>Replace</b>：\n"
            f"<b>当前Replace</b>: <code>{original_task.get('replace')}</code>\n"
            f"<b>默认Replace</b>: <code>{qas_config.replace}</code>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("保留当前Replace", callback_data="qas_task_update_replace_keep")],
                [InlineKeyboardButton("使用默认Replace", callback_data="qas_task_update_replace_default")],
                [InlineKeyboardButton("通过AI生成Replace", callback_data="qas_task_update_ai_generate_replace")],
                [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
            ]),
            parse_mode="html"
        )
        return QAS_TASK_UPDATE_REPLACE
    elif action == "qas_task_update_aria2":
        # 修改Aria2设置
        original_task = context.user_data.get("qas_update_task_original", {})
        current_status = original_task.get('addition', {}).get('aria2', {}).get('auto_download', False)

        await update.effective_message.reply_text(
            "请选择 Aria2 自动下载设置：",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ 开启", callback_data="qas_task_update_aria2_enable")],
                [InlineKeyboardButton("❌ 关闭", callback_data="qas_task_update_aria2_disable")],
                [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
            ])
        )
        return QAS_TASK_UPDATE_ARIA2
    elif action == "qas_task_update_ignore_extension":
        # 修改忽略后缀名设置
        original_task = context.user_data.get("qas_update_task_original", {})
        current_status = original_task.get('ignore_extension', False)

        await update.effective_message.reply_text(
            f"当前忽略后缀名设置：{'✅ 开启' if current_status else '❌ 关闭'}\n请选择忽略后缀名设置：",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ 开启", callback_data="qas_task_update_ignore_extension_enable")],
                [InlineKeyboardButton("❌ 关闭", callback_data="qas_task_update_ignore_extension_disable")],
                [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
            ])
        )
        return QAS_TASK_UPDATE_IGNORE_EXTENSION


async def qas_task_update_share_url_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理分享链接输入"""
    if not update.message:
        return

    await update.message.reply_text(text='解析分享链接中，请稍后')

    quark_share_url = update.message.text
    if not quark_share_url.endswith('/'):
        quark_share_url += '/'

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    qas = QuarkAutoDownload(api_token=api_token)
    fid_files = await qas.get_fid_files(quark_share_url)
    if not fid_files:
        await update.message.reply_text("链接状态异常，请重新输入")
        return

    tree_paragraphs = await qas.get_tree_paragraphs(fid_files)
    for _ in tree_paragraphs:
        file_name = _.split('\n')[0].split('__')[0]
        fid = _.split('\n')[0].split('__')[1]
        url = quark_share_url + fid
        tmp_url_id = get_random_letter_number_id()
        context.user_data[tmp_url_id] = url
        await update.message.reply_text(
            text=_,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton(f"选择 {file_name}", callback_data=f"qas_task_update_share_url_select:{tmp_url_id}")
            ]])
        )
    return QAS_TASK_UPDATE_SHARE_URL


async def qas_task_update_share_url_select(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理分享链接选择"""
    query = update.callback_query
    await query.answer()
    tmp_url_id = query.data.split(':')[1]
    selected_url = context.user_data[tmp_url_id]

    # 保存编辑的数据
    context.user_data['qas_update_task_edit_data']['shareurl'] = selected_url

    await update.effective_message.reply_text(f"分享链接已更新为：{selected_url}")
    return await qas_task_update_show_menu(update, context, session, user)


async def qas_task_update_ai_generate_pattern(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理通过AI生成Pattern的交互式逻辑"""
    query = update.callback_query
    await query.answer()

    original_task = context.user_data.get("qas_update_task_original", {})
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    # 获取当前任务的分享链接
    share_url = original_task.get('shareurl')

    if not share_url:
        await update.effective_message.reply_text("无法获取分享链接，无法使用AI生成功能")
        return await qas_task_update_show_menu(update, context, session, user)

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    qas = QuarkAutoDownload(api_token=api_token)
    quark_id, stoken, pdir_fid = await qas.get_quark_id_stoken_pdir_fid(url=share_url)
    dir_details = await qas.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False)

    files_text = '\n'.join([
        f"🎥 {dir_detail['file_name']}"
        for dir_detail in dir_details[:15]
    ])

    await update.effective_message.reply_text(
        text=f'📁 <a href="{share_url}">分享链接</a> 中的文件列表：\n\n{files_text}\n\n💡 请描述你希望匹配的文件类型或特征：',
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([
            [
               InlineKeyboardButton(f"文件名中带 4K 的文件",
                                    callback_data=f"qas_task_update_ai_generate_param_button:filename_with_4k")
           ],
           [
               InlineKeyboardButton(f"❌ 取消更新操作",
                                    callback_data="cancel_qas_update_task")
           ]
        ])
    )

    return QAS_TASK_UPDATE_PATTERN_GENERATE


async def qas_task_update_ai_generate_pattern_replace_text(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理AI生成Pattern的文本输入"""
    await update.effective_message.reply_text(
        text="🤖 AI 根据分享链接中的文件内容生成正则中..."
    )

    original_task = context.user_data.get("qas_update_task_original", {})
    edit_data = context.user_data.get("qas_update_task_edit_data", {})

    share_url = edit_data.get("shareurl", original_task.get("shareurl"))

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    qas = QuarkAutoDownload(api_token=api_token)
    params = await qas.ai_generate_params(
        url=share_url,
        session=session,
        user_id=user.id,
        prompt=update.message
    )
    context.user_data['qas_update_task_ai_params'] = params

    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Pattern</b>：\n"
        f"<b>当前Pattern</b>: <code>{original_task.get('pattern')}</code>\n"
        f"<b>默认Pattern</b>: <code>{qas_config.pattern}</code>\n"
        f"<b>AI生成Pattern</b>: <code>{params.get('pattern')}</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("保留当前Pattern", callback_data="qas_task_update_pattern_keep")],
            [InlineKeyboardButton("使用默认Pattern", callback_data="qas_task_update_pattern_default")],
            [InlineKeyboardButton("AI生成Pattern", callback_data="qas_task_update_pattern_ai")],
            [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
        ]),
        parse_mode="html"
    )
    return QAS_TASK_UPDATE_PATTERN


async def qas_task_update_ai_generate_pattern_replace_button(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理AI生成Pattern的按钮点击"""
    await update.effective_message.reply_text(
        text="🤖 AI 根据分享链接中的文件内容生成正则中..."
    )

    original_task = context.user_data.get("qas_update_task_original", {})
    edit_data = context.user_data.get("qas_update_task_edit_data", {})

    share_url = edit_data.get("shareurl", original_task.get("shareurl"))

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    qas = QuarkAutoDownload(api_token=api_token)

    # 使用预定义的文本选项
    ai_generate_pattern_texts = {
        'filename_with_4k': '文件名中带 4K 的文件'
    }

    params = await qas.ai_generate_params(
        url=share_url,
        session=session,
        user_id=user.id,
        prompt=ai_generate_pattern_texts[update.callback_query.data.split(':')[1]]
    )
    context.user_data['qas_update_task_ai_params'] = params

    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Pattern</b>：\n"
        f"<b>当前Pattern</b>: <code>{original_task.get('pattern')}</code>\n"
        f"<b>默认Pattern</b>: <code>{qas_config.pattern}</code>\n"
        f"<b>AI生成Pattern</b>: <code>{params.get('pattern')}</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("保留当前Pattern", callback_data="qas_task_update_pattern_keep")],
            [InlineKeyboardButton("使用默认Pattern", callback_data="qas_task_update_pattern_default")],
            [InlineKeyboardButton("AI生成Pattern", callback_data="qas_task_update_pattern_ai")],
            [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
        ]),
        parse_mode="html"
    )
    return QAS_TASK_UPDATE_PATTERN


async def qas_task_update_ai_generate_replace(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """直接通过AI生成Replace，无需交互"""
    query = update.callback_query
    await query.answer()

    original_task = context.user_data.get("qas_update_task_original", {})
    edit_data = context.user_data.get("qas_update_task_edit_data", {})

    share_url = edit_data.get("shareurl", original_task.get("shareurl"))
    current_pattern = edit_data.get("pattern", original_task.get("pattern"))
    replace = edit_data.get("replace", original_task.get("replace"))

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    if not share_url:
        await update.effective_message.reply_text("无法获取分享链接，无法使用AI生成功能")
        return await qas_task_update_show_menu(update, context, session, user)

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    await update.effective_message.reply_text(
        text="🤖 AI 根据文件列表和当前Pattern生成Replace中..."
    )

    qas = QuarkAutoDownload(api_token=api_token)
    quark_id, stoken, pdir_fid = await qas.get_quark_id_stoken_pdir_fid(url=share_url)
    dir_details = await qas.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False)

    files_text = '\n'.join([
        f"🎥 {dir_detail['file_name']}"
        for dir_detail in dir_details[:15]
    ])

    # 构建AI提示，告诉AI根据文件列表和当前Pattern生成合适的Replace
    prompt = f"根据当前Pattern {current_pattern} 匹配到的文件，生成相应的Replace替换模板，确保Replace模板能与Pattern匹配到的文件名格式相对应。"

    params = await qas.ai_generate_replace(
        url=share_url,
        session=session,
        user_id=user.id,
        prompt=prompt
    )
    context.user_data['qas_update_task_ai_params'] = params

    # 直接显示选择界面，让用户选择是否使用AI生成的Replace
    await update.effective_message.reply_text(
        text=f"请输入或选择 <b>Replace</b>：\n"
        f"<b>当前Pattern</b>: <code>{current_pattern}</code>\n"
        f"<b>当前Replace</b>: <code>{original_task.get('replace')}</code>\n"
        f"<b>默认Replace</b>: <code>{qas_config.replace}</code>\n"
        f"<b>AI生成Replace</b>: <code>{params.get('replace')}</code>",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("保留当前Replace", callback_data="qas_task_update_replace_keep")],
            [InlineKeyboardButton("使用默认Replace", callback_data="qas_task_update_replace_default")],
            [InlineKeyboardButton("AI生成Replace", callback_data="qas_task_update_replace_ai")],
            [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
        ]),
        parse_mode="html"
    )
    return QAS_TASK_UPDATE_REPLACE




async def qas_task_update_pattern_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理Pattern设置"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        action = query.data

        if action == "qas_task_update_pattern_keep":
            # 保留当前Pattern，不需要修改
            pass
        elif action == "qas_task_update_pattern_default":
            qas_config = session.query(QuarkAutoDownloadConfig).filter(
                QuarkAutoDownloadConfig.user_id == user.id
            ).first()
            context.user_data['qas_update_task_edit_data']['pattern'] = qas_config.pattern
            await update.effective_message.reply_text(f"Pattern已设置为默认值：{qas_config.pattern}")
        elif action == "qas_task_update_pattern_ai":
            # 使用AI生成的Pattern
            ai_params = context.user_data.get('qas_update_task_ai_params', {})
            ai_pattern = ai_params.get('pattern')
            if ai_pattern:
                context.user_data['qas_update_task_edit_data']['pattern'] = ai_pattern
                await update.effective_message.reply_text(f"Pattern已使用AI生成值：{ai_pattern}")
            else:
                await update.effective_message.reply_text("AI生成Pattern失败，请重试或选择其他选项")
                return
        else:
            # 自定义输入
            return
    else:
        # 文本输入
        context.user_data['qas_update_task_edit_data']['pattern'] = update.message.text
        await update.message.reply_text(f"Pattern已更新为：{update.message.text}")

    return await qas_task_update_show_menu(update, context, session, user)


async def qas_task_update_replace_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理Replace设置"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        action = query.data

        if action == "qas_task_update_replace_keep":
            # 保留当前Replace，不需要修改
            pass
        elif action == "qas_task_update_replace_default":
            qas_config = session.query(QuarkAutoDownloadConfig).filter(
                QuarkAutoDownloadConfig.user_id == user.id
            ).first()
            context.user_data['qas_update_task_edit_data']['replace'] = qas_config.replace
            await update.effective_message.reply_text(f"Replace已设置为默认值：{qas_config.replace}")
        elif action == "qas_task_update_replace_ai":
            # 使用AI生成的Replace
            ai_params = context.user_data.get('qas_update_task_ai_params', {})
            ai_replace = ai_params.get('replace')
            if ai_replace:
                context.user_data['qas_update_task_edit_data']['replace'] = ai_replace
                await update.effective_message.reply_text(f"Replace已使用AI生成值：{ai_replace}")
            else:
                await update.effective_message.reply_text("AI生成Replace失败，请重试或选择其他选项")
                return
        else:
            # 自定义输入
            return
    else:
        # 文本输入
        context.user_data['qas_update_task_edit_data']['replace'] = update.message.text
        await update.message.reply_text(f"Replace已更新为：{update.message.text}")

    return await qas_task_update_show_menu(update, context, session, user)


async def qas_task_update_aria2_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理Aria2设置"""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "qas_task_update_aria2_enable":
        context.user_data['qas_update_task_edit_data']['aria2_auto_download'] = True
        await update.effective_message.reply_text("Aria2 自动下载已开启")
    elif action == "qas_task_update_aria2_disable":
        context.user_data['qas_update_task_edit_data']['aria2_auto_download'] = False
        await update.effective_message.reply_text("Aria2 自动下载已关闭")

    return await qas_task_update_show_menu(update, context, session, user)


async def qas_task_update_ignore_extension_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理忽略后缀名设置"""
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "qas_task_update_ignore_extension_enable":
        context.user_data['qas_update_task_edit_data']['ignore_extension'] = True
        await update.effective_message.reply_text("忽略后缀名已开启")
    elif action == "qas_task_update_ignore_extension_disable":
        context.user_data['qas_update_task_edit_data']['ignore_extension'] = False
        await update.effective_message.reply_text("忽略后缀名已关闭")

    return await qas_task_update_show_menu(update, context, session, user)


async def qas_task_update_savepath_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理保存路径设置"""
    if not update.message:
        return

    savepath = update.message.text
    # 确保路径以 / 开头
    if not savepath.startswith('/'):
        savepath = '/' + savepath

    # 保存编辑的数据
    context.user_data['qas_update_task_edit_data']['savepath'] = savepath
    await update.message.reply_text(f"保存路径已更新为：{savepath}")
    return await qas_task_update_show_menu(update, context, session, user)


async def qas_task_update_show_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """显示更新菜单"""
    original_task = context.user_data.get("qas_update_task_original", {})
    task_id = context.user_data.get("qas_update_task", {}).get('id')
    edit_data = context.user_data.get("qas_update_task_edit_data", {})

    # 显示当前配置和已修改的字段
    share_url = edit_data.get("shareurl", original_task.get("shareurl"))
    savepath = edit_data.get("savepath", original_task.get("savepath"))
    pattern = edit_data.get("pattern", original_task.get("pattern"))
    replace = edit_data.get("replace", original_task.get("replace"))
    aria2_auto_download = edit_data.get("aria2_auto_download", original_task.get("addition", {}).get("aria2", {}).get("auto_download", False))
    ignore_extension = edit_data.get("ignore_extension", original_task.get("ignore_extension", False))

    keyboard = [
        [InlineKeyboardButton("🔗 分享链接", callback_data="qas_task_update_share_url")],
        [InlineKeyboardButton("📁 保存路径", callback_data="qas_task_update_savepath")],
        [InlineKeyboardButton("🎯 Pattern", callback_data="qas_task_update_pattern")],
        [InlineKeyboardButton("🔄 Replace", callback_data="qas_task_update_replace")],
        [InlineKeyboardButton("🧲 Aria2 设置", callback_data="qas_task_update_aria2")],
        [InlineKeyboardButton("📄 忽略后缀名", callback_data="qas_task_update_ignore_extension")],
        [InlineKeyboardButton("✅ 完成更新", callback_data="qas_task_update_finish")],
        [InlineKeyboardButton("❌ 取消更新", callback_data="cancel_qas_update_task")]
    ]

    message = f"""
<b>任务更新状态：</b>
🆔 <b>ID：</b> {task_id}
📌 <b>任务名称：</b> {original_task.get('taskname')}
📁 <b>保存路径：</b> <code>{savepath}</code>
🔗 <b>分享链接：</b> <a href="{share_url}">点我查看</a>
🎯 <b>Pattern：</b> <code>{pattern}</code>
🔄 <b>Replace：</b> <code>{replace}</code>
🧲 <b>Aria2 自动下载：</b> {"✅ 开启" if aria2_auto_download else "❌ 关闭"}
📄 <b>忽略后缀名：</b> {"✅ 开启" if ignore_extension else "❌ 关闭"}

请选择要修改的字段：
    """

    await update.effective_message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="html"
    )
    return QAS_TASK_UPDATE_FIELD_SELECT


async def qas_task_update_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """完成任务更新"""
    query = update.callback_query
    await query.answer()

    task_id = context.user_data['qas_update_task']['id']
    original_task = context.user_data.get("qas_update_task_original", {})
    edit_data = context.user_data.get("qas_update_task_edit_data", {})

    if not edit_data:
        await update.effective_message.reply_text("没有进行任何修改")
        return ConversationHandler.END

    # 构建更新数据
    update_data = original_task.copy()

    # 只更新用户修改过的字段
    if "shareurl" in edit_data:
        update_data["shareurl"] = edit_data["shareurl"]
    if "savepath" in edit_data:
        update_data["savepath"] = edit_data["savepath"]
    if "pattern" in edit_data:
        update_data["pattern"] = edit_data["pattern"]
    if "replace" in edit_data:
        update_data["replace"] = edit_data["replace"]
    if "aria2_auto_download" in edit_data:
        if "addition" not in update_data:
            update_data["addition"] = {}
        if "aria2" not in update_data["addition"]:
            update_data["addition"]["aria2"] = {}
        update_data["addition"]["aria2"]["auto_download"] = edit_data["aria2_auto_download"]
    if "ignore_extension" in edit_data:
        update_data["ignore_extension"] = edit_data["ignore_extension"]

    # 调用API更新任务
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return ConversationHandler.END

    qas = QuarkAutoDownload(api_token=api_token)

    data = await qas.data(host=qas_config.host)

    for index, task in enumerate(data.get("tasklist", [])):
        if index == int(task_id):
            for k, v in update_data.items():
                data['tasklist'][index][k] = v
            if 'id' in data['tasklist'][index]:
                data['tasklist'][index].pop('id')
            if 'ai_params' in data['tasklist'][index]:
                data['tasklist'][index].pop('ai_params')
            if 'shareurl_ban' in data['tasklist'][index]:
                data['tasklist'][index].pop('shareurl_ban')

            data['tasklist'][index]["addition"]["aria2"]["auto_download"] = update_data["addition"]["aria2"]["auto_download"] if update_data["addition"]["aria2"]["auto_download"] else False

            data['tasklist'][index]['startfid'] = ''
            if "ignore_extension" in edit_data:
                data["tasklist"][index]['ignore_extension'] = edit_data["ignore_extension"]
            break
    success = await qas.update(host=qas_config.host, data=data)

    if success:
        # 获取更新后的任务数据
        updated_data = await qas.data(host=qas_config.host)
        updated_task = updated_data['tasklist'][int(task_id)]

        message = f"""
更新任务成功：
📌 <b>任务名称</b>：{updated_task['taskname']}
📁 <b>保存路径</b>：<code>{updated_task['savepath']}</code>
🔗 <b>分享链接</b>：<a href="{updated_task['shareurl']}">点我打开</a>
🎯 <b>匹配规则</b>：<code>{updated_task['pattern']}</code>
🔁 <b>替换模板</b>：<code>{updated_task['replace']}</code>

📦 <b>扩展设置</b>：
- 🧲 <b>Aria2 自动下载</b>：{"✅ 开启" if updated_task["addition"]["aria2"]["auto_download"] else "❌ 关闭"}
- 📄 <b>忽略后缀名</b>：{"✅ 开启" if updated_task.get("ignore_extension") else "❌ 关闭"}
- 🧬 <b>Emby 匹配</b>：{"✅ 开启" if updated_task["addition"].get("emby", {}).get("try_match") else "❌ 关闭"}（Media ID: {updated_task["addition"].get("emby", {}).get("media_id", "")}）

🌐 <a href="{qas_config.host}"><b>你的 QAS 服务</b></a>
        """
        await update.effective_message.reply_text(
            text=message,
            parse_mode="html",
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton(f"▶️ 运行此任务", callback_data=f"qas_run_script:{task_id}")
                ],
                [
                    InlineKeyboardButton(f"📁 标记开始文件", callback_data=f"qas_tag_start_file:{task_id}")
                ],
                [
                    InlineKeyboardButton(f"🗑️ 删除对应路径云盘文件", callback_data=f"qas_delete_cloud_files:{task_id}")
                ],
                [
                    InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{task_id}")
                ],
                [
                    InlineKeyboardButton(f"🔧 修复资源链接", callback_data=f"qas_fix_link:{task_id}")
                ],
                [
                    InlineKeyboardButton(f"🛠️ 更新此任务", callback_data=f"qas_update_task:{task_id}")
                ],
                [
                    InlineKeyboardButton(f"🗑 删除此任务", callback_data=f"qas_delete_task:{task_id}")
                ]
            ])
        )
    else:
        await update.effective_message.reply_text("❌ 任务更新失败，请检查配置")

    # 清理数据
    context.user_data.pop("qas_update_task_original", None)
    context.user_data.pop("qas_update_task", None)
    context.user_data.pop("qas_update_task_edit_data", None)

    return ConversationHandler.END


# ==================== 修复资源链接 ====================

async def qas_fix_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """修复资源链接入口"""
    query = update.callback_query
    await query.answer(text="修复资源链接")
    task_id = int(query.data.split(':')[1])

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    if not qas_config:
        await update.effective_message.reply_text("尚未添加 QAS 配置，请使用 /upsert_configuration 命令进行配置")
        return ConversationHandler.END

    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return ConversationHandler.END

    qas = QuarkAutoDownload(api_token=api_token)
    data = await qas.data(host=qas_config.host)
    task_info = data.get("tasklist", [])[task_id]

    context.user_data['qas_fix_link'] = {
        'task_id': task_id,
        'original_task': task_info.copy(),
    }

    await update.effective_message.reply_text(
        f"🔧 <b>修复资源链接</b>\n\n"
        f"📌 <b>任务名称：</b>{task_info.get('taskname')}\n"
        f"🔗 <b>当前链接：</b><a href=\"{task_info.get('shareurl')}\">点我查看</a>\n\n"
        f"请输入新的分享链接：",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ 取消", callback_data="cancel_qas_fix_link")
        ]]),
        parse_mode="html"
    )
    return QAS_FIX_LINK_INPUT_URL


async def qas_fix_link_url_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理新链接输入"""
    if not update.message:
        return

    await update.message.reply_text(text='解析分享链接中，请稍后')

    quark_share_url = update.message.text.strip()
    if not quark_share_url.endswith('/'):
        quark_share_url += '/'

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.message.reply_text("无法解密QAS API令牌，请重新配置")
        return ConversationHandler.END

    qas = QuarkAutoDownload(api_token=api_token)
    fid_files = await qas.get_fid_files(quark_share_url)
    if not fid_files:
        await update.message.reply_text(
            "链接状态异常，请重新输入：",
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ 取消", callback_data="cancel_qas_fix_link")
            ]])
        )
        return QAS_FIX_LINK_INPUT_URL

    tree_paragraphs = await qas.get_tree_paragraphs(fid_files)
    if tree_paragraphs:
        # AI 分析推荐包含最新集的文件夹
        recommended_fid = None
        recommend_reason = ''
        try:
            result = await qas.ai_recommend_folder(fid_files, session, user.id)
            if result:
                recommended_fid, recommend_reason = result
        except Exception as e:
            logger.warning(f"AI 推荐文件夹失败，不影响正常流程: {e}")

        for _ in tree_paragraphs:
            file_name = _.split('\n')[0].split('__')[0]
            fid = _.split('\n')[0].split('__')[1]
            url = quark_share_url + fid
            tmp_url_id = get_random_letter_number_id()
            context.user_data[tmp_url_id] = url

            # 推荐标记
            is_recommended = recommended_fid and fid == recommended_fid
            recommend_label = f"⭐ 推荐选择 {file_name}" if is_recommended else f"选择 {file_name}"
            text = _
            if is_recommended and recommend_reason:
                text += f"\n\n⭐ <b>AI 推荐</b>：{recommend_reason}"

            await update.message.reply_text(
                text=text,
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(recommend_label, callback_data=f"qas_fix_link_select:{tmp_url_id}")
                ]]),
                parse_mode="html"
            )
        return QAS_FIX_LINK_SELECT_URL

    # 无子目录，直接用当前链接进行 AI 生成
    context.user_data['qas_fix_link']['new_shareurl'] = quark_share_url
    return await _qas_fix_link_ai_generate(update, context, session, user, qas, quark_share_url)


async def qas_fix_link_url_select(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理子目录选择"""
    query = update.callback_query
    await query.answer()
    tmp_url_id = query.data.split(':')[1]
    selected_url = context.user_data.get(tmp_url_id)

    if not selected_url:
        await update.effective_message.reply_text("链接已过期，请重新操作")
        return ConversationHandler.END

    context.user_data['qas_fix_link']['new_shareurl'] = selected_url

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    qas = QuarkAutoDownload(api_token=api_token)

    return await _qas_fix_link_ai_generate(update, context, session, user, qas, selected_url)


async def _qas_fix_link_ai_generate(update, context, session, user, qas, share_url):
    """调用 AI 生成 pattern/replace 并展示确认界面"""
    await update.effective_message.reply_text("🤖 AI 正在生成正则表达式，请稍等...")

    try:
        ai_params = await qas.ai_generate_params(
            url=share_url,
            session=session,
            user_id=user.id,
            prompt="提取视频文件"
        )
        context.user_data['qas_fix_link']['ai_params'] = ai_params

        original_task = context.user_data['qas_fix_link']['original_task']
        await update.effective_message.reply_text(
            f"🤖 <b>AI 生成结果：</b>\n\n"
            f"🎯 <b>Pattern：</b><code>{html.escape(ai_params.get('pattern', ''))}</code>\n"
            f"🔄 <b>Replace：</b><code>{html.escape(ai_params.get('replace', ''))}</code>\n\n"
            f"<b>原任务信息：</b>\n"
            f"📌 <b>任务名称：</b>{original_task.get('taskname')}\n"
            f"📁 <b>保存路径：</b><code>{original_task.get('savepath')}</code>\n"
            f"🔗 <b>新链接：</b><a href=\"{context.user_data['qas_fix_link']['new_shareurl']}\">点我查看</a>\n\n"
            f"确认后将更新链接、Pattern、Replace 并清空开始文件标记，其他配置不变。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ 确认修复", callback_data="qas_fix_link_confirm")],
                [InlineKeyboardButton("🔄 重新生成", callback_data="qas_fix_link_retry")],
                [InlineKeyboardButton("❌ 取消", callback_data="cancel_qas_fix_link")]
            ]),
            parse_mode="html"
        )
        return QAS_FIX_LINK_CONFIRM

    except Exception as e:
        logger.error(f"AI 生成正则失败: {e}")
        await update.effective_message.reply_text(
            f"❌ AI 生成失败：{str(e)}\n\n请重试或取消操作。",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 重试", callback_data="qas_fix_link_retry")],
                [InlineKeyboardButton("❌ 取消", callback_data="cancel_qas_fix_link")]
            ])
        )
        return QAS_FIX_LINK_CONFIRM


async def qas_fix_link_retry(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """重新生成 AI 参数"""
    query = update.callback_query
    await query.answer()

    fix_data = context.user_data.get('qas_fix_link', {})
    share_url = fix_data.get('new_shareurl')
    if not share_url:
        await update.effective_message.reply_text("操作已过期，请重新开始")
        return ConversationHandler.END

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    qas = QuarkAutoDownload(api_token=api_token)

    return await _qas_fix_link_ai_generate(update, context, session, user, qas, share_url)


async def qas_fix_link_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """确认修复，执行更新"""
    query = update.callback_query
    await query.answer()

    fix_data = context.user_data.get('qas_fix_link', {})
    task_id = fix_data.get('task_id')
    new_shareurl = fix_data.get('new_shareurl')
    ai_params = fix_data.get('ai_params', {})

    if not all([task_id is not None, new_shareurl, ai_params]):
        await update.effective_message.reply_text("操作数据不完整，请重新开始")
        context.user_data.pop('qas_fix_link', None)
        return ConversationHandler.END

    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        context.user_data.pop('qas_fix_link', None)
        return ConversationHandler.END

    qas = QuarkAutoDownload(api_token=api_token)
    data = await qas.data(host=qas_config.host)

    # 更新任务
    task = data['tasklist'][task_id]
    task['shareurl'] = new_shareurl
    task['pattern'] = ai_params.get('pattern', '')
    task['replace'] = ai_params.get('replace', '')
    task['startfid'] = ''

    # 清除临时字段
    for key in ['id', 'ai_params', 'shareurl_ban']:
        task.pop(key, None)

    success = await qas.update(host=qas_config.host, data=data)

    if success:
        updated_data = await qas.data(host=qas_config.host)
        updated_task = updated_data['tasklist'][task_id]

        message = (
            f"✅ <b>资源链接修复成功</b>\n\n"
            f"📌 <b>任务名称</b>：{updated_task['taskname']}\n"
            f"📁 <b>保存路径</b>：<code>{updated_task['savepath']}</code>\n"
            f"🔗 <b>分享链接</b>：<a href=\"{updated_task['shareurl']}\">点我打开</a>\n"
            f"🎯 <b>匹配规则</b>：<code>{html.escape(updated_task['pattern'])}</code>\n"
            f"🔁 <b>替换模板</b>：<code>{html.escape(updated_task['replace'])}</code>\n\n"
            f"📦 <b>扩展设置</b>：\n"
            f"- 🧲 <b>Aria2 自动下载</b>：{'✅ 开启' if updated_task.get('addition', {}).get('aria2', {}).get('auto_download') else '❌ 关闭'}\n"
            f"- 📄 <b>忽略后缀名</b>：{'✅ 开启' if updated_task.get('ignore_extension') else '❌ 关闭'}\n"
            f"- 🧬 <b>Emby 匹配</b>：{'✅ 开启' if updated_task.get('addition', {}).get('emby', {}).get('try_match') else '❌ 关闭'}\n\n"
            f"🌐 <a href=\"{qas_config.host}\"><b>你的 QAS 服务</b></a>"
        )
        await update.effective_message.reply_text(
            text=message,
            parse_mode="html",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(f"▶️ 运行此任务", callback_data=f"qas_run_script:{task_id}")],
                [InlineKeyboardButton(f"📁 标记开始文件", callback_data=f"qas_tag_start_file:{task_id}")],
                [InlineKeyboardButton(f"🗑️ 删除对应路径云盘文件", callback_data=f"qas_delete_cloud_files:{task_id}")],
                [InlineKeyboardButton(f"👀 查看任务正则匹配效果", callback_data=f"qas_view_task_regex:{task_id}")],
                [InlineKeyboardButton(f"🔧 修复资源链接", callback_data=f"qas_fix_link:{task_id}")],
                [InlineKeyboardButton(f"🛠️ 更新此任务", callback_data=f"qas_update_task:{task_id}")],
                [InlineKeyboardButton(f"🗑 删除此任务", callback_data=f"qas_delete_task:{task_id}")]
            ])
        )
    else:
        await update.effective_message.reply_text("❌ 修复失败，请检查配置后重试")

    context.user_data.pop('qas_fix_link', None)
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
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
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
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
    data = await qas.data(host=qas_config.host)
    task_name = data['tasklist'][qas_deleted_task_id]['taskname']
    data['tasklist'].pop(int(qas_deleted_task_id))
    await qas.update(host=qas_config.host, data=data)
    await update.effective_message.reply_text(
        text=f"删除 QAS 任务 {task_name} 成功",
    )
    context.user_data['qas_delete_task_id'] = -1
    await query.edit_message_reply_markup(reply_markup=None)


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
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
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
    task = task_list[0]
    if task["addition"]["aria2"]["auto_download"] and get_user_save_space_mode(user) and task["savepath"].startswith(qas_config.movie_save_path_prefix):
        # 检查是否配置了夸克 cookies
        quark_cookies = await get_user_quark_cookies(user)
        if not quark_cookies:
            await update.effective_message.reply_text(
                text="⚠️ 已开启节省网盘空间模式，但未配置夸克网盘 Cookies。\n请使用 /upsert_configuration 命令配置「夸克网盘」Cookies 。",
                parse_mode='html'
            )
            # 跳过删除旧文件的逻辑，继续标记开始文件
        else:
            quark = Quark(cookies=quark_cookies)
            await update.effective_message.reply_text(
                text=f"已开启节省网盘空间设置且此电影任务已开启aria2下载，即将清理 <b> {task.get('savepath')}</b> 下的旧文件",
                parse_mode='html'
            )
            delete_message = f'删除 <b>{task.get("savepath")}</b> 下的旧文件：\n'
            delete_files_fid = list()
            path_file_map = await quark.get_path_file_map(paths=[task.get('savepath')])
            for path, file in path_file_map.items():
                delete_files_fid.append(file['fid'])
                logger.info(f'即将删除 <b>{task.get("savepath")}</b>')
                path_files = await quark.get_quark_clouddrive_files(pdir_fid=file['fid'])
                for idx, path_file in enumerate(path_files):
                    logger.info(f'即将删除 <b>{task.get("savepath")}</b> 的 {path_file["file_name"]}')
                    prefix = '└──' if idx == len(path_files) - 1 else '├──'
                    delete_message += f"{prefix} {path_file["file_name"]}\n"
                    delete_files_fid.append(path_file['fid'])
            if delete_files_fid:
                await quark.delete_files(delete_files_fid)
                await update.effective_message.reply_text(
                    text=delete_message,
                    parse_mode='html'
                )
            # 清理完成后删除对应的 QAS 电影任务
            try:
                qas_task_index = int(context.args[0]) if len(context.args) >= 1 else 0
                qas_task_name = data['tasklist'][qas_task_index]['taskname']
                data['tasklist'].pop(qas_task_index)
                success = await qas.update(host=qas_config.host, data=data)
                if success:
                    await update.effective_message.reply_text(
                        text=f"已删除 QAS 电影任务 {qas_task_name}",
                    )
                else:
                    await update.effective_message.reply_text(
                        text=f"删除 QAS 电影任务 {qas_task_name} 失败",
                    )
            except Exception as exc:
                logger.error(f"删除 QAS 电影任务失败: {exc}")
                await update.effective_message.reply_text(
                    text="删除 QAS 电影任务失败",
                )


async def qas_run_script_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    context.args = [int(query.data.split(":")[1])]
    return await qas_run_script(update, context, session, user)


@command(name='qas_tag_start_file', description="QAS 标记任务开始转存文件", args="{task id}")
async def qas_tag_start_file(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    await update.effective_message.reply_text(
        text="标记任务的开始转存文件"
    )
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)

    await update.effective_message.reply_text(
        text="获取qas任务数据中"
    )

    data = await qas.data(host=qas_config.host)
    if len(context.args) < 1:
        task_list = data["tasklist"]
    else:
        task_list = [data["tasklist"][int(context.args[0])]]
    async with aiohttp.ClientSession() as http_session:
        quark_cookies = await get_user_quark_cookies(user)
        quark = Quark(cookies=quark_cookies)
        for index, task in enumerate(task_list):
            share_url = task.get('shareurl')
            quark_id, stoken, pdir_fid, _ = await quark.get_quark_id_stoken_pdir_fid(url=share_url, session=http_session)
            dir_details = await quark.get_quark_dir_detail(quark_id, stoken, pdir_fid, include_dir=False, size=1)
            latest_timestamp = None
            if isinstance(dir_details, list) and len(dir_details) > 0:
                latest_fid = dir_details[0]['fid']
                if len(context.args) < 1:
                    data['tasklist'][index]['startfid'] = latest_fid
                    latest_timestamp = int(dir_details[0]['l_updated_at'])
                    latest_datetime = datetime.datetime.fromtimestamp(latest_timestamp / 1000, tz=datetime.UTC).astimezone(pytz.timezone(TIME_ZONE))
                    await update.effective_message.reply_text(
                        text=f"即将标记任务 <b>{data['tasklist'][index]['taskname']}</b> 的开始转存文件为 <b>{dir_details[0]['file_name']}</b> ({latest_datetime.strftime('%Y年%m月%d日 %H:%M:%S')})",
                        parse_mode='html'
                    )
                else:
                    data['tasklist'][int(context.args[0])]['startfid'] = latest_fid
                    latest_timestamp = int(dir_details[0]['l_updated_at'])
                    latest_datetime = datetime.datetime.fromtimestamp(latest_timestamp / 1000, tz=datetime.UTC).astimezone(pytz.timezone(TIME_ZONE))
                    await update.effective_message.reply_text(
                        text=f"即将标记任务 <b>{data['tasklist'][int(context.args[0])]['taskname']}</b> 的开始转存文件为 <b>{dir_details[0]['file_name']}</b> ({latest_datetime.strftime('%Y年%m月%d日 %H:%M:%S')})",
                        parse_mode='html'
                    )

        success = await qas.update(host=qas_config.host, data=data)
        if success:
            await update.effective_message.reply_text(
                text="标记完成 ✅"
            )
        else:
            await update.effective_message.reply_text(
                text="标记失败 ❌"
            )


async def qas_tag_start_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    context.args = [int(query.data.split(":")[1])]
    return await qas_tag_start_file(update, context, session, user)


async def qas_delete_cloud_files_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """删除任务对应路径的云盘文件 - 显示确认对话框"""
    query = update.callback_query
    await query.answer()
    task_index = int(query.data.split(":")[1])

    # 获取QAS配置
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()
    if not qas_config:
        await update.effective_message.reply_text("尚未添加 QAS 配置，请使用 /upsert_configuration 命令进行配置")
        return

    # 检查是否配置了夸克 cookies
    quark_cookies = await get_user_quark_cookies(user)
    if not quark_cookies:
        await update.effective_message.reply_text(
            text="⚠️ 未配置夸克网盘 Cookies。\n请使用 /upsert_configuration 命令配置「夸克网盘」Cookies 后再试。",
            parse_mode='html'
        )
        return

    # 获取任务数据
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return

    qas = QuarkAutoDownload(api_token=api_token)
    data = await qas.data(host=qas_config.host)
    task = data['tasklist'][task_index]
    save_path = task.get('savepath')

    await update.effective_message.reply_text(
        text=f"正在查询 <b>{save_path}</b> 下的文件...",
        parse_mode='html'
    )

    # 获取云盘文件列表
    quark = Quark(cookies=quark_cookies)
    try:
        path_file_map = await quark.get_path_file_map(paths=[save_path])
        if not path_file_map or save_path not in path_file_map:
            await update.effective_message.reply_text(
                text=f"❌ 未找到路径 <b>{save_path}</b>",
                parse_mode='html'
            )
            return

        path_files = await quark.get_quark_clouddrive_files(pdir_fid=path_file_map[save_path]['fid'])

        if not path_files:
            await update.effective_message.reply_text(
                text=f"📁 路径 <b>{save_path}</b> 下没有内容",
                parse_mode='html'
            )
            return

        # 构建文件列表消息(显示所有文件和目录)
        file_list_message = f"⚠️ 即将删除 <b>{save_path}</b> 目录及其下的所有内容（共 {len(path_files)} 项）：\n\n"
        for idx, file in enumerate(path_files[:20]):  # 最多显示20个
            prefix = '└──' if idx == len(path_files) - 1 and len(path_files) <= 20 else '├──'
            file_type = '📁' if file['dir'] else '📄'
            file_list_message += f"{prefix} {file_type} {file['file_name']}\n"

        if len(path_files) > 20:
            file_list_message += f"\n... 还有 {len(path_files) - 20} 项未显示"

        file_list_message += f"\n\n⚠️ <b>注意：将删除 {save_path} 目录本身及其所有内容，此操作不可恢复！</b>"

        # 显示确认按钮
        await update.effective_message.reply_text(
            text=file_list_message,
            parse_mode='html',
            reply_markup=InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ 确认删除", callback_data=f"qas_delete_cloud_files_confirm:{task_index}"),
                    InlineKeyboardButton("❌ 取消", callback_data=f"qas_delete_cloud_files_cancel:{task_index}")
                ]
            ])
        )

    except Exception as e:
        await update.effective_message.reply_text(
            text=f"❌ 查询文件失败: {str(e)}",
            parse_mode='html'
        )


async def qas_delete_cloud_files_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """确认删除云盘文件"""
    query = update.callback_query
    await query.answer()
    task_index = int(query.data.split(":")[1])

    # 获取QAS配置
    qas_config = session.query(QuarkAutoDownloadConfig).filter(
        QuarkAutoDownloadConfig.user_id == user.id
    ).first()

    # 获取任务数据
    api_token = get_decrypted_api_token(qas_config)
    qas = QuarkAutoDownload(api_token=api_token)
    data = await qas.data(host=qas_config.host)
    task = data['tasklist'][task_index]
    save_path = task.get('savepath')

    await update.effective_message.reply_text(
        text=f"正在删除 <b>{save_path}</b> 下的文件...",
        parse_mode='html'
    )

    # 获取云盘文件并删除
    quark_cookies = await get_user_quark_cookies(user)
    quark = Quark(cookies=quark_cookies)

    try:
        path_file_map = await quark.get_path_file_map(paths=[save_path])

        # 收集要删除的文件和目录fid
        delete_files_fid = []

        for path, file in path_file_map.items():
            # 先添加父目录的fid
            delete_files_fid.append(file['fid'])

            # 获取目录下的所有文件和子目录
            path_files = await quark.get_quark_clouddrive_files(pdir_fid=file['fid'])
            for path_file in path_files:
                delete_files_fid.append(path_file['fid'])

        if delete_files_fid:
            await quark.delete_files(delete_files_fid)
            await update.effective_message.reply_text(
                text=f"✅ 成功删除 <b>{save_path}</b> 及其下的 {len(delete_files_fid)} 个项目",
                parse_mode='html'
            )
        else:
            await update.effective_message.reply_text(
                text=f"📁 路径 <b>{save_path}</b> 下没有内容",
                parse_mode='html'
            )
    except Exception as e:
        await update.effective_message.reply_text(
            text=f"❌ 删除文件失败: {str(e)}",
            parse_mode='html'
        )


async def qas_delete_cloud_files_cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """取消删除云盘文件"""
    query = update.callback_query
    await query.answer()
    await update.effective_message.reply_text(
        text="❌ 已取消删除操作"
    )


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
    api_token = get_decrypted_api_token(qas_config)
    if not api_token:
        await update.effective_message.reply_text("无法解密QAS API令牌，请重新配置")
        return
    qas = QuarkAutoDownload(api_token=api_token)
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
                InlineKeyboardButton(f"📁 标记开始文件", callback_data=f"qas_tag_start_file:{index}")
            ],
            [
                InlineKeyboardButton(f"🗑️ 删除对应路径云盘文件", callback_data=f"qas_delete_cloud_files:{index}")
            ],
            [
                InlineKeyboardButton(f"🔧 修复资源链接", callback_data=f"qas_fix_link:{index}")
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
            # 部分修改状态
            QAS_EDIT_FIELD_SELECT: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(qas_field_select_handler),
                        pattern=r"^qas_(edit_|finish_).*$"
                )
            ],
            QAS_EDIT_HOST: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(qas_edit_field_set)
                )
            ],
            QAS_EDIT_API_TOKEN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(qas_edit_field_set)
                )
            ],
            QAS_EDIT_SAVE_PATH: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(qas_edit_field_set)
                )
            ],
            QAS_EDIT_MOVIE_PATH: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(qas_edit_field_set)
                )
            ],
            QAS_EDIT_PATTERN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(qas_edit_field_set)
                )
            ],
            QAS_EDIT_REPLACE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(qas_edit_field_set)
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
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_ai_ask_pattern_replace_button),
                        pattern=r"^qas_add_task_ai_generate_pattern_button:.*$"
                )
            ],
            QAS_ADD_TASK_PATTERN_REPLACE_GENERATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_ai_generate_pattern_replace_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_ai_generate_pattern_replace_button),
                        pattern=r"^qas_add_task_ai_generate_pattern_replace_button:.*$"
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
            ],
            QAS_ADD_TASK_IGNORE_EXTENSION_SET: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_ignore_extension_set_button),
                        pattern=r"^qas_add_task_ignore_extension_button:.*$"
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
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_select_tv_multi_seasons),
            pattern=r"^qas_add_task_tv_multi_seasons:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_add_task_select_movie),
            pattern=r"^qas_add_task_movie:.*$"
    ),
    # update qas task (支持部分更新)
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_update_task),
                pattern=r"^qas_update_task:.*$"
            )
        ],
        states={
            # 部分更新状态
            QAS_TASK_UPDATE_FIELD_SELECT: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_field_select_handler),
                        pattern=r"^qas_task_update_.*$"
                )
            ],
            QAS_TASK_UPDATE_SHARE_URL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_share_url_set)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_share_url_select),
                        pattern=r"^qas_task_update_share_url_select:.*$"
                )
            ],
            QAS_TASK_UPDATE_SAVEPATH: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_savepath_set)
                )
            ],
            QAS_TASK_UPDATE_PATTERN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_pattern_set)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_pattern_set),
                        pattern=r"^qas_task_update_pattern_(keep|default|ai)$"
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_ai_generate_pattern),
                        pattern=r"^qas_task_update_ai_generate_pattern$"
                )
            ],
            QAS_TASK_UPDATE_PATTERN_GENERATE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_ai_generate_pattern_replace_text)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_ai_generate_pattern_replace_button),
                        pattern=r"^qas_task_update_ai_generate_param_button:.*$"
                )
            ],
              QAS_TASK_UPDATE_REPLACE: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_replace_set)
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_replace_set),
                        pattern=r"^qas_task_update_replace_(keep|default|ai)$"
                ),
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_ai_generate_replace),
                        pattern=r"^qas_task_update_ai_generate_replace$"
                )
            ],
            QAS_TASK_UPDATE_ARIA2: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_aria2_set),
                        pattern=r"^qas_task_update_aria2_(enable|disable)$"
                )
            ],
            QAS_TASK_UPDATE_IGNORE_EXTENSION: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_task_update_ignore_extension_set),
                        pattern=r"^qas_task_update_ignore_extension_(enable|disable)$"
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_qas_update_task$")
        ],
    ),
    # fix resource link (修复资源链接)
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_fix_link_start),
                pattern=r"^qas_fix_link:.*$"
            )
        ],
        states={
            QAS_FIX_LINK_INPUT_URL: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_fix_link_url_input)
                )
            ],
            QAS_FIX_LINK_SELECT_URL: [
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_fix_link_url_select),
                    pattern=r"^qas_fix_link_select:.*$"
                )
            ],
            QAS_FIX_LINK_CONFIRM: [
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_fix_link_confirm),
                    pattern=r"^qas_fix_link_confirm$"
                ),
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('qas_add_task'))(qas_fix_link_retry),
                    pattern=r"^qas_fix_link_retry$"
                )
            ]
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_qas_fix_link$")
        ],
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
            depends(allowed_roles=get_allow_roles_command_map().get('qas_tag_start_file'))(qas_tag_start_file_handler),
            pattern=r"^qas_tag_start_file:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_run_script'))(qas_view_task_regex_handler),
            pattern=r"^qas_view_task_regex:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_tag_start_file'))(qas_delete_cloud_files_handler),
            pattern=r"^qas_delete_cloud_files:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_tag_start_file'))(qas_delete_cloud_files_confirm_handler),
            pattern=r"^qas_delete_cloud_files_confirm:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('qas_tag_start_file'))(qas_delete_cloud_files_cancel_handler),
            pattern=r"^qas_delete_cloud_files_cancel:.*$"
    )
]
