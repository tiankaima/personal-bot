import { ExecutionContext, KVNamespace } from '@cloudflare/workers-types/experimental';
import { TelegramAPI } from './api/telegram';

export interface Env {
	DATA: KVNamespace;
	ENV_BOT_TOKEN: string;
	ENV_BOT_SECRET: string;
	ENV_BOT_ADMIN_CHAT_ID: string;

	load<T = string[]>(key: string, defaultValue: string): Promise<T>;
	save(key: string, value: any): Promise<void>;
	get bot(): TelegramAPI;
}

export function monkeyPatchEnv(env: Env) {
	if (typeof env.load === 'function' && typeof env.save === 'function') return;

	Object.defineProperties(env, {
		load: {
			value: async function <T = string[]>(key: string, defaultValue: string): Promise<T> {
				const value = await this.DATA.get(key);
				return JSON.parse(value || defaultValue);
			},
		},
		save: {
			value: async function (key: string, value: any): Promise<void> {
				await this.DATA.put(key, JSON.stringify(value));
			},
		},
		bot: {
			get: function () {
				return new TelegramAPI(this.ENV_BOT_TOKEN);
			},
		},
	});
}
