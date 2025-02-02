import httpx
import asyncio
import os
import re
import json
from telegraph.aio import Telegraph
from telegram.ext import ContextTypes

telegraph = Telegraph()


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


async def send_to_telegraph(novel_id: str) -> list[str]:
    novel = await get_novel(novel_id)

    _ = await telegraph.create_account(
        short_name=novel['userName'],
        author_name=novel['userName'],
        author_url=f"https://www.pixiv.net/users/{novel['userId']}",
    )

    html_content_whole = novel['content'].replace("\n", "<br>")

    pages = []
    start = 0
    count = 1

    while start < len(html_content_whole):
        if start + 20000 > len(html_content_whole):
            end = len(html_content_whole)
        else:
            end = html_content_whole.rfind("<br>", start, start + 20000)
            if end == -1:
                end = start + 20000

        html_content = f'<p>{html_content_whole[start:end]}</p>'

        page = await telegraph.create_page(
            title=f"[{novel_id}.{count}] {novel['title']}",
            html_content=html_content,
            author_name=novel['userName'],
            author_url=f"https://www.pixiv.net/users/{novel['userId']}",
        )

        pages.append(page)

        start = end
        count += 1

    return [page['url'] for page in pages]

async def send_pixiv_novel(novel_id: str, context: ContextTypes.DEFAULT_TYPE, user_id: int, message_id: int):
    page_urls = await send_to_telegraph(novel_id)
    for page_url in page_urls:
        await context.bot.send_message(chat_id=user_id, text=page_url, reply_to_message_id=message_id)

if __name__ == "__main__":
    novel_id = "11630290"
    asyncio.run(send_to_telegraph(novel_id))
