import json
import logging
from typing import Optional, List, Dict

from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters

from api.base import command, depends
from api.common import cancel_conversation_callback
from config.config import get_allow_roles_command_map
from db.models.ai_config import AIProviderConfig
from db.models.user import User
from utils.crypto import encrypt_sensitive_data, decrypt_sensitive_data

logger = logging.getLogger(__name__)

# 对话状态
PROVIDER_SELECT, API_KEY_INPUT, HOST_INPUT, MODEL_INPUT, SET_DEFAULT = range(5)

# 不再使用默认配置，所有字段必须显式配置


async def provider_select(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """选择AI提供商"""
    query = update.callback_query
    await query.answer()

    ai_configs = session.query(AIProviderConfig).filter_by(user_id=user.id).all()

    # 构建提供商状态显示
    providers_status = {}
    default_provider = None

    for config in ai_configs:
        providers_status[config.provider_name] = config
        if config.is_default:
            default_provider = config.provider_name

    # 提供商列表
    available_providers = ['openai', 'deepseek', 'kimi']

    buttons = []
    for provider in available_providers:
        if provider in providers_status:
            status = "✅"
            config = providers_status[provider]
        else:
            status = "❌"
            config = None

        is_default_indicator = "⭐" if provider == default_provider else ""
        button_text = f"{status} {provider.upper()} {is_default_indicator}"
        buttons.append([InlineKeyboardButton(button_text, callback_data=f"ai_provider_{provider}")])

    buttons.append([InlineKeyboardButton("设置默认提供商", callback_data="ai_set_default_provider")])
    buttons.append([InlineKeyboardButton("取消", callback_data="cancel_ai_config_upsert_conversation")])

    keyboard = InlineKeyboardMarkup(buttons)

    message = "请选择要配置的AI提供商：\n\n"
    message += "✅ 已配置  ❌ 未配置  ⭐ 默认\n\n"
    if default_provider:
        message += f"当前默认提供商: {default_provider.upper()}"
    else:
        message += "当前默认提供商: 未设置"

    await update.effective_message.reply_text(message, reply_markup=keyboard)
    return PROVIDER_SELECT


async def provider_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """显示提供商详情和配置选项"""
    query = update.callback_query
    await query.answer()

    provider = query.data.replace("ai_provider_", "")
    context.user_data["ai_provider"] = provider

    config = session.query(AIProviderConfig).filter_by(
        user_id=user.id,
        provider_name=provider
    ).first()

    # 显示当前配置状态
    if config:
        current_config = f"""
当前{provider.upper()}配置:
- API Key: {'已设置' if config.api_key else '未设置'}
- Host: {config.host or '未设置'}
- Model: {config.model or '未设置'}
- 默认提供商: {'是' if config.is_default else '否'}
"""
    else:
        current_config = f"""
当前{provider.upper()}配置: 未配置
请先配置所有必需字段 (API Key, Host, Model)
"""

    buttons = [
        [InlineKeyboardButton("配置API Key", callback_data="ai_config_api_key")],
        [InlineKeyboardButton("配置Host", callback_data="ai_config_host")],
        [InlineKeyboardButton("配置Model", callback_data="ai_config_model")],
        [InlineKeyboardButton("删除配置", callback_data="ai_config_delete")],
        [InlineKeyboardButton("返回", callback_data="ai_config_back")]
    ]

    keyboard = InlineKeyboardMarkup(buttons)
    await update.effective_message.reply_text(current_config.strip(), reply_markup=keyboard)
    return PROVIDER_SELECT


async def handle_api_key_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理API Key输入"""
    api_key = update.message.text.strip()
    provider = context.user_data.get("ai_provider")

    if api_key.lower() == 'skip':
        api_key = None

    # 验证API Key不能为空
    if not api_key:
        await update.message.reply_text(f"❌ {provider.upper()} API Key 不能为空，请重新输入:")
        return API_KEY_INPUT

    # 获取或创建配置
    config = session.query(AIProviderConfig).filter_by(
        user_id=user.id,
        provider_name=provider
    ).first()

    if not config:
        config = AIProviderConfig(
            user_id=user.id,
            provider_name=provider,
            api_key=encrypt_sensitive_data(api_key),
            host="",  # 需要后续配置
            model=""  # 需要后续配置
        )
        session.add(config)
    else:
        config.api_key = encrypt_sensitive_data(api_key)

    session.commit()

    await update.message.reply_text(f"✅ {provider.upper()} API Key 已更新")
    return await show_provider_menu(update, context, session, user)


async def handle_host_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理Host输入"""
    host = update.message.text.strip()
    provider = context.user_data.get("ai_provider")

    if host.lower() == 'skip':
        host = None

    # 验证Host不能为空
    if not host:
        await update.message.reply_text(f"❌ {provider.upper()} Host 不能为空，请重新输入:")
        return HOST_INPUT

    # 获取或创建配置
    config = session.query(AIProviderConfig).filter_by(
        user_id=user.id,
        provider_name=provider
    ).first()

    if not config:
        config = AIProviderConfig(
            user_id=user.id,
            provider_name=provider,
            host=host,
            api_key="",  # 需要后续配置
            model=""  # 需要后续配置
        )
        session.add(config)
    else:
        config.host = host

    session.commit()

    await update.message.reply_text(f"✅ {provider.upper()} Host 已更新")
    return await show_provider_menu(update, context, session, user)


async def handle_model_input(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """处理Model输入"""
    model = update.message.text.strip()
    provider = context.user_data.get("ai_provider")

    if model.lower() == 'skip':
        model = None

    # 验证Model不能为空
    if not model:
        await update.message.reply_text(f"❌ {provider.upper()} Model 不能为空，请重新输入:")
        return MODEL_INPUT

    # 获取或创建配置
    config = session.query(AIProviderConfig).filter_by(
        user_id=user.id,
        provider_name=provider
    ).first()

    if not config:
        config = AIProviderConfig(
            user_id=user.id,
            provider_name=provider,
            model=model,
            api_key="",  # 需要后续配置
            host=""  # 需要后续配置
        )
        session.add(config)
    else:
        config.model = model

    session.commit()

    await update.effective_message.reply_text(f"✅ {provider.upper()} Model 已更新")
    return await show_provider_menu(update, context, session, user)


async def delete_config(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """删除配置"""
    query = update.callback_query
    await query.answer()

    provider = context.user_data.get("ai_provider")

    config = session.query(AIProviderConfig).filter_by(
        user_id=user.id,
        provider_name=provider
    ).first()

    if config:
        session.delete(config)
        session.commit()
        await update.effective_message.reply_text(f"✅ {provider.upper()} 配置已删除")
    else:
        await update.effective_message.reply_text(f"❌ {provider.upper()} 配置不存在")

    return await provider_select(update, context, session, user)


def is_config_complete(config: AIProviderConfig) -> bool:
    """检查配置是否完整（所有必填字段都已配置）"""
    return bool(config.api_key and config.host and config.model)

async def set_default_provider_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """设置默认提供商菜单"""
    query = update.callback_query
    await query.answer()

    # 获取当前用户的所有配置
    configs = session.query(AIProviderConfig).filter_by(user_id=user.id).all()

    if not configs:
        await update.effective_message.reply_text("请先配置至少一个AI提供商")
        return PROVIDER_SELECT

    buttons = []
    for config in configs:
        is_default = "⭐" if config.is_default else ""
        # 检查配置是否完整
        if is_config_complete(config):
            status = "✅"
        else:
            status = "❌"
        buttons.append([InlineKeyboardButton(
            f"{status} {config.provider_name.upper()} {is_default}",
            callback_data=f"set_default_{config.provider_name}"
        )])

    buttons.append([InlineKeyboardButton("返回", callback_data="ai_config_back")])
    keyboard = InlineKeyboardMarkup(buttons)

    message = "选择要设为默认的AI提供商:\n\n"
    message += "✅ 配置完整  ❌ 配置不完整"

    await update.effective_message.reply_text(message, reply_markup=keyboard)
    return PROVIDER_SELECT


async def set_default_provider(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """设置默认提供商"""
    query = update.callback_query
    await query.answer()

    provider = query.data.replace("set_default_", "")

    # 获取配置
    config = session.query(AIProviderConfig).filter_by(
        user_id=user.id,
        provider_name=provider
    ).first()

    if not config:
        await update.effective_message.reply_text(f"❌ {provider.upper()} 配置不存在")
        return await provider_select(update, context, session, user)

    # 检查配置是否完整
    if not is_config_complete(config):
        await update.effective_message.reply_text(f"❌ {provider.upper()} 配置不完整，请先配置所有必需字段 (API Key, Host, Model)")
        return await provider_select(update, context, session, user)

    # 先将所有提供商设为非默认
    session.query(AIProviderConfig).filter_by(user_id=user.id).update({"is_default": False})

    # 设置新的默认提供商
    config.is_default = True
    session.commit()
    await update.effective_message.reply_text(f"✅ 默认AI提供商已设置为: {provider.upper()}")

    return await provider_select(update, context, session, user)


async def show_provider_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """显示提供商配置菜单"""
    provider = context.user_data.get("ai_provider")

    buttons = [
        [InlineKeyboardButton("配置API Key", callback_data="ai_config_api_key")],
        [InlineKeyboardButton("配置Host", callback_data="ai_config_host")],
        [InlineKeyboardButton("配置Model", callback_data="ai_config_model")],
        [InlineKeyboardButton("删除配置", callback_data="ai_config_delete")],
        [InlineKeyboardButton("返回", callback_data="ai_config_back")]
    ]

    keyboard = InlineKeyboardMarkup(buttons)

    if update.callback_query:
        await update.effective_message.reply_text(f"{provider.upper()} 配置选项:", reply_markup=keyboard)
    else:
        await update.message.reply_text(f"{provider.upper()} 配置选项:", reply_markup=keyboard)

    return PROVIDER_SELECT


async def handle_api_key_config(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """开始配置API Key"""
    query = update.callback_query
    await query.answer()

    provider = context.user_data.get("ai_provider")

    await update.effective_message.reply_text(f"请输入 {provider.upper()} 的API Key:")
    return API_KEY_INPUT


async def handle_host_config(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """开始配置Host"""
    query = update.callback_query
    await query.answer()

    provider = context.user_data.get("ai_provider")

    await update.effective_message.reply_text(f"请输入 {provider.upper()} 的Host (不能为空):")
    return HOST_INPUT


async def handle_model_config(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    """开始配置Model"""
    query = update.callback_query
    await query.answer()

    provider = context.user_data.get("ai_provider")

    await update.effective_message.reply_text(f"请输入 {provider.upper()} 的Model (不能为空):")
    return MODEL_INPUT


# 获取AI配置的辅助函数
def get_user_ai_config(session: Session, user_id: int) -> Optional[Dict]:
    """获取用户的AI配置（解密敏感数据）"""
    configs = session.query(AIProviderConfig).filter_by(user_id=user_id).all()
    if not configs:
        return None

    result = {}
    default_provider = None

    for config in configs:
        provider_info = {
            'api_key': decrypt_sensitive_data(config.api_key) if config.api_key else None,
            'host': config.host,
            'model': config.model,
            'is_default': config.is_default
        }
        result[config.provider_name] = provider_info

        if config.is_default:
            default_provider = config.provider_name

    result['default_provider'] = default_provider or 'kimi'
    return result


def get_default_ai_config(provider: str) -> Dict:
    """获取默认AI配置（不再使用默认配置）"""
    return {
        'api_key': None,
        'host': '',
        'model': '',
        'is_default': False
    }


# 处理器定义
handlers = [
    # 主要的对话处理器
    ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(provider_select),
                pattern=r"^upsert_ai_configuration"
            )
        ],
        states={
            PROVIDER_SELECT: [
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(provider_detail), pattern=r"^ai_provider_"),
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(set_default_provider_menu), pattern=r"^ai_set_default_provider"),
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(set_default_provider), pattern=r"^set_default_"),
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(provider_select), pattern=r"^ai_config_back$"),
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(delete_config), pattern=r"^ai_config_delete$"),
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(handle_api_key_config), pattern=r"^ai_config_api_key$"),
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(handle_host_config), pattern=r"^ai_config_host$"),
                CallbackQueryHandler(depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(handle_model_config), pattern=r"^ai_config_model$"),
            ],
            API_KEY_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(handle_api_key_input))],
            HOST_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(handle_host_input))],
            MODEL_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, depends(allowed_roles=get_allow_roles_command_map().get('upsert_configuration'))(handle_model_input))],
        },
        fallbacks=[
            CallbackQueryHandler(cancel_conversation_callback, pattern="^cancel_ai_config_upsert_conversation$")
        ],
        conversation_timeout=300,
        name="ai_config_conversation"
    )
]