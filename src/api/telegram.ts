export class TelegramAPI {
	botToken: string;

	constructor(botToken: string) {
		this.botToken = botToken;
	}

	apiUrl({ methodName, params }: { methodName: string; params: Record<string, any> }): string {
		const url = new URL(`https://api.telegram.org/bot${this.botToken}/${methodName}`);
		for (const key in params) {
			url.searchParams.set(key, params[key]);
		}
		return url.toString();
	}

	async setWebhook({ webhookUrl, webhookSecret }: { webhookUrl: string; webhookSecret: string }): Promise<string> {
		const url = this.apiUrl({
			methodName: 'setWebhook',
			params: {
				url: webhookUrl,
				secret_token: webhookSecret,
			},
		});
		const r = await fetch(url).then((res) => res.json());
		return JSON.stringify(r);
	}

	async sendMessage({
		chatId,
		text,
		notify = true,
		parseMode = '',
	}: {
		chatId: string;
		text: string;
		notify?: boolean;
		parseMode?: string;
	}): Promise<string> {
		const url = this.apiUrl({
			methodName: 'sendMessage',
			params: {
				chat_id: chatId,
				text: text.slice(0, 4096),
				disable_notification: !notify,
				parse_mode: parseMode,
			},
		});
		const r = await fetch(url).then((res) => res.json());
		return JSON.stringify(r);
	}

	async fowardMessage({
		chatId,
		fromChatId,
		messageId,
		notify = true,
	}: {
		chatId: string;
		fromChatId: string;
		messageId: string;
		notify?: boolean;
	}): Promise<string> {
		const url = this.apiUrl({
			methodName: 'forwardMessage',
			params: {
				chat_id: chatId,
				from_chat_id: fromChatId,
				message_id: messageId,
				disable_notification: !notify,
			},
		});
		const r = await fetch(url).then((res) => res.json());
		return JSON.stringify(r);
	}
}
