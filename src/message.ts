import { Env } from './env';
import { TelegramAPI } from './api/telegram';
import { TwitterAPI } from './api/twitter';
import { scheduleJob } from './schedule';

async function handleMessageStart(env: Env, chatId: string): Promise<void> {
	// `/start`
	const bot = new TelegramAPI({ botToken: env.ENV_BOT_TOKEN });

	await bot.sendMessage({
		chatId,
		text: `
Welcome, your chat id is ${chatId}

<b>For most commands, you need to be an admin to use them. Contact @tiankaima if you need help.</b>
`,
		parseMode: 'HTML',
	});
}

async function handleDebugHTML(env: Env, chatId: string): Promise<void> {
	const bot = new TelegramAPI({ botToken: env.ENV_BOT_TOKEN });

	await bot.sendMessage({
		chatId,
		text: `
<b>bold</b>, <strong>bold</strong>
<i>italic</i>, <em>italic</em>
<a href="URL">inline URL</a>
<code>inline fixed-width code</code>
<pre>pre-formatted fixed-width code block</pre>
`,
		parseMode: 'HTML',
	});
}

async function handleMessageSet(env: Env, chatId: string, text: string) {
	// `/set KEY VALUE`
	const bot = new TelegramAPI({ botToken: env.ENV_BOT_TOKEN });

	// VALUE might contain spaces
	const [_, key, ...valueParts] = text.split(' ');
	const value = valueParts.join(' ');

	const originalValue = await env.DATA.get(key);
	await env.DATA.put(key, value);
	await bot.sendMessage({
		chatId,
		text: `Set ${key} from ${originalValue} to ${value}`,
	});
}

async function handleMessageGet(env: Env, chatId: string, text: string) {
	// `/get KEY`
	const bot = new TelegramAPI({ botToken: env.ENV_BOT_TOKEN });

	const [_, key] = text.split(' ');

	const value = await env.DATA.get(key);
	await bot.sendMessage({
		chatId,
		text: `Value of ${key} is ${value}`,
	});
}

async function handleMessageToggleTwitterUser(env: Env, chatId: string, text: string) {
	// `/toggleTwitterUser USERNAME`
	const bot = new TelegramAPI({ botToken: env.ENV_BOT_TOKEN });

	const [_, userName] = text.split(' ');

	const users = await env.DATA.get('twitter_users').then((data) => JSON.parse(data || '[]'));
	const index = users.indexOf(userName);
	if (index === -1) {
		users.push(userName);
		await bot.sendMessage({
			chatId,
			text: `Added ${userName} to the list`,
		});
	} else {
		users.splice(index, 1);
		await bot.sendMessage({
			chatId,
			text: `Removed ${userName} from the list`,
		});
	}

	await env.DATA.put('twitter_users', JSON.stringify(users));
}

async function handleMessageDebug(env: Env, chatId: string): Promise<void> {
	const bot = new TelegramAPI({ botToken: env.ENV_BOT_TOKEN });

	try {
		const twitter_api = new TwitterAPI({});
		const ids = await twitter_api.fetchTweetIds({
			userName: 'tiankaima',
			cookies: (await env.DATA.get('twitter_cookies')) || '',
		});
		await bot.sendMessage({
			chatId,
			text: JSON.stringify(ids, null, 2),
		});

		const details = await twitter_api.fetchTweetDetails({ userName: 'tiankaima', idList: ids.slice(0, 2) });
		await bot.sendMessage({
			chatId,
			text: JSON.stringify(details, null, 2),
		});
	} catch (e) {
		await bot.sendMessage({
			chatId,
			text: e.message,
		});
	}

	return;
}

export async function handleMessageText(env: Env, chatId: string, text: string): Promise<void> {
	console.info(`Received message from ${chatId}: ${text}`);

	if (text.startsWith('/start')) {
		return await handleMessageStart(env, chatId);
	}

	// Requires ADMIN previlige from now on
	if (chatId !== env.ENV_BOT_ADMIN_CHAT_ID) {
		return;
	}
	if (text.startsWith('/set')) {
		return await handleMessageSet(env, chatId, text);
	}
	if (text.startsWith('/get')) {
		return await handleMessageGet(env, chatId, text);
	}
	if (text.startsWith('/toggleTwitterUser')) {
		return await handleMessageToggleTwitterUser(env, chatId, text);
	}
	if (text.startsWith('/debugHTML')) {
		return await handleDebugHTML(env, chatId);
	}
	if (text.startsWith('/debugSchedule')) {
		await scheduleJob(env);
		return;
	}
	if (text.startsWith('/debug')) {
		return await handleMessageDebug(env, chatId);
	}
}
