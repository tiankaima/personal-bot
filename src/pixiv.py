import json
import os
import re

import httpx
from telegram.ext import ContextTypes
from telegraph.aio import Telegraph

from core import logger, redis_client
from llm_translate import translate_text_by_page, translate_text, translate_text_stream
from utils import split_content_by_delimiter, get_redis_value

telegraph = Telegraph()

PIXIV_NOVEL_URL_REGEX = re.compile(r"https://www.pixiv.net/novel/show.php\?id=(\d+).*")

PIXIV_COOKIE = os.getenv('PIXIV_COOKIE')
if not PIXIV_COOKIE:
    raise ValueError("PIXIV_COOKIE environment variable not set")

RAW_HEADERS = f"""
Host: www.pixiv.net
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:134.0) Gecko/20100101 Firefox/134.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
DNT: 1
Sec-GPC: 1
Connection: keep-alive
Cookie: ${PIXIV_COOKIE}
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: cross-site
Priority: u=0, i
Pragma: no-cache
Cache-Control: no-cache
"""

HEADERS = {
    line.split(": ")[0]: line.split(": ")[1]
    for line in RAW_HEADERS.split("\n")
    if line
}


async def get_novel(novel_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://www.pixiv.net/ajax/novel/{novel_id}", headers=HEADERS
        )

        return json.loads(response.text)['body']


async def send_to_telegraph(title: str, content: str, author_name: str, author_url: str) -> list[str]:
    _ = await telegraph.create_account(
        short_name=author_name,
        author_name=author_name,
        author_url=author_url,
    )

    html_content_whole = content.replace("\n", "<br>")
    pages = []
    chunks = split_content_by_delimiter(html_content_whole, "<br>")

    for i, chunk in enumerate(chunks, 1):
        page = await telegraph.create_page(
            title=f"{title} Part.{i}",
            html_content=chunk,
            author_name=author_name,
            author_url=author_url,
        )
        pages.append(page)

    return [page['url'] for page in pages]


async def send_pixiv_novel_direct(
    url: str,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    message_id: int
):
    match = PIXIV_NOVEL_URL_REGEX.match(url)
    if not match:
        logger.warning(f"Invalid Pixiv novel URL: {url}")
        return

    novel_id = match.group(1)
    novel = await get_novel(novel_id)

    openai_api_key = await get_redis_value(f'user:{user_id}:openai_api_key')
    openai_api_endpoint = await get_redis_value(f'user:{user_id}:openai_api_endpoint')
    openai_model = await get_redis_value(f'user:{user_id}:openai_model')
    pixiv_translation = (await get_redis_value(f'user:{user_id}:pixiv_translation', 'false')).lower() == 'true'

    if not openai_api_key or not pixiv_translation:
        return

    # Split content into paragraphs
    paragraphs = novel["content"].split("\n")
    current_batch = ""
    translated_content = []
    message_context = []

    for paragraph in paragraphs:
        if len(current_batch) + len(paragraph) <= 800:
            current_batch += paragraph + "\n"
        else:
            if current_batch.strip():
                # Translate current batch
                translated = await translate_text(
                    current_batch,
                    openai_api_key=openai_api_key,
                    openai_api_endpoint=openai_api_endpoint,
                    openai_model=openai_model
                )

                # Send translated batch to user
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"<b>[{novel_id}] {novel['title']}</b>\n{translated.strip(" \n")}",
                    reply_to_message_id=message_id,
                    parse_mode="HTML"
                )

                # Add to context for next batch
                message_context.append(translated)
                translated_content.append(translated)

            current_batch = paragraph + "\n"

    # Handle the last batch
    if current_batch.strip():
        translated = await translate_text(
            current_batch,
            openai_api_key=openai_api_key,
            openai_api_endpoint=openai_api_endpoint,
            openai_model=openai_model
        )

        await context.bot.send_message(
            chat_id=chat_id,
            text=f"<b>[{novel_id}] {novel['title']}</b>\n\n{translated}",
            reply_to_message_id=message_id,
            parse_mode="HTML"
        )

        translated_content.append(translated)

    return "\n".join(translated_content)


async def send_pixiv_novel_streaming(
    url: str,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    message_id: int
):
    match = PIXIV_NOVEL_URL_REGEX.match(url)
    if not match:
        logger.warning(f"Invalid Pixiv novel URL: {url}")
        return

    novel_id = match.group(1)
    novel = await get_novel(novel_id)

    openai_api_key = await get_redis_value(f'user:{user_id}:openai_api_key')
    openai_api_endpoint = await get_redis_value(f'user:{user_id}:openai_api_endpoint')
    openai_model = await get_redis_value(f'user:{user_id}:openai_model')
    pixiv_translation = (await get_redis_value(f'user:{user_id}:pixiv_translation', 'false')).lower() == 'true'

    if not openai_api_key or not pixiv_translation:
        return

    # Split content into paragraphs
    paragraphs = novel["content"].split("\n")
    current_batch = ""
    translated_content = []
    message_context = []
    translated_context = []
    
    # Initialize message objects for streaming
    current_reply_obj = None
    reply_msg = ""
    reply_msg_start = 0
    reply_msg_last_sent_end_pos = 0
    replies = []
    TELEGRAM_MESSAGE_MAX_LENGTH = 4000
    CUT_CHARACTERS = [' ', '\n']
    
    async def update_reply_msg_to_user(chunk):
        nonlocal reply_msg, reply_msg_start, reply_msg_last_sent_end_pos, current_reply_obj, replies
        
        reply_msg += chunk
        
        if len(reply_msg[reply_msg_last_sent_end_pos:]) > 100 or reply_msg_last_sent_end_pos == 0:
            msg = f"<b>[{novel_id}] {novel['title']}</b>\n\n{reply_msg}"
            
            try:
                if len(msg[reply_msg_start:]) > TELEGRAM_MESSAGE_MAX_LENGTH:
                    # A cut & new reply is needed, determine where to cut the old message
                    trim_point = reply_msg_start + TELEGRAM_MESSAGE_MAX_LENGTH
                    while trim_point > reply_msg_start and msg[trim_point] not in CUT_CHARACTERS:
                        trim_point -= 1
                    if trim_point == reply_msg_start:
                        # If we match back to the start, just give up and cut at the max length
                        trim_point = reply_msg_start + TELEGRAM_MESSAGE_MAX_LENGTH
                    
                    if current_reply_obj is None:
                        # First message
                        current_reply_obj = await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg[reply_msg_start:trim_point],
                            reply_to_message_id=message_id,
                            parse_mode="HTML"
                        )
                    else:
                        # Update existing message
                        await current_reply_obj.edit_text(
                            msg[reply_msg_start:trim_point],
                            parse_mode="HTML"
                        )
                    
                    reply_msg_last_sent_end_pos = trim_point
                    replies.append(current_reply_obj)
                    
                    reply_msg_start = trim_point
                    current_reply_obj = await context.bot.send_message(
                        chat_id=chat_id,
                        text=msg[reply_msg_start:],
                        reply_to_message_id=message_id,
                        parse_mode="HTML"
                    )
                else:
                    if current_reply_obj is None:
                        # First message
                        current_reply_obj = await context.bot.send_message(
                            chat_id=chat_id,
                            text=msg[reply_msg_start:],
                            reply_to_message_id=message_id,
                            parse_mode="HTML"
                        )
                    else:
                        # Update existing message
                        await current_reply_obj.edit_text(
                            msg[reply_msg_start:],
                            parse_mode="HTML"
                        )
                    
                    reply_msg_last_sent_end_pos = len(msg)
            except Exception as e:
                logger.error(f"Failed to update reply message: {str(e)}", exc_info=True)
                raise

    for paragraph in paragraphs:
        if len(current_batch) + len(paragraph) <= 800:
            current_batch += paragraph + "\n\n"
        else:
            if current_batch.strip():
                # Add current batch to message context
                message_context.append(current_batch)
                
                # Translate current batch using streaming with context
                translated = await translate_text_stream(
                    current_batch,
                    openai_api_key=openai_api_key,
                    openai_api_endpoint=openai_api_endpoint,
                    openai_model=openai_model,
                    callback=update_reply_msg_to_user,
                    message_context=message_context[:-1],  # Exclude current batch
                    translated_context=translated_context
                )
                
                # Add to translated context
                translated_context.append(translated)
                translated_content.append(translated)
            
            current_batch = paragraph + "\n\n"

    # Handle the last batch
    if current_batch.strip():
        # Add current batch to message context
        message_context.append(current_batch)
        
        # Translate last batch using streaming with context
        translated = await translate_text_stream(
            current_batch,
            openai_api_key=openai_api_key,
            openai_api_endpoint=openai_api_endpoint,
            openai_model=openai_model,
            callback=update_reply_msg_to_user,
            message_context=message_context[:-1],  # Exclude current batch
            translated_context=translated_context
        )
        
        # Add to translated context
        translated_context.append(translated)
        translated_content.append(translated)
    
    # Send any remaining content
    if reply_msg and reply_msg_last_sent_end_pos < len(reply_msg):
        msg = f"<b>[{novel_id}] {novel['title']}</b>\n\n{reply_msg}"
        if current_reply_obj is None:
            current_reply_obj = await context.bot.send_message(
                chat_id=chat_id,
                text=msg[reply_msg_start:],
                reply_to_message_id=message_id,
                parse_mode="HTML"
            )
        else:
            await current_reply_obj.edit_text(
                msg[reply_msg_start:],
                parse_mode="HTML"
            )
        replies.append(current_reply_obj)

    return "\n".join(translated_content)


async def send_pixiv_novel(
    url: str,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    message_id: int
):
    match = PIXIV_NOVEL_URL_REGEX.match(url)
    if not match:
        logger.warning(f"Invalid Pixiv novel URL: {url}")
        return

    novel_id = match.group(1)
    novel = await get_novel(novel_id)

    streaming_translation = (await get_redis_value(f'user:{user_id}:pixiv_streaming_translation', 'true')).lower() == 'true'
    direct_translation = (await get_redis_value(f'user:{user_id}:pixiv_direct_translation', 'true')).lower() == 'true'

    if streaming_translation:
        await send_pixiv_novel_streaming(url, context, user_id, chat_id, message_id)
        return
    elif direct_translation:
        await send_pixiv_novel_direct(url, context, user_id, chat_id, message_id)
        return

    page_urls = await send_to_telegraph(
        title=f"[{novel_id}] {novel['title']}",
        content=novel['content'],
        author_name=novel['userName'],
        author_url=f"https://www.pixiv.net/users/{novel['userId']}"
    )

    for page_url in page_urls:
        await context.bot.send_message(chat_id=user_id, text=page_url, reply_to_message_id=message_id)

    openai_api_key = await get_redis_value(f'user:{user_id}:openai_api_key')
    openai_api_endpoint = await get_redis_value(f'user:{user_id}:openai_api_endpoint')
    openai_model = await get_redis_value(f'user:{user_id}:openai_model')
    pixiv_translation = (await get_redis_value(f'user:{user_id}:pixiv_translation', 'false')).lower() == 'true'

    if not openai_api_key or not pixiv_translation:
        return

    translated_content = await translate_text_by_page(
        novel["content"],
        openai_api_key,
        openai_api_endpoint,
        openai_model
    )

    page_urls = await send_to_telegraph(
        title=f"[{novel_id}-translated] {novel['title']}",
        content=translated_content,
        author_name=novel['userName'],
        author_url=f"https://www.pixiv.net/users/{novel['userId']}"
    )

    for page_url in page_urls:
        await context.bot.send_message(chat_id=chat_id, text=page_url, reply_to_message_id=message_id)
