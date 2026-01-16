import logging
from typing import Optional, List

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler

from api.common import cancel_conversation_callback
from config.config import get_allow_roles_command_map, AVAILABLE_CLOUD_TYPES
from db.models.user import User
from utils.command_middleware import depends

logger = logging.getLogger(__name__)

# 对话状态
CLOUD_TYPE_SELECT = 0
SAVE_SPACE_SELECT = 1

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
    message += "<i>开启后，手动运行QAS任务时会自动标记最新文件为开始转存文件，节省网盘空间，<b>⚠️注意：开启后运行任务会删除云盘中旧的文件⚠️</b></i>"

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
    message += "<i>开启后，手动运行QAS任务时会自动标记最新文件为开始转存文件，节省网盘空间，<b>⚠️注意：开启后运行任务会删除云盘中旧的文件⚠️</b></i>"

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
    )
]