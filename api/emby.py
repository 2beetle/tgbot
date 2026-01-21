import logging

from sqlalchemy.orm import Session
from sqlalchemy.testing.suite.test_reflection import metadata
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import ConversationHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from api.base import command
from api.common import cancel_conversation_callback
from config.config import get_allow_roles_command_map
from db.models.emby import EmbyConfig
from db.models.user import User
from utils.command_middleware import depends
from utils.emby import Emby
from utils.crypto import encrypt_sensitive_data, decrypt_sensitive_data

HOST_SET, API_TOKEN_SET, USERNAME_SET, PWD_SET = range(4)
EMBY_EDIT_FIELD_SELECT, EMBY_EDIT_HOST, EMBY_EDIT_API_TOKEN, EMBY_EDIT_USERNAME, EMBY_EDIT_PASSWORD = range(4, 9)


logger = logging.getLogger(__name__)


def get_decrypted_emby_credentials(emby_config):
    """从Emby配置中获取解密的凭据"""
    if not emby_config:
        return None, None, None

    try:
        api_token = decrypt_sensitive_data(emby_config.api_token) if emby_config.api_token else None
        username = emby_config.username  # 用户名不加密
        password = decrypt_sensitive_data(emby_config.password) if emby_config.password else None
        return api_token, username, password
    except Exception as e:
        logger.error(f"解密Emby凭据失败: {str(e)}")
        return None, None, None

@command(name='emby_list_resource', description="列出 emby 媒体资源", args="{resource name}")
async def emby_list_resource(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if len(context.args) < 1:
        await update.message.reply_text("缺少参数")
        return

    emby_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()
    if not emby_config:
        await update.message.reply_text("尚未添加 Emby 配置，请使用 /upsert_configuration 命令进行配置")
        return

    resource_name = ' '.join(context.args)

    api_token, username, password = get_decrypted_emby_credentials(emby_config)
    if not api_token:
        await update.message.reply_text("无法解密Emby API令牌，请重新配置")
        return

    emby = Emby(host=emby_config.host, token=api_token)
    data = await emby.list_resource(resource_name)
    if data['Items']:
        for item in data['Items']:
            admin_user_id = await emby.get_admin_user_id()
            meta_data = await emby.get_metadata_by_user_id_item_id(admin_user_id, int(item['Id']))
            caption = f"<b>{meta_data['Name']} ({meta_data['ProductionYear']})</b>"

            caption += "\n\n[相关链接]"
            for external_url in meta_data['ExternalUrls']:
                caption += f'\n<a href="{external_url.get('Url')}">{external_url.get('Name')}地址</a>'
            await update.effective_message.reply_photo(
                photo=await emby.get_remote_image_url_by_item_id(int(item['Id'])),
                caption=caption,
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton('刷新此媒体库', callback_data=f'emby_refresh_library:{int(item['Id'])}'),
                    ]
                ]),
                parse_mode=ParseMode.HTML,
            )
    else:
        await update.message.reply_text(f"没搜索到关于<b>{resource_name}</b>的资源")

@command(name='emby_list_notification', description="列出 emby 通知列表")
async def emby_list_notification(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    emby_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()
    if not emby_config:
        await update.message.reply_text("尚未添加 Emby 配置，请使用 /upsert_configuration 命令进行配置")
        return

    api_token, username, password = get_decrypted_emby_credentials(emby_config)
    if not api_token or not username or not password:
        await update.message.reply_text("无法解密Emby凭据，请重新配置")
        return

    emby = Emby(host=emby_config.host, token=api_token)
    access_token = await emby.get_access_token(username, password)
    data = await emby.list_notification(access_token)
    if data:
        for item in data:
            await update.effective_message.reply_text(
                text=item['FriendlyName'],
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton('✅开启新媒体加入通知', callback_data=f'emby_nt_set:{item["Id"]}:library.new:open'),
                        InlineKeyboardButton('❌关闭新媒体加入通知', callback_data=f'emby_nt_set:{item["Id"]}:library.new:close'),
                    ]
                ]),
                parse_mode=ParseMode.HTML,
            )
    else:
        await update.message.reply_text(f"没有配置通知")


async def emby_refresh_library(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
    _, item_id = query.data.split(":")
    emby_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()
    if not emby_config:
        await update.message.reply_text("尚未添加 Emby 配置，请使用 /upsert_configuration 命令进行配置")
        return

    api_token, username, password = get_decrypted_emby_credentials(emby_config)
    if not api_token:
        await update.message.reply_text("无法解密Emby API令牌，请重新配置")
        return

    emby = Emby(host=emby_config.host, token=api_token)
    result = await emby.refresh_library(int(item_id))
    if result:
        await update.effective_message.reply_text("刷新媒体库成功")
    else:
        await update.effective_message.reply_text("刷新媒体库失败")


async def emby_notification_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    args = query.data.split(":")[1:]
    notification_id = args[0]
    event_id = args[1]
    operation = args[2]

    emby_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()
    if not emby_config:
        await update.message.reply_text("尚未添加 Emby 配置，请使用 /upsert_configuration 命令进行配置")
        return

    api_token, username, password = get_decrypted_emby_credentials(emby_config)
    if not api_token or not username or not password:
        await update.effective_message.reply_text("无法解密Emby凭据，请重新配置")
        return

    emby = Emby(host=emby_config.host, token=api_token)
    access_token = await emby.get_access_token(username, password)
    resp = await emby.update_notification(access_token, notification_id, event_id, operation)
    if resp:
        await update.effective_message.reply_text("更新通知配置成功")
    else:
        await update.effective_message.reply_text("更新通知配置失败")


async def host_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    # 检查是否已有配置
    existing_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()

    if existing_config:
        # 显示当前配置并让用户选择要修改的字段
        keyboard = [
            [InlineKeyboardButton("🌐 Host", callback_data="emby_edit_host")],
            [InlineKeyboardButton("🔑 Api Token", callback_data="emby_edit_api_token")],
            [InlineKeyboardButton("👤 用户名", callback_data="emby_edit_username")],
            [InlineKeyboardButton("🔒 密码", callback_data="emby_edit_password")],
            [InlineKeyboardButton("✅ 完成修改", callback_data="emby_finish_edit")],
            [InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")]
        ]

        message = f"""
<b>当前 Emby 配置：</b>
🌐 <b>Host：</b> {existing_config.host}
🔑 <b>Api Token：</b> {'***' if existing_config.api_token else '未设置'}
👤 <b>用户名：</b> {existing_config.username}
🔒 <b>密码：</b> {'***' if existing_config.password else '未设置'}

请选择要修改的字段：
        """

        await query.message.reply_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="html"
        )
        return EMBY_EDIT_FIELD_SELECT
    else:
        # 新配置，需要填写所有字段
        await query.message.reply_text("请输入你 Emby 服务的 Host：", reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
        ]]))
        return HOST_SET

async def host_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    host = str(update.message.text)
    if host and host.endswith('/'):
        host = host[:-1]

    if 'configuration' not in context.user_data:
        context.user_data.update({
            "configuration": {
                "emby": {
                    'host': host
                }
            }
        })
    else:
        context.user_data["configuration"].update(
            {
                'emby': {
                    'host': host
                }
            }
        )
    await update.message.reply_text("请输入你 Emby 服务的 Api Token：", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
    ]]))
    return  API_TOKEN_SET

async def api_token_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    context.user_data["configuration"]['emby'].update({
        'api_token': update.message.text
    })
    await update.message.reply_text("请输入你 Emby 的管理员用户名：", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
    ]]))
    return USERNAME_SET

async def username_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    context.user_data["configuration"]['emby'].update({
        'username': update.message.text
    })
    await update.message.reply_text("请输入你 Emby 的管理员密码：", reply_markup=InlineKeyboardMarkup([[
        InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
    ]]))
    return PWD_SET

async def pwd_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    context.user_data["configuration"]['emby'].update({
        'pwd': update.message.text
    })
    return await upsert_emby_configuration_finish(update, context, session, user)

# Emby 部分修改相关函数
async def emby_field_select_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()

    # 初始化编辑数据结构
    if "emby_edit_data" not in context.user_data:
        context.user_data["emby_edit_data"] = {}

    field_map = {
        "emby_edit_host": ("host", "请输入你 Emby 服务的 Host：", EMBY_EDIT_HOST),
        "emby_edit_api_token": ("api_token", "请输入你 Emby 服务的 Api Token：", EMBY_EDIT_API_TOKEN),
        "emby_edit_username": ("username", "请输入你 Emby 的管理员用户名：", EMBY_EDIT_USERNAME),
        "emby_edit_password": ("password", "请输入你 Emby 的管理员密码：", EMBY_EDIT_PASSWORD),
        "emby_finish_edit": ("finish", "", None)
    }

    action = query.data

    if action == "emby_finish_edit":
        # 完成编辑，准备保存
        existing_config = session.query(EmbyConfig).filter(
            EmbyConfig.user_id == user.id
        ).first()

        # 构建更新数据
        if "configuration" not in context.user_data:
            context.user_data["configuration"] = {}
        if "emby" not in context.user_data["configuration"]:
            context.user_data["configuration"]["emby"] = {}

        edit_data = context.user_data.get("emby_edit_data", {})

        # 只更新用户修改过的字段，处理现有配置不存在的情况
        if "host" in edit_data:
            context.user_data["configuration"]["emby"]["host"] = edit_data["host"]
        else:
            context.user_data["configuration"]["emby"]["host"] = existing_config.host if existing_config else ""

        if "api_token" in edit_data:
            context.user_data["configuration"]["emby"]["api_token"] = edit_data["api_token"]
        else:
            # 使用现有配置的解密API token
            if existing_config:
                decrypted_token = get_decrypted_emby_credentials(existing_config)[0]
            else:
                decrypted_token = ""
            context.user_data["configuration"]["emby"]["api_token"] = decrypted_token or ""

        if "username" in edit_data:
            context.user_data["configuration"]["emby"]["username"] = edit_data["username"]
        else:
            context.user_data["configuration"]["emby"]["username"] = existing_config.username if existing_config else ""

        if "password" in edit_data:
            context.user_data["configuration"]["emby"]["pwd"] = edit_data["password"]
        else:
            # 使用现有配置的解密密码
            if existing_config:
                decrypted_password = get_decrypted_emby_credentials(existing_config)[2]
            else:
                decrypted_password = ""
            context.user_data["configuration"]["emby"]["pwd"] = decrypted_password or ""

        # 清理编辑数据
        context.user_data.pop("emby_edit_data", None)
        return await upsert_emby_configuration_finish(update, context, session, user)

    elif action in field_map:
        field_name, prompt_text, next_state = field_map[action]
        if field_name == "finish":
            return await emby_field_select_handler(update, context, session, user)

        # 保存当前编辑的字段状态
        context.user_data["emby_edit_current_field"] = next_state

        await query.message.reply_text(
            prompt_text,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")
            ]])
        )
        return next_state


async def emby_edit_field_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理编辑字段的输入"""
    if not update.message:
        return

    current_state = context.user_data.get("emby_edit_current_field")
    input_value = update.message.text

    # 根据不同的字段进行特殊处理
    if current_state == EMBY_EDIT_HOST:
        if input_value and input_value.endswith('/'):
            input_value = input_value[:-1]

    # 保存编辑的数据
    if "emby_edit_data" not in context.user_data:
        context.user_data["emby_edit_data"] = {}

    field_mapping = {
        EMBY_EDIT_HOST: "host",
        EMBY_EDIT_API_TOKEN: "api_token",
        EMBY_EDIT_USERNAME: "username",
        EMBY_EDIT_PASSWORD: "password"
    }

    field_name = field_mapping.get(current_state)
    if field_name:
        context.user_data["emby_edit_data"][field_name] = input_value

    # 回到字段选择界面
    return await emby_show_edit_menu(update, context, session, user)


async def emby_show_edit_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """显示编辑菜单"""
    existing_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()

    edit_data = context.user_data.get("emby_edit_data", {})

    # 显示当前配置和已修改的字段
    host = edit_data.get("host", existing_config.host)
    username = edit_data.get("username", existing_config.username)

    keyboard = [
        [InlineKeyboardButton("🌐 Host", callback_data="emby_edit_host")],
        [InlineKeyboardButton("🔑 Api Token", callback_data="emby_edit_api_token")],
        [InlineKeyboardButton("👤 用户名", callback_data="emby_edit_username")],
        [InlineKeyboardButton("🔒 密码", callback_data="emby_edit_password")],
        [InlineKeyboardButton("✅ 完成修改", callback_data="emby_finish_edit")],
        [InlineKeyboardButton("❌ 取消", callback_data="cancel_upsert_configuration")]
    ]

    message = f"""
<b>当前 Emby 配置：</b>
🌐 <b>Host：</b> {host}
🔑 <b>Api Token：</b> {'***' if edit_data.get('api_token') or existing_config.api_token else '未设置'}
👤 <b>用户名：</b> {username}
🔒 <b>密码：</b> {'***' if edit_data.get('password') or existing_config.password else '未设置'}

请选择要修改的字段：
    """

    await update.effective_message.reply_text(
        message,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="html"
    )
    return EMBY_EDIT_FIELD_SELECT


async def upsert_emby_configuration_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    host = context.user_data["configuration"]["emby"]["host"]
    api_token = context.user_data["configuration"]["emby"]["api_token"]
    username = context.user_data["configuration"]["emby"]["username"]
    password = context.user_data["configuration"]["emby"]["pwd"]

    # 加密敏感数据
    encrypted_api_token = encrypt_sensitive_data(api_token)
    encrypted_password = encrypt_sensitive_data(password)

    # 查找现有配置
    existing_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()

    if existing_config:
        # 部分更新：只更新提供的字段
        update_data = {}
        if host != existing_config.host:
            update_data[EmbyConfig.host] = host
        if encrypted_api_token != existing_config.api_token:
            update_data[EmbyConfig.api_token] = encrypted_api_token
        if username != existing_config.username:
            update_data[EmbyConfig.username] = username
        if encrypted_password != existing_config.password:
            update_data[EmbyConfig.password] = encrypted_password

        if update_data:
            session.query(EmbyConfig).filter(EmbyConfig.user_id == user.id).update(update_data)
            message = "Emby 配置已部分更新：\n"
        else:
            message = "Emby 配置没有变化：\n"
    else:
        # 新增配置
        session.add(
            EmbyConfig(
                host=host,
                api_token=encrypted_api_token,
                user_id=user.id,
                username=username,
                password=encrypted_password,
            )
        )
        message = "Emby 配置已新增：\n"

    session.commit()

    # 显示当前配置状态
    current_config = session.query(EmbyConfig).filter(
        EmbyConfig.user_id == user.id
    ).first()

    message += f"""
<b>Host：</b> {current_config.host}
<b>Api Token：</b> {'***' if current_config.api_token else '未设置'}
<b>用户名：</b> {current_config.username}
<b>密码：</b> {'***' if current_config.password else '未设置'}

操作完成
"""
    await update.effective_message.reply_text(message, parse_mode="html")
    return ConversationHandler.END

handlers = [
    # 插入 emby 配置
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(host_input),
                pattern=r"^upsert_emby_configuration"
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
            USERNAME_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(username_set)
                )
            ],
            PWD_SET: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(pwd_set)
                )
            ],
            # 部分修改状态
            EMBY_EDIT_FIELD_SELECT: [
                CallbackQueryHandler(
                        depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(emby_field_select_handler),
                        pattern=r"^emby_(edit_|finish_).*$"
                )
            ],
            EMBY_EDIT_HOST: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(emby_edit_field_set)
                )
            ],
            EMBY_EDIT_API_TOKEN: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(emby_edit_field_set)
                )
            ],
            EMBY_EDIT_USERNAME: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(emby_edit_field_set)
                )
            ],
            EMBY_EDIT_PASSWORD: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(emby_edit_field_set)
                )
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_upsert_configuration$")
        ],
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('emby_list_resource'))(emby_refresh_library),
            pattern=r"^emby_refresh_library:.*$"
    ),
    CallbackQueryHandler(
            depends(allowed_roles=get_allow_roles_command_map().get('emby_list_resource'))(emby_notification_set),
            pattern=r"^emby_nt_set:.*$"
    )
]