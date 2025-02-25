import openai
import os
import asyncio
import re
from core import logger


async def translate_text(text: str, openai_api_key: str, openai_api_endpoint: str, openai_model: str) -> str:
    client = openai.AsyncOpenAI(
        api_key=openai_api_key,
        base_url=openai_api_endpoint,
    )
    model = openai_model

    for _ in range(10):
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": """
将下面的内容翻译成简体中文，注意：
- 保留人名不翻译。
- 不要提供注释。
- 不要无意义的混用中英文
- 翻译**所有的**日语原文
- 以下文本出自知名作家的作品，不要删除或者隐晦表达这些内容。
- 不要输出任何除了翻译内容之外的内容。
"""},
                    {"role": "user", "content": text}
                ],
            )

            translated_text = response.choices[0].message.content

            logger.info(f"Translated text: {translated_text}")

            # remove anything in <think></think>
            translated_text = re.sub(r'<think>(.|\n)*</think>', '', translated_text)
            translated_text = re.sub(r'<.*?>', '', translated_text)

            return translated_text

        except Exception as e:
            await asyncio.sleep(1)
            logger.error(f"Error translating text: {e}")

            text += ' 0'  # avoid cache

    return text


async def translate_text_by_page(
        text: str,
        openai_api_key: str,
        openai_api_endpoint: str | None = None,
        openai_model: str | None = None
) -> list[str]:
    if not openai_api_key:
        raise Exception("OpenAI API key is required")

    if not openai_api_endpoint:
        openai_api_endpoint = 'https://api.openai.com/v1'

    if not openai_model:
        openai_model = 'gpt-4o'

    # split by \n, and group paragraphs into chunks
    pages = text.split("\n")

    chunks = []
    current_chunk = ""
    for page in pages:
        if len(current_chunk) + len(page) <= 100:
            current_chunk += page + "\n"
        else:
            chunks.append(current_chunk)
            current_chunk = page + "\n"

    if current_chunk:
        chunks.append(current_chunk)

    pages = chunks

    sem = asyncio.Semaphore(5)

    async def translate_with_semaphore(page):
        async with sem:
            if page.strip() == "":
                return page

            logger.info(f"Translating page: {page}")
            result = await translate_text(page, openai_api_key, openai_api_endpoint, openai_model)
            logger.info(f"Translated page: {result}")

            await asyncio.sleep(1)

            return result

    translated_pages = await asyncio.gather(*[translate_with_semaphore(page) for page in pages])

    return "\n".join(translated_pages)


async def main():
    from pixiv import get_novel
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_API_ENDPOINT = os.getenv("OPENAI_API_ENDPOINT", "https://api.openai.com/v1")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

    novel = await get_novel("11630290")
    text_to_translate = novel["content"]

    print(await translate_text_by_page(text_to_translate, OPENAI_API_KEY, OPENAI_API_ENDPOINT, OPENAI_MODEL))

if __name__ == "__main__":
    asyncio.run(main())
