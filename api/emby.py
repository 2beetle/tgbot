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
    resp = await emby.refresh_library(int(item_id))
    if resp.ok:
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
    if resp.ok:
        await update.effective_message.reply_text("更新通知配置成功")
    else:
        await update.effective_message.reply_text("更新通知配置失败")


async def host_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    query = update.callback_query
    await query.answer()
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

async def upsert_emby_configuration_finish(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    host = context.user_data["configuration"]["emby"]["host"]
    api_token = context.user_data["configuration"]["emby"]["api_token"]
    username = context.user_data["configuration"]["emby"]["username"]
    password = context.user_data["configuration"]["emby"]["pwd"]

    # 加密敏感数据
    encrypted_api_token = encrypt_sensitive_data(api_token)
    encrypted_password = encrypt_sensitive_data(password)

    count = session.query(EmbyConfig).filter(EmbyConfig.user_id == user.id).count()
    if count > 0:
        session.query(EmbyConfig).filter(EmbyConfig.user_id == user.id).update({
            EmbyConfig.host: host,
            EmbyConfig.api_token: encrypted_api_token,
            EmbyConfig.username: username,
            EmbyConfig.password: encrypted_password,
        })
    else:
        session.add(
            EmbyConfig(
                host=host,
                api_token=encrypted_api_token,
                user_id=user.id,
                username=username,
                password=encrypted_password,
            )
        )
    session.commit()

    message = f"""
已添加 <b>{host}</b> 配置
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
            ]
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