from typing import List, Callable, TypeVar, ParamSpec, Concatenate
from telegram import Update
from telegram.ext import CallbackContext

# Type definitions for command handler wrapper
P = ParamSpec('P')
T = TypeVar('T')


class MessageUpdate(Update):
    @property
    def message(self):
        message = super().message
        assert message is not None
        return message


class CommandContext(CallbackContext):
    @property
    def args(self) -> List[str]:
        args = super().args
        assert args is not None
        return args


def command_handler(func: Callable[Concatenate[MessageUpdate, CommandContext, P], T]) -> Callable[Concatenate[Update, CallbackContext, P], T]:
    async def wrapper(update: Update, context: CallbackContext, *args: P.args, **kwargs: P.kwargs) -> T:
        return await func(MessageUpdate(update.to_dict()), CommandContext.from_context(context), *args, **kwargs)
    return wrapper
