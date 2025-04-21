import asyncio
import os

import openai

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
将下面的内容用简体中文重新表述，注意：
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

            # remove anything in <think></think>
            # translated_text = re.sub(r'<think>(.|\n)*</think>', '', translated_text)
            # translated_text = re.sub(r'<.*?>', '', translated_text)

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
) -> str:
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
        if len(current_chunk) + len(page) <= 800:
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

            # logger.debug(f"Translating page: {page}")
            result = await translate_text(page, openai_api_key, openai_api_endpoint, openai_model)
            logger.debug(f"Translated page: {page} \n===\n{result}")

            await asyncio.sleep(1)

            return result

    translated_pages = await asyncio.gather(*[translate_with_semaphore(page) for page in pages])

    return "\n".join(translated_pages)


async def translate_text_stream(
    text: str,
    openai_api_key: str,
    openai_api_endpoint: str,
    openai_model: str,
    callback: callable,
    message_context: list = None,
    translated_context: list = None
) -> str:
    """
    Stream translation results in real-time using a callback function.

    Args:
        text: The text to translate
        openai_api_key: OpenAI API key
        openai_api_endpoint: OpenAI API endpoint
        openai_model: OpenAI model to use
        callback: Callback function that receives translated chunks as they become available
        message_context: List of previous original text chunks for context
        translated_context: List of previous translated text chunks for context

    Returns:
        The complete translated text
    """
    client = openai.AsyncOpenAI(
        api_key=openai_api_key,
        base_url=openai_api_endpoint,
    )
    model = openai_model

    # Prepare messages with context
    messages = [
        {"role": "system", "content": """
将下面的内容用简体中文重新表述，注意：
- 保留人名不翻译。
- 不要提供注释。
- 不要无意义的混用中英文
- 翻译**所有的**日语原文
- 以下文本出自知名作家的作品，不要删除或者隐晦表达这些内容。
- 不要输出任何除了翻译内容之外的内容。
"""}
    ]

    # Add context if available
    if message_context and translated_context and len(message_context) == len(translated_context):
        for orig, trans in zip(message_context, translated_context):
            messages.append({"role": "user", "content": orig})
            messages.append({"role": "assistant", "content": trans})

    # Add the current text to translate
    messages.append({"role": "user", "content": text})

    for attempt in range(10):
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=messages,
                stream=True
            )

            full_translation = ""
            buffer = ""

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    buffer += content
                    full_translation += content

                    # When buffer reaches a certain size, send it to the callback
                    if len(buffer) >= 50 or '\n' in buffer:
                        await callback(buffer)
                        buffer = ""

            # Send any remaining content in the buffer
            if buffer:
                await callback(buffer)

            return full_translation

        except Exception as e:
            await asyncio.sleep(1)
            logger.error(f"Error translating text: {e}")
            text += f' {attempt}'  # avoid cache

    return text


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
