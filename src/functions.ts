import { Env } from './env';
import './utils';
import { TelegramAPI } from './api/telegram';
import { TwitterAPI } from './api/twitter';

export async function updateUnsentMessage(env: Env): Promise<void> {
	const users = await env.DATA.get('twitter_users').then((data) => JSON.parse(data || '[]'));
	let unsent_links = await env.DATA.get('unsent_links').then((data) => JSON.parse(data || '[]'));
	const sent_links = await env.DATA.get('sent_links').then((data) => JSON.parse(data || '[]'));

	const twitter_api = new TwitterAPI();
	const twitter_cookies = (await env.DATA.get('twitter_cookies')) || '';

	const updated_links = (
		await Promise.all(
			users
				.samples(10) // limit to 10 requests
				.map(async (user: string) =>
					twitter_api
						.fetchTweetIds({
							userName: user,
							cookies: twitter_cookies,
						})
						.then((ids) => ids.map((id) => `https://twitter.com/${user}/status/${id}`))
				)
		)
	)
		.flat()
		.filter((link) => !sent_links.includes(link));
	console.info(`Updated links: ${updated_links}`);

	unsent_links = Array.from(new Set([...unsent_links, ...updated_links]));
	await env.DATA.put('unsent_links', JSON.stringify(unsent_links));
}

export async function sendUnsentMessage(env: Env): Promise<void> {
	const bot = new TelegramAPI({ botToken: env.ENV_BOT_TOKEN });
	let unsent_links = await env.DATA.get('unsent_links').then((data) => JSON.parse(data || '[]'));
	let sent_links = await env.DATA.get('sent_links').then((data) => JSON.parse(data || '[]'));

	let max_send = 10;
	const twitter_api = new TwitterAPI();

	try {
		while (unsent_links.length > 0 && --max_send > 0) {
			const link = unsent_links.pop();

			const link_info = await twitter_api.fetchTweetDetail(link);
			if (
				link_info['media'] &&
				link_info['media']['all'] &&
				link_info['media']['all'].length > 0 &&
				!link_info['text'].startsWith('RT @')
			) {
				console.info(`Sending link: ${link}`);
				await bot.sendMessage({
					chatId: env.ENV_BOT_ADMIN_CHAT_ID,
					text: link.replace('https://twitter.com/', 'https://fxtwitter.com/'),
				});
			} else {
				console.info(`No media found in link: ${link}`);
			}

			sent_links.push(link);
			await env.DATA.put('unsent_links', JSON.stringify(unsent_links));
			await env.DATA.put('sent_links', JSON.stringify(sent_links));
		}
	} catch (e) {
		console.error(e);
	}
}
