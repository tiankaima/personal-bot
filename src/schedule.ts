import { Env } from './env';
import { sendUnsentMessage, updateUnsentMessage } from './functions';

export async function scheduleJob(env: Env): Promise<Response> {
	if (Math.random() < 1 / 5) {
		await updateUnsentMessage(env);
	}

	await sendUnsentMessage(env);
	return new Response('ok');
}
