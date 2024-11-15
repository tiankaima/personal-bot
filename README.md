# Personal Bot

> [!NOTE]
>
> This is more of a PoC project, a code review & revise is suggested before using it in production.

A simple Telegram bot hosted on Cloudflare Workers, which can perform:

- Cron job fetching posts from Twitter, if new posts with images are found, it will send them to user
- ...

GitHub Actions is used for CI/CD, meaning that the bot will be automatically deployed to Cloudflare Workers when new commits are pushed to the `main` branch.

## Deployment

> [!WARNING]
>
> Hide any sensitive information before pushing to GitHub / asking for help.

To host you own version of this bot, you need to:

1. Register a new bot on Telegram and get the API token (contact [BotFather](https://t.me/botfather) on Telegram)
2. A Cloudflare account with Workers enabled

You'll also need to create a KV namespace in Cloudflare Workers, follow CF Guide [here](https://developers.cloudflare.com/kv/get-started/):

```sh
npx wrangler kv namespace create "DATA"
```

and change `wrangler.toml` to your own:

```toml
[[kv_namespaces]]
binding = "DATA"
id = "c687973e88a54653908e2d016fb6ac8a"
```

Then set envs/secrets, follow these steps:

1. Set `CLOUDFLARE_API_TOKEN`

    Follow CF Guide [here](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/), you'll need `Workers KV Storage:Edit, Workers Scripts:Edit` permissions.

    This env is only used for CI/CD, so you can set it in GitHub Secrets.

    > You may now create a first deployment, but currently no connection to telegram is established, so the bot won't work.

2. Set `ENV_BOT_TOKEN`

    The API token you got from BotFather.

    This would be used both in debugging & production runtime, first create a `.dev.vars` file in the root of the project:

    ```sh
    echo "
    ENV_BOT_TOKEN=YOUR_BOT_TOKEN
    " > .dev.vars
    ```

    `.dev.vars` are ignored by git for safety, but you'll still need to set them to CF worker for them to be available in production runtime:

    ```sh
    npx wrangler secret put ENV_BOT_TOKEN
    ```

3. Set `ENV_BOT_SECRET`

    This is to prevent `/webhook` endpoint from unauthorized access other than telegram, first generate a random string:

    ```sh
    openssl rand -base64 32
    ```

    Then set it in `.dev.vars`:

    ```sh
    echo "
    ENV_BOT_SECRET=YOUR_SECRET
    " >> .dev.vars
    ```

    like `ENV_BOT_TOKEN`, set it to CF worker:

    ```sh
    npx wrangler secret put ENV_BOT_SECRET
    ```

    Note an extra step is required for the worker to bind telegram webhook to itself, you'll need to manually call `/setWebhook` endpoint just once after deployment:

    ```sh
    curl -D - "https://your-worker-name.your-username.workers.dev/setWebhook?secret=YOUR_SECRET"
    ```

4. set `ENV_BOT_ADMIN_CHAT_ID`

    First open Worker Logs in CF dashboard, then send a message to your bot, you'll see the chat id in the logs.

    Set it in `.dev.vars`:

    ```sh
    echo "
    ENV_BOT_ADMIN_CHAT_ID=YOUR_CHAT_ID
    " >> .dev.vars
    ```

    like `ENV_BOT_TOKEN`, set it to

    ```sh
    npx wrangler secret put ENV_BOT_ADMIN_CHAT_ID
    ```

## Twitter features

For convenience, these variables are stored in KV storage other than env variables/secrets to allow fast rotation/update:

- `twitter_cookies`
- `twitter_users`

To update them, you can send `/set` commands to the bot, for example:

```txt
/set twitter_cookies YOUR_COOKIES
```

## Development

Unlike other bot runtimes, this webhook method to receive updates from telegram is more like a serverless function, so debugging locally might not be as straightforward.

However with the framework set up properly, you'll easily write code w/o much errors, just `git commit --amend` and `git push -f` and wait for CI/CD to publish edits.

> [!NOTE]
>
> CF Worker KV have a limit of 1000 writes per day on a free plan, lower cron job frequency in `wrangler.toml` if you're close to the limit.