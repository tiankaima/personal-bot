import json
import re
from datetime import datetime, timedelta
from typing import List

import openai
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
from telegram import Update, Message
from telegram.ext import CallbackContext

from core import logger, redis_client
from pixiv import send_pixiv_novel
from tweet import send_tweet
from utils import clean_html, get_web_content, rate_limit, get_redis_value

INTERACTION_LIMIT = 10
TIME_WINDOW = timedelta(minutes=1)
TELEGRAM_MESSAGE_MAX_LENGTH = 2000
CUT_CHARACTERS = [' ', '\n']
MAX_RETRIES = 10
TOOLS: List[ChatCompletionToolParam] = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current time",
            "parameters": {
                "type": "object",
                "properties": {

                },
                "required": [],
                "additionalProperties": False
            },
        }
    }, {
        "type": "function",
        "function": {
            "name": "get_web_content",
            "description": "Get the content of a web page",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "The URL of the web page to get the content from"}
                },
                "required": ["url"],
                "additionalProperties": False
            }
        }
    }
]
DEFAULT_SYSTEM_PROMPT = """
Output in HTML instead of markdown, format the text with these tags: <b/>(bold), <i/>(italics), <code/>, <s/>(strike), <pre language="python">code</pre>; NO <p> or <br/> tags. (Only use tag when it helps the structure, don't overuse it).
Notice you'll have to escape the < and > characters (that are not part of tag) with \\ in the output.
"""

TWITTER_URL_REGEX = re.compile(r"https://(x|twitter)\.com/[^/]+/status/\d+/?.*")
PIXIV_NOVEL_URL_REGEX = re.compile(r"https://www.pixiv.net/novel/show.php\?id=(\d+).*")


@rate_limit(time_window=TIME_WINDOW, limit=INTERACTION_LIMIT)
async def handle_message(update: Update, context: CallbackContext) -> None:
    """
    Handle incoming messages from users. This function:
    1. Checks for Twitter/Pixiv URLs and handles them directly
    2. Verifies OpenAI API key and other prerequisites
    3. Retrieves conversation context from Redis if available
    4. Processes the message with OpenAI's API
    5. Sends the response back to the user

    The function uses rate limiting to prevent abuse and maintains conversation context
    through Redis storage.
    """
    logger.debug(f"Handling message: user_id={update.message.from_user.id}, chat_id={update.message.chat.id}, message_id={update.message.message_id}")

    user_id = update.message.from_user.id
    chat_id = update.message.chat.id
    message_id = update.message.message_id

    if not update.message or not update.message.from_user:
        return

    if not update.message.text or not len(update.message.text):
        logger.debug(f"Empty message received from user {user_id}")
        return

    if TWITTER_URL_REGEX.match(update.message.text):
        logger.debug(f"Twitter URL detected in message from user {user_id}")
        await send_tweet(update.message.text, context, user_id, chat_id, message_id)
        return

    if PIXIV_NOVEL_URL_REGEX.match(update.message.text):
        logger.debug(f"Pixiv novel URL detected in message from user {user_id}")
        await send_pixiv_novel(update.message.text, context, user_id, chat_id, message_id)
        return

    openai_api_key = await get_redis_value(f"user:{user_id}:openai_api_key")
    openai_api_endpoint = await get_redis_value(f"user:{user_id}:openai_api_endpoint", "https://api.openai.com/v1")
    openai_model = await get_redis_value(f"user:{user_id}:openai_model", "gpt-4")
    openai_enable_tools = (await get_redis_value(f"user:{user_id}:openai_enable_tools", "false")).lower() == "true"

    if not openai_api_key:
        logger.debug(f"OpenAI API key not configured for user {user_id}")
        if update.message.chat.type == "private":
            await update.message.reply_text('Please set your OpenAI API key using /set_openai_key <your_openai_api_key>.')
        else:
            if update.message.reply_to_message and update.message.reply_to_message.from_user.id == context.bot.id:
                await update.effective_message.set_reaction("😢")
                await update.message.reply_text('DM me to setup your OpenAI keys/endpoint/model first.')
        return

    client = openai.AsyncOpenAI(
        api_key=openai_api_key,
        base_url=openai_api_endpoint
    )

    logger.debug(f"Processing message with OpenAI: model={openai_model}, endpoint={openai_api_endpoint}, user_id={user_id}")

    user_key = f"user:{user_id}:messages"
    messages = []
    if update.message.reply_to_message:
        replied_message_id = update.message.reply_to_message.message_id
        replied_message = await redis_client.hget(user_key, str(replied_message_id))
        if replied_message:
            messages = json.loads(replied_message)
            logger.debug(f"Retrieved context from replied message {replied_message_id}")
        else:
            logger.warning(f"Context not found for replied message {replied_message_id}")
    else:
        messages = [{
            "role": "system",
            "content": DEFAULT_SYSTEM_PROMPT
        }]

    messages.append({
        "role": "user",
        "content": update.message.text
    })

    await redis_client.hset(user_key, str(message_id), json.dumps(messages))

    async def add_tool_calls_results(tool_calls: dict[int, ChoiceDeltaToolCall]):
        nonlocal messages
        logger.debug(f"Processing tool calls: {len(tool_calls)} calls")

        for tool_call in tool_calls.values():
            arguments = json.loads(tool_call.function.arguments)
            if tool_call.function and tool_call.function.name == "get_current_time":
                logger.debug("Executing get_current_time tool")

                time = datetime.now()
                time_str = time.strftime("%Y-%m-%d %H:%M:%S")
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": f"The current time is {time_str}. (UTC)"
                })
            elif tool_call.function and tool_call.function.name == "get_web_content":
                logger.debug(f"Executing get_web_content tool for URL: {arguments['url']}")
                url = arguments["url"]
                content = await get_web_content(url)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": content
                })

    async def update_reply_msg_to_user():
        nonlocal reply_msg_start, reply_msg_last_sent_end_pos, current_reply_obj, replies
        logger.debug(f"Updating reply message: start={reply_msg_start}, last_sent_end={reply_msg_last_sent_end_pos}")

        msg = f"[{openai_model}] {reply_msg}"

        if len(msg) == reply_msg_last_sent_end_pos or msg[reply_msg_start:].strip(" \n\t") == "":
            return

        try:
            while True:
                if len(msg[reply_msg_start:]) > TELEGRAM_MESSAGE_MAX_LENGTH:
                    # a cut & new reply is needed, now we determine where to cut the old message
                    trim_point = reply_msg_start + TELEGRAM_MESSAGE_MAX_LENGTH
                    while trim_point > reply_msg_start and msg[trim_point] not in CUT_CHARACTERS:
                        trim_point -= 1
                    if trim_point == reply_msg_start:
                        # if we match back to the start, just give up and cut at the max length
                        trim_point = reply_msg_start + TELEGRAM_MESSAGE_MAX_LENGTH

                    await current_reply_obj.edit_text(
                        clean_html(msg[reply_msg_start:trim_point]),
                        parse_mode="HTML"
                    )
                    reply_msg_last_sent_end_pos = trim_point
                    replies.append(current_reply_obj)

                    reply_msg_start = trim_point
                    current_reply_obj = await update.message.reply_text(
                        clean_html(msg[reply_msg_start:]),
                        reply_to_message_id=message_id
                    )
                else:
                    await current_reply_obj.edit_text(clean_html(msg[reply_msg_start:]), parse_mode="HTML")
                    reply_msg_last_sent_end_pos = len(msg)
                    break
        except Exception as e:
            logger.error(f"Failed to update reply message: {str(e)}", exc_info=True)
            raise

    async def get_assistant_reply():
        nonlocal reply_msg, messages, replies
        logger.debug("Getting assistant reply with OpenAI")

        if openai_enable_tools:
            stream = await client.chat.completions.create(
                model=openai_model,
                messages=messages,
                tools=TOOLS,
                stream=True
            )
        else:
            stream = await client.chat.completions.create(
                model=openai_model,
                messages=messages,
                stream=True
            )

        tool_calls: dict[int, ChoiceDeltaToolCall] = {}

        async for chunk in stream:
            for tool_call in chunk.choices[0].delta.tool_calls or []:
                if (index := tool_call.index) not in tool_calls:
                    tool_calls[index] = tool_call
                else:
                    tool_calls[index].function.arguments += tool_call.function.arguments or ""

            reply_msg += chunk.choices[0].delta.content or ""

            if len(reply_msg[reply_msg_last_sent_end_pos:]) > 200 or reply_msg_last_sent_end_pos == 0:
                await update_reply_msg_to_user()

        if len(reply_msg.strip(" \n\t")) > 0:
            await update_reply_msg_to_user()
            replies.append(current_reply_obj)

        if len(tool_calls) > 0:
            tool_calls_json = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments
                    }
                }
                for tool_call in tool_calls.values()
            ]

            messages.append({
                "role": "assistant",
                "content": reply_msg,
                "tool_calls": tool_calls_json
            })
            await add_tool_calls_results(tool_calls)
            return False
        else:
            messages.append({
                "role": "assistant",
                "content": reply_msg
            })
            return True

    current_reply_obj = await update.message.reply_text("...", reply_to_message_id=message_id)

    for attempt in range(MAX_RETRIES):
        logger.debug(f"Processing message attempt {attempt + 1}/{MAX_RETRIES}")
        replies: List[Message] = []
        reply_msg = ""
        reply_msg_start = 0
        reply_msg_last_sent_end_pos = 0

        no_tool_call = await get_assistant_reply()
        for reply in replies:
            # store message to Redis
            await redis_client.hset(user_key, str(reply.message_id), json.dumps(messages))

        if no_tool_call and len(reply_msg.strip(" \n\t")) > 0:
            for reply in replies:
                await redis_client.hset(user_key, str(reply.message_id), json.dumps(messages))
            logger.info(f"Successfully processed message for user {user_id}")
            break
    else:
        logger.error(f"Failed to process message after {MAX_RETRIES} attempts for user {user_id}")
        await update.message.reply_text(
            "I'm sorry, but I'm having trouble understanding your message. Please try again.")
        return

    logger.debug(f"Message handling completed for user {user_id}")
