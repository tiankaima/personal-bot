"""
tweet.py

This file contains the logic for checking for new tweets, send new tweets to corresponding users.

This requires a many-to-many mapping between twitter_id and telegram_id, we store as:

twitter_send_target:@username -> [telegram_id1, telegram_id2, ...]
telegram_sub_target:chat_id -> [twitter_username1, twitter_username2, ...]

whenever a user(chat) updates their preferences, we update the above two mappings.

To remember which tweets are already sent, we store:

tweet_id_sent:tweet_id -> 1

and finally we maintain a combined list of all the twitter_ids that we are watching. (This list would be only ipdates when `twitter_send_target` is created/a list turn empty)
"""

from core import logger, redis_client
from telegram.ext import CallbackContext
from telegram import Update, InputMediaPhoto, InputMediaVideo, LinkPreviewOptions
import os
import httpx
import re
import json
from datetime import datetime
import random
import asyncio

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
    logger.info(f"Subscribing to {username} for chat {chat_id}")

    # add to twitter_send_target
    await redis_client.sadd(f"twitter_send_target:{username}", chat_id)

    # add to telegram_sub_target
    await redis_client.sadd(f"telegram_sub_target:{chat_id}", username)

    # add to twitter_ids
    await redis_client.sadd("twitter_ids", username)


async def unsubscribe_twitter_user(username: str, chat_id: int):
    logger.info(f"Unsubscribing from {username} for chat {chat_id}")

    # remove from twitter_send_target
    await redis_client.srem(f"twitter_send_target:{username}", chat_id)

    # remove from telegram_sub_target
    await redis_client.srem(f"telegram_sub_target:{chat_id}", username)

    # remove from twitter_ids
    # Only remove from twitter_ids if no one else is subscribed to this user
    if not await redis_client.scard(f"twitter_send_target:{username}"):
        await redis_client.srem("twitter_ids", username)


async def send_tweet(url: str, context: CallbackContext, chat_id: int, reply_to_message_id: int | None = None, can_ignore: bool = False) -> None:
    async with httpx.AsyncClient() as client:
        url = url.replace("x.com", "twitter.com").replace('twitter.com', 'api.fxtwitter.com')

        response = await client.get(url, timeout=10)
        info = json.loads(response.text)

    create_timestamp = datetime.fromtimestamp(info['tweet']['created_timestamp'])
    create_timestamp_str = create_timestamp.strftime("%Y/%m/%d %H:%M:%S")

    if can_ignore and IGNORE_RETWEETS and info['tweet']['text'].startswith("RT"):
        logger.info(f"Ignoring retweet {url}")
        return

    def info_to_caption(info: dict) -> str:
        if len(info['text']):
            return f"""
<b>{info['author']['name']}</b> (<a href="{info['author']['url']}">@{info['author']['screen_name']}</a>)

{info['text']}

<a href="{info['url']}">{create_timestamp_str}</a>
"""
        else:
            return f"""
<b>{info['author']['name']}</b> (<a href="{info['author']['url']}">@{info['author']['screen_name']}</a>)

<a href="{info['url']}">{create_timestamp_str}</a>
"""

    caption = info_to_caption(info['tweet'])

    if "quote" in info['tweet']:
        caption += "<blockquote>"
        caption += info_to_caption(info['tweet']['quote'])
        caption += "</blockquote>"

    if "media" in info['tweet']:
        try:
            medias = []

            for media in info['tweet']['media']['all']:
                if media['type'] == 'photo':
                    medias.append(InputMediaPhoto(media['url']))
                elif media['type'] == 'video':
                    medias.append(InputMediaVideo(media['variants'][3]['url']))

            await context.bot.send_media_group(chat_id=chat_id, media=medias, reply_to_message_id=reply_to_message_id, caption=caption, parse_mode="HTML", write_timeout=20)
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

            await context.bot.send_media_group(chat_id=chat_id, media=medias, reply_to_message_id=reply_to_message_id, caption=caption, parse_mode="HTML", write_timeout=20)

    else:
        if can_ignore and SEND_ONLY_WITH_MEDIA:
            logger.info(f"Ignoring tweet {url} because it has no media and SEND_ONLY_WITH_MEDIA is true")
            return

        await context.bot.send_message(chat_id=chat_id, text=caption, parse_mode="HTML", reply_to_message_id=reply_to_message_id, link_preview_options=LinkPreviewOptions(is_disabled=True))


async def fetch_tweets(twitter_id: str) -> list[str]:
    logger.info(f"Fetching tweets for {twitter_id}")

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

        logger.info(tweet_urls)

        return tweet_urls


async def check_for_new_tweets(context: CallbackContext):
    logger.info("Checking for new tweets")

    # randomly select one twitter_id from twitter_ids
    twitter_id_raw = await redis_client.srandmember("twitter_ids")
    if not twitter_id_raw:
        logger.info("No twitter_ids found, skipping")
        return

    twitter_id = twitter_id_raw.decode("utf-8")
    logger.info(f"Selected twitter_id: {twitter_id}")

    # fetch the tweets
    tweet_urls = await fetch_tweets(twitter_id)

    for tweet_url in tweet_urls:
        # check if the tweet is already sent
        if await redis_client.get(f"tweet_id_sent:{tweet_url}"):
            continue

        # send the tweet to all the users that are subscribed to this twitter_id
        for chat_id in await redis_client.smembers(f"twitter_send_target:{twitter_id}"):
            chat_id = int(chat_id)
            try:
                await send_tweet(tweet_url, context, chat_id, can_ignore=True)
            except Exception as e:
                logger.error(f"Error sending tweet {tweet_url} to chat {chat_id}: {e}")

        await asyncio.sleep(random.randint(1, 3))

        # mark the tweet as sent
        await redis_client.set(f"tweet_id_sent:{tweet_url}", 1)
