import { ExecutionContext, KVNamespace, ScheduledController } from '@cloudflare/workers-types/experimental';
import { TelegramAPI } from './api/telegram';

export class Env {
	DATA: KVNamespace;
	ENV_BOT_TOKEN: string;
	ENV_BOT_SECRET: string;
	ENV_BOT_ADMIN_CHAT_ID: string;

	async load<T = string[]>(key: string, defaultValue: string = '[]'): Promise<T> {
		const value = await this.DATA.get(key);
		return JSON.parse(value || defaultValue);
	}

	async save(key: string, value: any): Promise<void> {
		await this.DATA.put(key, JSON.stringify(value));
	}

	get bot(): TelegramAPI {
		return new TelegramAPI(this.ENV_BOT_TOKEN);
	}
}
