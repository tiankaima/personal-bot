import { ExecutionContext, KVNamespace, ScheduledController } from '@cloudflare/workers-types/experimental';

export interface Env {
	DATA: KVNamespace;
	ENV_BOT_TOKEN: string;
	ENV_BOT_SECRET: string;
	ENV_BOT_ADMIN_CHAT_ID: string;
}
