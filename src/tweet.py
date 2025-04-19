"""
tweet.py

This file contains the logic for checking for new tweets, send new tweets to corresponding users.

This requires a many-to-many mapping between twitter_id and telegram_id, we store as:

twitter_send_target:@username -> [telegram_id1, telegram_id2, ...]
telegram_sub_target:chat_id -> [twitter_username1, twitter_username2, ...]

whenever a user(chat) updates their preferences, we update the above two mappings.

To remember which tweets are already sent, we store:

tweet_id_sent:tweet_id -> 1

and finally we maintain a combined list of all the twitter_ids that we are watching. (This list would be only ypdates when `twitter_send_target` is created/a list turn empty)

---

update (2025-02-02)

we divide the sending process into two parts:

- fetch tweet url from Twitter
- send tweet to telegram

an additional set is used to cache the fetched tweet urls:

tweet_url_to_be_sent: [tweet_url1, tweet_url2, ...]
"""

import asyncio
import json
import os
import random
import re
from datetime import datetime

import httpx
from telegram import InputMediaPhoto, InputMediaVideo, LinkPreviewOptions
from telegram.ext import CallbackContext

from core import logger, redis_client
from llm_translate import translate_text
from utils import get_redis_value

TWITTER_COOKIE = os.getenv("TWITTER_COOKIE")
if not TWITTER_COOKIE:
    raise ValueError("TWITTER_COOKIE environment variable not set")

SEND_ONLY_WITH_MEDIA = os.getenv("SEND_ONLY_WITH_MEDIA", "true").lower() == "true"
IGNORE_RETWEETS = os.getenv("IGNORE_RETWEETS", "true").lower() == "true"

RAW_HEADERS = f"""
Host: syndication.twitter.com
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
Accept-Encoding: gzip, deflate, br, zstd
DNT: 1
Sec-GPC: 1
Connection: keep-alive
Cookie: ${TWITTER_COOKIE}
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


async def subscribe_twitter_user(username: str, chat_id: int):
    await redis_client.sadd(f"twitter_send_target:{username}", chat_id)
    await redis_client.sadd(f"telegram_sub_target:{chat_id}", username)
    await redis_client.sadd("twitter_ids", username)


async def unsubscribe_twitter_user(username: str, chat_id: int):
    await redis_client.srem(f"twitter_send_target:{username}", chat_id)
    await redis_client.srem(f"telegram_sub_target:{chat_id}", username)
    if not await redis_client.scard(f"twitter_send_target:{username}"):
        await redis_client.srem("twitter_ids", username)


async def get_all_subscribed_users(chat_id: int) -> list[str]:
    twitter_usernames = await redis_client.smembers(f"telegram_sub_target:{chat_id}")
    if not twitter_usernames:
        return []
    return twitter_usernames


async def send_tweet(
        url: str,
        context: CallbackContext,
        user_id: int,
        chat_id: int,
        reply_to_message_id: int | None = None,
        can_ignore: bool = False
) -> None:
    async with httpx.AsyncClient() as client:
        url = url.replace("x.com", "twitter.com").replace('twitter.com', 'api.fxtwitter.com')

        response = await client.get(url, timeout=10)
        info = json.loads(response.text)

    create_timestamp = datetime.fromtimestamp(info['tweet']['created_timestamp'])
    create_timestamp_str = create_timestamp.strftime("%Y/%m/%d %H:%M:%S")

    if can_ignore and IGNORE_RETWEETS and info['tweet']['text'].startswith("RT"):
        logger.debug(f"Ignoring tweet {url} because it's a retweet")
        return

    async def info_to_caption(info: dict) -> str:
        if len(info['text']):
            openai_api_key = await get_redis_value(f'user:{user_id}:openai_api_key')
            openai_api_endpoint = await get_redis_value(f'user:{user_id}:openai_api_endpoint')
            openai_model = await get_redis_value(f'user:{user_id}:openai_model')
            twitter_translation = (await get_redis_value(f'user:{user_id}:twitter_translation', 'false')).lower() == 'true'

            if openai_api_key and twitter_translation:
                logger.debug(f"Translating tweet {url} to {openai_model}")

                translated = (await translate_text(
                    info['text'],
                    openai_api_key=openai_api_key,
                    openai_api_endpoint=openai_api_endpoint,
                    openai_model=openai_model
                )).strip(' \n')

                return f"""
<b>{info['author']['name']}</b> (<a href="{info['author']['url']}">@{info['author']['screen_name']}</a>)

{info['text'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}

===

{translated.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}

<a href="{info['url']}">{create_timestamp_str}</a>
"""
            else:
                return f"""
<b>{info['author']['name']}</b> (<a href="{info['author']['url']}">@{info['author']['screen_name']}</a>)

{info['text'].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}

<a href="{info['url']}">{create_timestamp_str}</a>
"""

        else:
            return f"""
<b>{info['author']['name']}</b> (<a href="{info['author']['url']}">@{info['author']['screen_name']}</a>)

<a href="{info['url']}">{create_timestamp_str}</a>
"""

    caption = await info_to_caption(info['tweet'])

    if "quote" in info['tweet']:
        caption += "<blockquote>"
        caption += await info_to_caption(info['tweet']['quote'])
        caption += "</blockquote>"

    if "media" in info['tweet']:
        try:
            medias = []

            for media in info['tweet']['media']['all']:
                if media['type'] == 'photo':
                    medias.append(InputMediaPhoto(media['url']))
                elif media['type'] == 'video':
                    medias.append(InputMediaVideo(media['variants'][3]['url']))
                elif media['type'] == 'gif':
                    medias.append(InputMediaVideo(media['variants'][0]['url']))

            await context.bot.send_media_group(
                chat_id=chat_id,
                media=medias,
                reply_to_message_id=reply_to_message_id,
                caption=caption,
                parse_mode="HTML",
                write_timeout=20
            )

        except Exception as e:
            logger.error(f"Error fetching media for tweet {url}: {e}")
            medias = []

            async with httpx.AsyncClient() as client:
                for media in info['tweet']['media']['all']:
                    if media['type'] == 'photo':
                        response = await client.get(media['url'])
                        medias.append(InputMediaPhoto(response.content))
                    elif media['type'] == 'video':
                        response = await client.get(media['variants'][3]['url'])
                        medias.append(InputMediaVideo(response.content))
                    elif media['type'] == 'gif':
                        response = await client.get(media['variants'][0]['url'])
                        medias.append(InputMediaVideo(response.content))

            await context.bot.send_media_group(
                chat_id=chat_id,
                media=medias,
                reply_to_message_id=reply_to_message_id,
                caption=caption,
                parse_mode="HTML",
                write_timeout=20
            )

    else:
        if can_ignore and SEND_ONLY_WITH_MEDIA:
            logger.debug(f"Ignoring tweet {url} because it has no media and SEND_ONLY_WITH_MEDIA is true")
            return

        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
            reply_to_message_id=reply_to_message_id,
            link_preview_options=LinkPreviewOptions(is_disabled=True)
        )


async def fetch_tweets(twitter_id: str) -> list[str]:
    logger.debug(f"Fetching tweets for {twitter_id}")

    # visit https://syndication.twitter.com/srv/timeline-profile/screen-name/{twitter_id}, regex all x.com/@twitter_id/status/...
    # and return the list of tweets
    async with httpx.AsyncClient(proxy="http://meta:7890") as client:
        response = await client.get(
            f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{twitter_id}",
            headers=HEADERS,
            timeout=10,
        )
        tweet_ids = re.findall(r"tweet-(\d{19})", response.text)
        tweet_urls = [f"https://x.com/{twitter_id}/status/{tweet_id}" for tweet_id in tweet_ids]
        return tweet_urls


async def check_for_new_tweets(context: CallbackContext):
    logger.debug("Checking for new tweets")

    # randomly select one twitter_id from twitter_ids
    twitter_id = await redis_client.srandmember("twitter_ids")
    if not twitter_id:
        logger.debug("No twitter_ids found, skipping")
        return

    logger.debug(f"Selected twitter_id: {twitter_id}")

    # fetch the tweets
    tweet_urls = await fetch_tweets(twitter_id)
    new_url_count = 0

    for tweet_url in tweet_urls:
        # check if the tweet is already sent
        if await redis_client.get(f"tweet_id_sent:{tweet_url}"):
            continue

        new_url_count += 1
        await redis_client.sadd("tweet_url_to_be_sent", tweet_url)

    logger.debug(f"Found {new_url_count} new tweets")


async def send_tweets(context: CallbackContext):
    tweet_urls = await redis_client.smembers("tweet_url_to_be_sent")
    if not tweet_urls:
        logger.debug("No tweet_url_to_be_sent found, skipping")
        return

    for tweet_url in tweet_urls:
        twitter_id = re.search(r"https://x\.com/(\w+)/status/(\d+)", tweet_url).group(1)

        for chat_id in await redis_client.smembers(f"twitter_send_target:{twitter_id}"):
            chat_id = int(chat_id)
            try:
                await send_tweet(tweet_url, context, chat_id, can_ignore=True)
                logger.info(f"Sent {tweet_url} to chat {chat_id}")
            except Exception as e:
                logger.error(f"Error sending tweet {tweet_url} to chat {chat_id}: {e}")

        # mark the tweet as sent
        await redis_client.set(f"tweet_id_sent:{tweet_url}", 1)
        await redis_client.srem("tweet_url_to_be_sent", tweet_url)

        await asyncio.sleep(random.randint(2, 4))
