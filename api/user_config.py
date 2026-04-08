import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from api.common import cancel_conversation_callback
from config.config import get_allow_roles_command_map, AVAILABLE_CLOUD_TYPES
from db.models.user import User
from utils.command_middleware import depends

logger = logging.getLogger(__name__)

# 对话状态
CLOUD_TYPE_SELECT = 0
SAVE_SPACE_SELECT = 1
QUARK_COOKIES_SET = 2

# 从全局配置获取支持的云盘类型，转换为 UI 需要的格式
AVAILABLE_CLOUD_TYPES_LIST = [
    {"id": cloud_type, "name": cloud_type}
    for cloud_type in sorted(AVAILABLE_CLOUD_TYPES)
]


async def save_space_mode_select(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """节省网盘空间模式配置"""
    query = update.callback_query
    await query.answer()

    # 获取用户当前配置
    user_config = user.configuration or {}
    save_space_mode = user_config.get('save_space_mode', False)
    status = "✅ 已开启" if save_space_mode else "⬜ 已关闭"

    buttons = [
        [InlineKeyboardButton(f"{status}", callback_data="toggle_save_space_mode")],
        [InlineKeyboardButton("❌ 关闭", callback_data="cancel_save_space_config_conversation")]
    ]

    keyboard = InlineKeyboardMarkup(buttons)

    message = "<b>💾 节省网盘空间模式</b>\n\n"
    message += f"<b>当前状态:</b> {status}\n\n"
    message += "<i><b>⚠️注意：开启设置后标记开始转存任务会删除云盘中旧的文件⚠️</b></i>"

    try:
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await update.effective_message.reply_text(message, reply_markup=keyboard, parse_mode="HTML")

    return SAVE_SPACE_SELECT


async def toggle_save_space_mode(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """切换节省网盘空间模式"""
    query = update.callback_query
    await query.answer()

    # 获取用户配置
    user_config = user.configuration or {}
    current_status = user_config.get('save_space_mode', False)

    # 切换状态
    new_status = not current_status
    user_config['save_space_mode'] = new_status

    # 保存到数据库
    user.configuration = user_config
    flag_modified(user, "configuration")
    session.commit()

    status_text = "已开启 ✅" if new_status else "已关闭 ⬜"
    message = f"💾 节省网盘空间模式 {status_text}\n\n"
    message += "<i><b>⚠️注意：开启设置后标记开始转存任务会删除云盘中旧的文件⚠️</b></i>"

    try:
        await query.edit_message_text(message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await update.effective_message.reply_text(message, parse_mode="HTML")

    return ConversationHandler.END


async def cloud_type_select(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """选择常用云盘类型"""
    query = update.callback_query
    await query.answer()

    # 获取用户当前配置
    user_config = user.configuration or {}
    preferred_clouds = user_config.get('preferred_cloud_types', [])

    # 从 context.user_data 中获取临时配置（如果有的话）
    temp_clouds = context.user_data.get('preferred_cloud_types')
    if temp_clouds is not None:
        preferred_clouds = temp_clouds

    # 构建云盘类型选择按钮
    buttons = []
    for cloud_type in AVAILABLE_CLOUD_TYPES_LIST:
        cloud_id = cloud_type['id']
        cloud_name = cloud_type['name']

        # 检查是否已选择
        is_selected = cloud_id in preferred_clouds
        status = "✅" if is_selected else "⬜"

        buttons.append([
            InlineKeyboardButton(
                f"{status} {cloud_name}",
                callback_data=f"toggle_cloud_{cloud_id}"
            )
        ])

    buttons.append([
        InlineKeyboardButton("💾 保存配置", callback_data="save_cloud_config")
    ])

    buttons.append([
        InlineKeyboardButton("❌ 取消", callback_data="cancel_cloud_config_conversation")
    ])

    keyboard = InlineKeyboardMarkup(buttons)

    message = "<b>☁️ 云盘配置</b>\n\n"
    message += "请选择常用云盘类型:\n\n"
    if preferred_clouds:
        message += f"<b>已选择:</b> {', '.join(preferred_clouds)}\n\n"
        message += "<i>搜索资源时将只显示这些云盘的资源</i>"
    else:
        message += "<i>未选择任何云盘，将显示所有云盘资源</i>"

    try:
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        # 如果编辑失败，尝试发送新消息
        await update.effective_message.reply_text(message, reply_markup=keyboard, parse_mode="HTML")

    return CLOUD_TYPE_SELECT


async def toggle_cloud_type(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """切换云盘类型选择状态"""
    query = update.callback_query
    await query.answer()

    # 获取用户当前配置
    user_config = user.configuration or {}
    preferred_clouds = user_config.get('preferred_cloud_types', [])

    # 从 context.user_data 中获取临时配置（如果有的话）
    if 'preferred_cloud_types' in context.user_data:
        preferred_clouds = context.user_data['preferred_cloud_types']

    # 从 callback_data 中提取云盘ID
    cloud_id = query.data.replace("toggle_cloud_", "")

    # 切换选择状态
    if cloud_id in preferred_clouds:
        preferred_clouds.remove(cloud_id)
    else:
        preferred_clouds.append(cloud_id)

    # 保存到 context.user_data，稍后在保存时写入数据库
    context.user_data['preferred_cloud_types'] = preferred_clouds

    return await cloud_type_select(update, context, session, user)


async def save_cloud_config(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """保存云盘配置"""
    query = update.callback_query
    await query.answer()

    # 从 context.user_data 中获取配置
    preferred_clouds = context.user_data.get('preferred_cloud_types', [])

    # 获取用户配置
    user_config = user.configuration or {}

    # 更新配置
    user_config['preferred_cloud_types'] = preferred_clouds

    # 保存到数据库
    user.configuration = user_config
    flag_modified(user, "configuration")
    session.commit()

    # 清除临时数据
    if 'preferred_cloud_types' in context.user_data:
        del context.user_data['preferred_cloud_types']

    message = "✅ <b>云盘配置已保存</b>\n\n"
    if preferred_clouds:
        message += f"<b>常用云盘:</b> {', '.join(preferred_clouds)}\n\n"
        message += "<i>搜索资源时将只显示这些云盘的资源</i>"
    else:
        message += "<i>未设置常用云盘，搜索资源时将显示所有云盘的资源</i>"

    try:
        await query.edit_message_text(message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await update.effective_message.reply_text(message, parse_mode="HTML")

    return ConversationHandler.END


async def quark_cookies_select(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """夸克网盘 Cookies 配置"""
    query = update.callback_query
    await query.answer()

    # 获取用户当前配置
    quark_cookies = await get_user_quark_cookies(user)
    has_cookies = bool(quark_cookies)
    status = "✅ 已配置" if has_cookies else "⬜ 未配置"

    buttons = [
        [InlineKeyboardButton(f"{status}", callback_data="update_quark_cookies")],
    ]
    if has_cookies:
        buttons.append([InlineKeyboardButton("🔍 检测有效性", callback_data="check_quark_cookies_validity")])
    buttons.append([InlineKeyboardButton("❌ 关闭", callback_data="cancel_quark_config_conversation")])

    keyboard = InlineKeyboardMarkup(buttons)

    message = "<b>🍪 夸克网盘 Cookies</b>\n\n"
    message += f"<b>当前状态:</b> {status}\n\n"
    message += "<i>用于获取夸克网盘文件列表、删除文件等操作</i>\n"
    if has_cookies:
        masked_cookies = quark_cookies[:20] + "..." if len(quark_cookies) > 20 else quark_cookies
        message += f"\n<i>已配置 Cookies: {masked_cookies}</i>"

    try:
        await query.edit_message_text(message, reply_markup=keyboard, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await update.effective_message.reply_text(message, reply_markup=keyboard, parse_mode="HTML")

    return QUARK_COOKIES_SET


async def update_quark_cookies(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """提示用户输入新的夸克网盘 Cookies"""
    query = update.callback_query
    await query.answer()

    message = "🍪 <b>请输入夸克网盘 Cookies</b>\n\n"
    message += "<i>请在浏览器中登录夸克网盘，复制 Cookie 值</i>\n\n"
    message += "<b>获取方式:</b>\n"
    message += "1. 在浏览器中打开 <code>https://pan.quark.cn</code>\n"
    message += "2. 登录你的夸克账号\n"
    message += "3. 按 F12 打开开发者工具\n"
    message += "4. 切换到 Network (网络) 标签\n"
    message += "5. 刷新页面，找到任意请求\n"
    message += "6. 在请求头中找到 <code>Cookie:</code> 字段\n"
    message += "7. 复制完整的 Cookie 值"

    buttons = [[InlineKeyboardButton("❌ 取消", callback_data="cancel_quark_config_conversation")]]

    try:
        await query.edit_message_text(message, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await update.effective_message.reply_text(message, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

    return QUARK_COOKIES_SET


async def quark_cookies_set(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """保存夸克网盘 Cookies"""
    if not update.message or not update.message.text:
        return

    cookies = update.message.text.strip()

    if not cookies:
        await update.message.reply_text("❌ Cookies 不能为空")
        return

    # 导入加密函数
    from utils.crypto import encrypt_sensitive_data

    # 加密 Cookies
    encrypted_cookies = encrypt_sensitive_data(cookies)

    # 获取用户配置
    user_config = user.configuration or {}
    user_config['quark_cookies'] = encrypted_cookies

    # 保存到数据库
    user.configuration = user_config
    flag_modified(user, "configuration")
    session.commit()

    message = "✅ <b>夸克网盘 Cookies 已保存</b>\n\n"
    message += "<i>现在可以使用夸克网盘相关功能了</i>"

    await update.message.reply_text(message, parse_mode="HTML")

    return ConversationHandler.END


async def check_quark_cookies_manual(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """手动检测夸克网盘 Cookies 有效性"""
    import asyncio
    query = update.callback_query
    await query.answer()

    quark_cookies = await get_user_quark_cookies(user)
    if not quark_cookies:
        await query.edit_message_text("❌ 未配置夸克网盘 Cookies", parse_mode="HTML")
        return ConversationHandler.END

    await query.edit_message_text("🔍 <b>正在检测夸克网盘 Cookies 有效性...</b>", parse_mode="HTML")

    from utils.quark import Quark
    quark = Quark(cookies=quark_cookies)

    max_retries = 3
    account_info = None
    for attempt in range(1, max_retries + 1):
        account_info = await quark.get_account_info()
        if account_info:
            break
        if attempt < max_retries:
            logger.warning(f"用户 {user.username} 手动检测夸克 Cookies 第 {attempt} 次失败，2秒后重试")
            await asyncio.sleep(2)

    if account_info:
        message = "✅ <b>夸克网盘 Cookies 有效</b>\n\n"
        nickname = account_info.get("nickname", "")
        if nickname:
            message += f"<b>账号昵称:</b> {nickname}"
    else:
        message = (
            "❌ <b>夸克网盘 Cookies 已失效</b>\n\n"
            f"重试 {max_retries} 次均失败，请重新配置 Cookies。\n"
            "使用 /upsert_configuration 命令更新「夸克网盘」Cookies。"
        )

    try:
        await query.edit_message_text(message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await update.effective_message.reply_text(message, parse_mode="HTML")

    return ConversationHandler.END


# 获取用户夸克网盘 Cookies 的辅助函数
async def get_user_quark_cookies(user: User) -> str:
    """获取用户夸克网盘 Cookies（解密后）"""
    if not user.configuration:
        return ""

    encrypted_cookies = user.configuration.get('quark_cookies', '')
    if not encrypted_cookies:
        return ""

    from utils.crypto import decrypt_sensitive_data
    try:
        return decrypt_sensitive_data(encrypted_cookies)
    except Exception as e:
        logger.error(f"解密夸克 Cookies 失败: {e}")
        return ""


# 获取用户常用云盘类型的辅助函数
def get_user_preferred_cloud_types(user: User) -> Optional[List[str]]:
    """获取用户常用云盘类型列表"""
    if not user.configuration:
        return None

    preferred_clouds = user.configuration.get('preferred_cloud_types', None)

    # 如果列表为空，返回 None 表示显示所有云盘
    if not preferred_clouds:
        return None

    return preferred_clouds


# 获取用户是否启用节省网盘空间模式
def get_user_save_space_mode(user: User) -> bool:
    """获取用户是否启用节省网盘空间模式"""
    if not user.configuration:
        return False

    return user.configuration.get('save_space_mode', False)


# 处理器定义
handlers = [
    # 节省网盘空间模式配置对话处理器
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(save_space_mode_select),
                pattern=r"^upsert_save_space_configuration"
            )
        ],
        states={
            SAVE_SPACE_SELECT: [
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(toggle_save_space_mode),
                    pattern=r"^toggle_save_space_mode$"
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_save_space_config_conversation$")
        ],
        conversation_timeout=300,
        name="save_space_config_conversation"
    ),
    # 云盘配置对话处理器
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(cloud_type_select),
                pattern=r"^upsert_cloud_configuration"
            )
        ],
        states={
            CLOUD_TYPE_SELECT: [
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(toggle_cloud_type),
                    pattern=r"^toggle_cloud_"
                ),
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(save_cloud_config),
                    pattern=r"^save_cloud_config$"
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_cloud_config_conversation$")
        ],
        conversation_timeout=300,
        name="cloud_config_conversation"
    ),
    # 夸克网盘 Cookies 配置对话处理器
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(quark_cookies_select),
                pattern=r"^upsert_quark_configuration"
            )
        ],
        states={
            QUARK_COOKIES_SET: [
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(update_quark_cookies),
                    pattern=r"^update_quark_cookies$"
                ),
                CallbackQueryHandler(
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(check_quark_cookies_manual),
                    pattern=r"^check_quark_cookies_validity$"
                ),
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND,
                    depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(quark_cookies_set)
                ),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_quark_config_conversation$")
        ],
        conversation_timeout=300,
        name="quark_config_conversation"
    )
]