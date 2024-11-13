import { Env } from './env';
import { sendUnsentMessage, updateUnsentMessage } from './functions';

export async function scheduleJob(env: Env): Promise<Response> {
	let unsent_links = await env.load('unsent_links');

	if (unsent_links.length > 0) {
		// 80%
		await sendUnsentMessage(env);
		return new Response('ok');
	}

	await updateUnsentMessage(env);
	return new Response('ok');
}
