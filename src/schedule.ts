import { Env } from './env';
import { sendUnsentMessage, updateUnsentMessage } from './functions';

export async function scheduleJob(env: Env): Promise<Response> {
	// 100%
	if (Math.random() < 1 / 5) {
		// 20%
		await updateUnsentMessage(env);
		return new Response('ok');
	}

	// 80%
	await sendUnsentMessage(env);
	return new Response('ok');
}
