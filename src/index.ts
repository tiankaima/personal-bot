import { ExecutionContext, ScheduledController } from '@cloudflare/workers-types/experimental';
import { Env } from './env';

import { setWebhook, unsetWebhook, handleWebhook } from './webhook';
import { scheduleJob } from './schedule';

export default {
	async scheduled(controller: ScheduledController, env: Env, ctx: ExecutionContext): Promise<void> {
		await scheduleJob(env);
	},

	async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
		const path = new URL(request.url).pathname;
		if (path === '/setWebhook') {
			return setWebhook(request, env, ctx);
		}
		if (path === '/unsetWebhook') {
			return unsetWebhook(request, env, ctx);
		}
		if (path === '/webhook') {
			return handleWebhook(request, env, ctx);
		}

		return new Response('not found', { status: 404 });
	},
};
