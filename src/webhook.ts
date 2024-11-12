import { ExecutionContext } from '@cloudflare/workers-types/experimental';
import { Env } from './env';
import { handleMessageText } from './message';

export async function setWebhook(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
	// auth
	const url = new URL(request.url);
	const secret = url.searchParams.get('secret');
	if (secret !== env.ENV_BOT_SECRET) {
		return new Response('invalid secret', { status: 403 });
	}

	const res = await env.bot.setWebhook({
		webhookUrl: `https://${new URL(request.url).hostname}/webhook`,
		webhookSecret: env.ENV_BOT_SECRET,
	});
	return new Response(res, { status: res ? 200 : 500 });
}

export async function unsetWebhook(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
	// auth
	const url = new URL(request.url);
	const secret = url.searchParams.get('secret');
	if (secret !== env.ENV_BOT_SECRET) {
		return new Response('invalid secret', { status: 403 });
	}

	const res = await env.bot.setWebhook({
		webhookUrl: '',
		webhookSecret: env.ENV_BOT_SECRET,
	});
	return new Response(res, {
		status: res ? 200 : 500,
		headers: {
			'content-type': 'application/json',
		},
	});
}

export async function handleWebhook(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
	// auth. this time check headers
	const secret = request.headers.get('X-Telegram-Bot-Api-Secret-Token');
	if (secret !== env.ENV_BOT_SECRET) {
		return new Response('invalid secret', { status: 403 });
	}

	const body = await request.json();
	console.info(body);

	if ('message' in body) {
		const message = body.message;
		if ('text' in message) {
			await handleMessageText(env, message.chat.id.toString(), message.text);
			return new Response('ok');
		}
	}

	return new Response('not implemented');
}
