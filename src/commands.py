from core import logger, redis_client
from typing import Optional
from telegram import Update
from telegram.ext import CallbackContext


async def start(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.from_user:
        return
    await update.message.reply_text('Hi! Send me a message to start a conversation.\n\nYou can use /help to see the available commands.')
    logger.info(f"New conversation started with user {update.message.from_user.id}")


async def help_command(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.from_user:
        return
    await update.message.reply_text("""
    Available commands:
    /set_openai_key <your_openai_api_key>
    /set_openai_endpoint <your_openai_api_endpoint>
    /set_openai_model <your_openai_model>
    """)
    logger.debug(f"Help command used by user {update.message.from_user.id}")


async def set_openai_key(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.from_user:
        return
    if not context.args or len(context.args) != 1:
        await update.message.reply_text('Usage: /set_openai_key <your_openai_api_key>')
        logger.warning(f"Invalid OpenAI key format from user {update.message.from_user.id}")
        return

    openai_api_key = context.args[0]
    await redis_client.set(f"user:{update.message.from_user.id}:openai_api_key", openai_api_key)
    await update.message.reply_text('Your OpenAI API key has been set.')
    logger.info(f"OpenAI API key set for user {update.message.from_user.id}")


async def set_openai_endpoint(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.from_user:
        return
    if not context.args or len(context.args) > 1:
        await update.message.reply_text('Usage: /set_openai_endpoint <your_openai_api_endpoint>')
        logger.warning(f"Invalid OpenAI endpoint format from user {update.message.from_user.id}")
        return

    if openai_api_endpoint := context.args[0] if context.args else None:
        await redis_client.set(f"user:{update.message.from_user.id}:openai_api_endpoint", openai_api_endpoint)
        await update.message.reply_text('Your OpenAI API endpoint has been set.')
        logger.info(f"OpenAI API endpoint set for user {update.message.from_user.id}: {openai_api_endpoint}")
    else:
        await update.message.reply_text('Usage: /set_openai_endpoint <your_openai_api_endpoint>')
        logger.warning(f"Invalid OpenAI endpoint format from user {update.message.from_user.id}")


async def set_openai_model(update: Update, context: CallbackContext) -> None:
    if not update.message or not update.message.from_user:
        return
    if not context.args or len(context.args) > 1:
        await update.message.reply_text('Usage: /set_openai_model <your_openai_model>')
        logger.warning(f"Invalid OpenAI model format from user {update.message.from_user.id}")
        return

    if openai_model := context.args[0] if context.args else None:
        await redis_client.set(f"user:{update.message.from_user.id}:openai_model", openai_model)
        await update.message.reply_text('Your OpenAI model has been set.')
        logger.info(f"OpenAI model set for user {update.message.from_user.id}: {openai_model}")
    else:
        await update.message.reply_text('Usage: /set_openai_model <your_openai_model>')
        logger.warning(f"Invalid OpenAI model format from user {update.message.from_user.id}")
