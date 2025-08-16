from typing import Callable, List
from telegram import BotCommand
from telegram.ext import CommandHandler

from config.config import get_allow_roles_command_map
from utils.command_middleware import depends

commands = []

def command(name: str, description: str, args: str= ""):
    def decorator(func: Callable):
        command_name_role_map = get_allow_roles_command_map()
        allow_roles = command_name_role_map.get(name, None)
        commands.append({
            'name': name,
            'description': description,
            'args': args,
            'handler': CommandHandler(name, depends(allowed_roles=allow_roles)(func)),
            'func': func,
        })
        return func
    return decorator

def get_handlers() -> List[CommandHandler]:
    return [cmd['handler'] for cmd in commands]

def get_bot_commands() -> dict:
    return dict([(cmd['name'], BotCommand(cmd['name'], cmd['description'])) for cmd in commands])

def get_help_text() -> str:
    return "\n".join(
        f"{cmd['description']} - /{cmd['name']} {cmd['args']}" for cmd in commands
    )
