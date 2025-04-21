"""
utils.py

Aims to clean out LLM output, cleans out non-existing HTML tags, and closes open tags
"""

import asyncio
from html.parser import HTMLParser
import httpx
from datetime import datetime, timedelta
from functools import wraps
from typing import Callable, Any, Optional, TypeVar, Union, Coroutine
from telegram import Update
from telegram.ext import ContextTypes, CallbackContext
import os

from core import logger, redis_client

T = TypeVar('T')

ADMIN_CHAT_ID_LIST = [int(id) for id in os.getenv('ADMIN_CHAT_ID_LIST', '').split(',') if id]


async def get_redis_value(key: str, default: Optional[T] = None) -> Optional[str]:
    """
    Get a value from Redis and decode it from bytes to string.

    Args:
        key: The Redis key to retrieve
        default: Default value to return if key doesn't exist

    Returns:
        The decoded string value or default if key doesn't exist
    """
    value = await redis_client.get(key)
    if value is None:
        return default
    return value


def split_content_by_delimiter(content: str, delimiter: str, chunk_size: int = 20000) -> list[str]:
    chunks = []
    start = 0

    while start < len(content):
        if start + chunk_size > len(content):
            end = len(content)
        else:
            end = content.rfind(delimiter, start, start + chunk_size)
            if end == -1:
                end = start + chunk_size

        chunks.append(content[start:end])
        start = end

    return chunks


ACCEPTABLE_HTML_TAGS = ["b", "strong", "i", "em", "code", "s", "strike", "del", "pre"]


def clean_html(html: str) -> str:
    tag_stack = []
    result = ""

    class HTMLCleaner(HTMLParser):
        """
        we can assume no attributes are present in the tags
        """

        def handle_starttag(self, tag, attrs):
            nonlocal result
            if tag in ACCEPTABLE_HTML_TAGS:
                tag_stack.append(tag)
                result += f"<{tag}>"
            else:
                result += f"&lt;{tag}&gt;"

        def handle_endtag(self, tag):
            nonlocal result
            if tag in ACCEPTABLE_HTML_TAGS and tag_stack and tag_stack[-1] == tag:
                tag_stack.pop()
                result += f"</{tag}>"
            else:
                result += f"&lt;/{tag}&gt;"

        def handle_data(self, data):
            nonlocal result
            result += data.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    parser = HTMLCleaner()
    parser.feed(html)

    result.rstrip(" \n\t")

    # close all open tags
    while len(tag_stack) > 0:
        result += f"</{tag_stack[-1]}>"
        tag_stack.pop()

    return result


TAGS_TO_KEEP = ["body", "h1", "h2", "h3", "h4", "h5", "h6", "p", "a", "ul", "ol", "li", "blockquote", "code", "pre",
                "table", "thead", "tbody", "tfoot", "tr", "td", "th", "article"]
ATTRIBUTES_TO_KEEP = ["alt"]


def clean_web_html(html: str) -> str:
    """
    Cleans out comments, scripts, css, and other non-content tags and attributes.
    """
    result = ""
    tag_stack = []

    class HTMLCleaner(HTMLParser):
        def handle_starttag(self, tag, attrs):
            nonlocal result
            tag_stack.append(tag)
            if tag in TAGS_TO_KEEP:
                result += f"<{tag}"
                for attr, value in attrs:
                    if attr in ATTRIBUTES_TO_KEEP:
                        result += f" {attr}=\"{value}\""
                result += ">"

        def handle_endtag(self, tag):
            nonlocal result
            tag_stack.pop()
            if tag in TAGS_TO_KEEP:
                result += f"</{tag}>"

        def handle_data(self, data):
            nonlocal result
            if tag_stack and tag_stack[-1] in TAGS_TO_KEEP:
                result += data

    parser = HTMLCleaner()
    parser.feed(html)
    return result


async def get_web_content(url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
        # return clean_web_html(response.text)


def rate_limit(time_window: timedelta, limit: int):
    """
    Decorator to limit the rate of interactions for a user.

    Args:
        limit: Maximum number of interactions allowed in the time window
        time_window: Time window for the rate limit
    """
    def decorator(func: Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]) -> Callable[[Update, ContextTypes.DEFAULT_TYPE], Any]:
        @wraps(func)
        async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> Any:
            if not update.message or not update.message.from_user:
                return

            user_id = update.message.from_user.id
            interaction_key = f"user:{user_id}:interactions"

            # Check interaction limit
            interaction_times_list = await redis_client.lrange(interaction_key, 0, -1)
            interaction_times_decoded = [datetime.fromtimestamp(float(ts)) for ts in interaction_times_list]
            interaction_times = [ts for ts in interaction_times_decoded if datetime.now() - ts < time_window]

            if len(interaction_times) >= limit:
                await update.message.reply_text('Interaction limit reached. Please try again later.')
                logger.info(f"Rate limit exceeded for user {user_id}")
                return

            # Record interaction time
            await redis_client.rpush(interaction_key, datetime.now().timestamp())
            await redis_client.ltrim(interaction_key, -limit, -1)

            return await func(update, context)
        return wrapper
    return decorator


def admin_required(func: Callable[[Update, CallbackContext], Coroutine]):
    @wraps(func)
    async def wrapper(update: Update, context: CallbackContext, *args, **kwargs):
        if update.effective_chat.id not in ADMIN_CHAT_ID_LIST:
            logger.warning(f"Unauthorized access to {func.__name__} from chat_id={update.effective_chat.id} user_id={update.effective_user.id}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper
