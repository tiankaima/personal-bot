"""
tweet.py

This file contains the logic for checking for new tweets, send new tweets to corresponding users.

Redis key structure:
- tweets:sent:{username}:{post_id} -> 1  # Track sent tweets
- tweets:urls:queue -> [tweet_url1, tweet_url2, ...]  # Queue of tweet URLs to be sent
- tweets:subscriptions:user:{telegram_id} -> [twitter_username1, twitter_username2, ...]  # User's subscriptions
- tweets:targets:user:{twitter_username} -> [telegram_id1, telegram_id2, ...]  # Target users for each Twitter user

This requires a many-to-many mapping between twitter_id and telegram_id, we store as:

twitter_send_target:@username -> [telegram_id1, telegram_id2, ...]
telegram_sub_target:chat_id -> [twitter_username1, twitter_username2, ...]

whenever a user(chat) updates their preferences, we update the above two mappings.

To remember which tweets are already sent, we store:

tweets:sent:{username}:{post_id} -> 1

and finally we maintain a combined list of all the twitter_ids that we are watching. (This list would be only ypdates when `twitter_send_target` is created/a list turn empty)

---
update (2025-04-22)

migration command: (stage 1)

# Migrate tweet_id_sent to tweets:sent
redis-cli --scan --pattern "tweet_id_sent:*" | while read key; do
    new_key="tweets:sent:${key#tweet_id_sent:}"
    redis-cli rename "$key" "$new_key"
done

# Migrate tweet_url_to_be_sent to tweets:urls:queue
redis-cli rename tweet_url_to_be_sent tweets:urls:queue

# Migrate telegram_sub_target to tweets:subscriptions:user
redis-cli --scan --pattern "telegram_sub_target:*" | while read key; do
    new_key="tweets:subscriptions:user:${key#telegram_sub_target:}"
    redis-cli rename "$key" "$new_key"
done

# Migrate twitter_send_target to tweets:targets:user
redis-cli --scan --pattern "twitter_send_target:*" | while read key; do
    new_key="tweets:targets:user:${key#twitter_send_target:}"
    redis-cli rename "$key" "$new_key"
done

migration command: (stage 2)

# Migrate tweets:sent:{url} to tweets:sent:{username}:{post_id}
redis-cli --scan --pattern "tweets:sent:https://x.com/*" | while read key; do
    url="${key#tweets:sent:}"
    username=$(echo "$url" | cut -d'/' -f4)
    post_id=$(echo "$url" | cut -d'/' -f6)
    new_key="tweets:sent:${username}:${post_id}"
    redis-cli rename "$key" "$new_key"
done

Merged:

#!/bin/bash

# Migrate all tweet-related keys in one go
redis-cli --scan --pattern "tweet_id_sent:*" | while read key; do
    # Extract the URL from the old key
    url="${key#tweet_id_sent:}"
    # Extract username and post_id from URL
    username=$(echo "$url" | cut -d'/' -f4)
    post_id=$(echo "$url" | cut -d'/' -f6)
    # Create new key and rename
    new_key="tweets:sent:${username}:${post_id}"
    redis-cli rename "$key" "$new_key"
done

# Rename the queue key
redis-cli rename tweet_url_to_be_sent tweets:urls:queue

# Migrate subscription keys
redis-cli --scan --pattern "telegram_sub_target:*" | while read key; do
    new_key="tweets:subscriptions:user:${key#telegram_sub_target:}"
    redis-cli rename "$key" "$new_key"
done

# Migrate target keys
redis-cli --scan --pattern "twitter_send_target:*" | while read key; do
    new_key="tweets:targets:user:${key#twitter_send_target:}"
    redis-cli rename "$key" "$new_key"
done

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


async def subscribe_twitter_user(twitter_username: str, chat_id: int) -> str | None:
    twitter_username = twitter_username.lower()
    if twitter_username.startswith('@'):
        twitter_username = twitter_username[1:]

    # Add to user's subscriptions
    await redis_client.sadd(f"tweets:subscriptions:user:{chat_id}", twitter_username)
    # Add to Twitter user's targets
    await redis_client.sadd(f"tweets:targets:user:{twitter_username}", chat_id)

    return f"Subscribed to @{twitter_username}"


async def unsubscribe_twitter_user(twitter_username: str, chat_id: int) -> str | None:
    twitter_username = twitter_username.lower()
    if twitter_username.startswith('@'):
        twitter_username = twitter_username[1:]

    # Remove from user's subscriptions
    await redis_client.srem(f"tweets:subscriptions:user:{chat_id}", twitter_username)
    # Remove from Twitter user's targets
    await redis_client.srem(f"tweets:targets:user:{twitter_username}", chat_id)

    return f"Unsubscribed from @{twitter_username}"


async def list_twitter_subscription(chat_id: int) -> str:
    """List all Twitter users that the chat is subscribed to."""
    subscribed_users = await redis_client.smembers(f"tweets:subscriptions:user:{chat_id}")
    if not subscribed_users:
        return "You are not subscribed to any Twitter users."

    message = "Your subscribed Twitter users:\n\n"
    for username in subscribed_users:
        message += f"• @{username}\n"

    return message


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


async def check_for_new_tweets(context: CallbackContext) -> None:
    logger.debug("Checking for new tweets...")

    # Get all Twitter usernames we're watching
    twitter_usernames = set()
    async for key in redis_client.scan_iter("tweets:targets:user:*"):
        username = key.split(":")[-1]
        twitter_usernames.add(username)

    if not twitter_usernames:
        logger.debug("No Twitter users to check")
        return

    for username in twitter_usernames:
        try:
            tweet_urls = await fetch_tweets(username)
            for tweet_url in tweet_urls:
                # Extract post ID from URL
                post_id = tweet_url.split("/")[-1]
                # Check if tweet was already sent
                if await redis_client.exists(f"tweets:sent:{username}:{post_id}"):
                    continue

                # Add to queue
                await redis_client.rpush(f"tweets:urls:queue", tweet_url)
                # Mark as sent
                await redis_client.set(f"tweets:sent:{username}:{post_id}", 1)

        except Exception as e:
            logger.error(f"Error checking tweets for @{username}: {e}", exc_info=True)


async def send_tweets(context: CallbackContext) -> None:
    logger.debug("Sending queued tweets...")

    # Get all queued tweet URLs
    tweet_urls = await redis_client.lrange(f"tweets:urls:queue", 0, -1)
    if not tweet_urls:
        return

    for tweet_url in tweet_urls:
        try:
            # Extract username from URL
            username = tweet_url.split("/")[3].lower()

            # Get target users
            target_users = await redis_client.smembers(f"tweets:targets:user:{username}")
            if not target_users:
                continue

            # Send to each target user
            for user_id in target_users:
                await send_tweet(
                    url=tweet_url,
                    context=context,
                    user_id=int(user_id),
                    chat_id=int(user_id),
                    can_ignore=True
                )

            # Remove from queue
            await redis_client.lrem(f"tweets:urls:queue", 1, tweet_url)

        except Exception as e:
            logger.error(f"Error sending tweet {tweet_url}: {e}", exc_info=True)
