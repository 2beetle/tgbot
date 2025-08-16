# 开发指南
## model
1. 在 `db/models` 中新增新的文件 `model_file.py`
2. 在 `alembic/env.py` 中添加 `from db.models.model_file import *`

## api（command）
1. 在 `api` 中新增新的文件 `command.py`
2. 在 `command.py` 中新增新的 command
   ```python
   @command(name='<command name>', description="<command description>")
   async def command_name(update: Update, context: ContextTypes.DEFAULT_TYPE, session: Session, user: User):
       await update.message.reply_text(
           text="text"
       )
   ```
3. 在 `config/config.py` 的 `ROLE_COMMANDS` 中配置 command 和 role 之间的关系
4. 在 `main.py` 中添加 `from api import command`
5. 若 `command.py` 中有额外的 handler 需要添加，请在文件末尾新增 `handlers` 列表变量
   ```python
   handlers = [
          CallbackQueryHandler(
              depends(allowed_roles=get_allow_roles_command_map().get(''))(on_callback),
              pattern=r"^:.*$")
   ]
   ```
6. 在 `main.py` 的 `register_extra_handlers.modules` 中添加 `api.command`


## 数据库版本管理
1. commit version (生成版本记录)
    ```bash
    alembic revision --autogenerate -m "message"
    ```
2. upgrade version (修改数据库结构)
    ```bash
    alembic upgrade head
    ```
3. [更多](https://alembic.sqlalchemy.org/en/latest/)