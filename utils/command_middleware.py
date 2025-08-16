from functools import wraps
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes
from db.models.user import User


def depends(allowed_roles: Optional[list[str]]=None):
    def decorator(func):
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            SessionLocal = context.bot_data['db_session_local']
            with SessionLocal() as session:
                user_id = str(update.effective_user.id)
                user = session.query(User).filter_by(tg_id=user_id).first()

                from api.commands import set_commands
                await set_commands(update, context, session, None if user is None else [user])

                if not allowed_roles:
                    return await func(update, context, session, user, *args, **kwargs)
                elif user and user.role.name in allowed_roles:
                    return await func(update, context, session, user, *args, **kwargs)
                else:
                    await update.effective_message.reply_text("你没有权限执行此操作。")
                    return
        return wrapper
    return decorator
