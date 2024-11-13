import { Env } from './env';
import './utils';
import { TwitterAPI } from './api/twitter';

export async function updateUnsentMessage(env: Env): Promise<void> {
	console.info('Updating unsent message');

	const users = await env.load('twitter_users');
	const unsent_links = await env.load('unsent_links');
	const sent_links = await env.load('sent_links');
	const twitter_cookies = (await env.DATA.get('twitter_cookies')) || '';

	const updated_links = await Promise.all(
		users.samples(10).map(async (user: string) =>
			TwitterAPI.fetchTweetIds({
				userName: user,
				cookies: twitter_cookies,
			}).then((ids) => ids.map((id) => `https://twitter.com/${user}/status/${id}`))
		)
	).then((e) => e.flat().filter((link) => !sent_links.includes(link)));
	console.info('Updated links:', updated_links);

	await env.DATA.put('unsent_links', JSON.stringify(Array.from(new Set([...unsent_links, ...updated_links]))));
}

export async function sendUnsentMessage(env: Env): Promise<void> {
	console.info('Sending unsent message');

	let unsent_links = await env.load('unsent_links');
	let sent_links = await env.load('sent_links');
	let send_counters = 10;

	try {
		while (unsent_links.length > 0 && send_counters-- > 0) {
			const link = unsent_links.pop()!;

			const e = await TwitterAPI.fetchTweetDetail(link);
			if (e['media'] && e['media']['all'] && e['media']['all'].length > 0 && !e['text'].startsWith('RT @')) {
				console.info(`Sending link: ${link}`);
				// await env.bot.sendMessage({
				// 	chatId: env.ENV_BOT_ADMIN_CHAT_ID,
				// 	text: link.replace('https://twitter.com/', 'https://fxtwitter.com/'),
				// });

				await env.bot.sendPhoto({
					chatId: env.ENV_BOT_ADMIN_CHAT_ID,
					photo: e['media']['all'][0]['url'],
					caption: e['text'] + '\n' + link,
				});
			} else {
				console.info(`No media found in link: ${link}, ignoring`);
			}

			sent_links.push(link);
			await env.save('unsent_links', unsent_links);
			await env.save('sent_links', sent_links);
		}
	} catch (e) {
		console.error(e);
	}

	console.log(`Total sent count = ${10 - send_counters}`);
}
