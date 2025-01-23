from utils import command_handler, MessageUpdate, CommandContext
from core import logger, redis_client
from typing import Optional


@command_handler
async def start(update: MessageUpdate, context: CommandContext) -> None:
    await update.message.reply_text('Hi! Send me a message to start a conversation.')
    logger.info(f"New conversation started with user {update.message.from_user.id}")


@command_handler
async def help_command(update: MessageUpdate, context: CommandContext) -> None:
    await update.message.reply_text("""
    Available commands:
    /start - Start a conversation
    /set_openai_key <your_openai_api_key> - Set your OpenAI API key
    /set_openai_endpoint [<your_openai_api_endpoint>] - Set your OpenAI API endpoint
    /set_openai_model [<your_openai_model>] - Set your OpenAI model
    """)
    logger.debug(f"Help command used by user {update.message.from_user.id}")


@command_handler
async def set_openai_key(update: MessageUpdate, context: CommandContext) -> None:
    if len(context.args) != 1:
        await update.message.reply_text('Usage: /set_openai_key <your_openai_api_key>')
        logger.warning(f"Invalid OpenAI key format from user {update.message.from_user.id}")
        return

    openai_api_key = context.args[0]
    redis_client.set(f"user:{update.message.from_user.id}:openai_api_key", openai_api_key)
    await update.message.reply_text('Your OpenAI API key has been set.')
    logger.info(f"OpenAI API key set for user {update.message.from_user.id}")


@command_handler
async def set_openai_endpoint(update: MessageUpdate, context: CommandContext) -> None:
    if len(context.args) > 1:
        await update.message.reply_text('Usage: /set_openai_endpoint [<your_openai_api_endpoint>]')
        logger.warning(f"Invalid OpenAI endpoint format from user {update.message.from_user.id}")
        return

    openai_api_endpoint: Optional[str] = context.args[0] if context.args else None
    redis_client.set(f"user:{update.message.from_user.id}:openai_api_endpoint", openai_api_endpoint)
    await update.message.reply_text('Your OpenAI API endpoint has been set.')
    logger.info(f"OpenAI API endpoint set for user {update.message.from_user.id}: {openai_api_endpoint}")


@command_handler
async def set_openai_model(update: MessageUpdate, context: CommandContext) -> None:
    if len(context.args) > 1:
        await update.message.reply_text('Usage: /set_openai_model [<your_openai_model>]')
        logger.warning(f"Invalid OpenAI model format from user {update.message.from_user.id}")
        return

    openai_model: Optional[str] = context.args[0] if context.args else None
    redis_client.set(f"user:{update.message.from_user.id}:openai_model", openai_model)
    await update.message.reply_text('Your OpenAI model has been set.')
    logger.info(f"OpenAI model set for user {update.message.from_user.id}: {openai_model}")
