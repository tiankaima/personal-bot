import json
import os
import re

import httpx
from telegram.ext import ContextTypes
from telegraph.aio import Telegraph

from core import logger, redis_client
from llm_translate import translate_text_by_page
from utils import split_content_by_delimiter

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
            f"https://www.pixiv.net/novel/show.php?id={novel_id}", headers=HEADERS
        )

        json_str = re.findall(
            r'<meta name="preload-data" id="meta-preload-data" content=\'(.*)\'>', response.text
        )

        if not json_str:
            raise ValueError("No preload-data found")

        return json.loads(json_str[0])['novel'][novel_id]


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


async def send_pixiv_novel(url: str, context: ContextTypes.DEFAULT_TYPE, user_id: int, message_id: int):
    match = PIXIV_NOVEL_URL_REGEX.match(url)
    if not match:
        logger.warning(f"Invalid Pixiv novel URL: {url}")
        return

    novel_id = match.group(1)
    novel = await get_novel(novel_id)

    page_urls = await send_to_telegraph(
        title=f"[{novel_id}] {novel['title']}",
        content=novel['content'],
        author_name=novel['userName'],
        author_url=f"https://www.pixiv.net/users/{novel['userId']}"
    )

    for page_url in page_urls:
        await context.bot.send_message(chat_id=user_id, text=page_url, reply_to_message_id=message_id)

    openai_api_key = (await redis_client.get(f"user:{user_id}:openai_api_key")) or b''
    openai_api_endpoint = (await redis_client.get(f"user:{user_id}:openai_api_endpoint")) or b''
    openai_model = (await redis_client.get(f"user:{user_id}:openai_model")) or b''

    if not openai_api_key:
        return

    translated_content = await translate_text_by_page(
        novel["content"],
        openai_api_key.decode('utf-8'),
        openai_api_endpoint.decode('utf-8'),
        openai_model.decode('utf-8')
    )

    page_urls = await send_to_telegraph(
        title=f"[{novel_id}-translated] {novel['title']}",
        content=translated_content,
        author_name=novel['userName'],
        author_url=f"https://www.pixiv.net/users/{novel['userId']}"
    )

    for page_url in page_urls:
        await context.bot.send_message(chat_id=user_id, text=page_url, reply_to_message_id=message_id)
