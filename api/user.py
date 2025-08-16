from pyexpat.errors import messages
from typing import Optional

from sqlalchemy.orm import Session
from telegram import Update
from telegram.ext import ContextTypes

from api.base import command
from api.commands import set_commands
from config.config import ADMIN_ROLE_NAME, USER_ROLE_NAME, OWNER_ROLE_NAME
from db.models.log import OperationLog, OperationType
from db.models.user import User, Role

@command(name='register', description="注册")
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if not user:
        user_count = session.query(User).count()
        if user_count == 0:
            user_role = session.query(Role).filter_by(name=OWNER_ROLE_NAME).first()
        else:
            user_role = session.query(Role).filter_by(name=USER_ROLE_NAME).first()
        new_user = User(tg_id=update.effective_user.id,
                        chat_id=update.effective_chat.id,
                        username=update.effective_user.username,
                        role_id=user_role.id
                        )
        session.add(new_user)
        session.commit()
        message = '注册成功'
        await set_commands(update, context, session, [new_user])
    else:
        message = '你已注册'
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)


@command(name='my_info', description="获取个人信息")
async def my_info(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    if user:
        message = "<pre>TG_ID   Username   Role\n"
        message += "------------------------\n"
        message += f"{user.tg_id: <4} {user.username: <10} {user.role.name: <6}\n"
        message += "</pre>"
    else:
        message = '你未注册'
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message,parse_mode='HTML')

@command(name='set_admin', description="将用户设置为管理员", args="{telegram id}")
async def set_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
    user_tg_ids = context.args[0].split(',')
    admin_role = session.query(Role).filter_by(name=ADMIN_ROLE_NAME).first()
    session.query(User).filter(User.tg_id.in_(user_tg_ids)
                               ).update(
        {User.role_id: admin_role.id},
        synchronize_session=False
    )

    op_logs = list()
    for user_tg_id in user_tg_ids:
        update_user = session.query(User).filter_by(tg_id=user_tg_id).first()
        if not update_user:
            continue
        op_logs.append(
            OperationLog(
                user_id=user.id,
                operation=OperationType.UPDATE,
                target_id=update_user.id,
                target_table=User.__tablename__,
                description=f"将用户 {update_user.username} 设置为管理员"
            )
        )
    session.add_all(op_logs)
    session.commit()
    message = f'{user_tg_ids} 已经设置为管理员'
    admins = session.query(User).filter(User.tg_id.in_(user_tg_ids)).all()
    await set_commands(update, context, session, admins)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=message)