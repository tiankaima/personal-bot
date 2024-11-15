export const fetchTweetIds = async ({ userName, cookies }: { userName: string; cookies: string }): Promise<string[]> => {
	const raw_headers = `
Host: syndication.twitter.com
User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0
Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8
Accept-Language: zh-CN,zh;q=0.8,zh-TW;q=0.7,zh-HK;q=0.5,en-US;q=0.3,en;q=0.2
Accept-Encoding: gzip, deflate, br, zstd
DNT: 1
Sec-GPC: 1
Connection: keep-alive
Cookie: ${cookies}
Upgrade-Insecure-Requests: 1
Sec-Fetch-Dest: document
Sec-Fetch-Mode: navigate
Sec-Fetch-Site: cross-site
Priority: u=0, i
Pragma: no-cache
Cache-Control: no-cache
`;

	const headers = raw_headers.split('\n').reduce((acc, line) => {
		const [key, value] = line.split(': ');
		if (key && value) {
			acc[key] = value;
		}
		return acc;
	}, {} as Record<string, string>);

	const text = await fetch(`https://syndication.twitter.com/srv/timeline-profile/screen-name/${userName}`, {
		headers: new Headers(headers),
	}).then((res) => {
		return res.text();
	});

	console.log(`Fetching ${userName} tweets`);

	// fuck the parsing logic, let's regex it
	const tweetIds = text.match(/tweet-(\d{19})/g)?.map((match) => match.replace('tweet-', ''));
	if (!tweetIds) {
		console.info(`userName = ${userName} links not found`);
		return [];
	}
	return tweetIds;
};

export const fetchTweetDetail = async (url: string): Promise<JSON> => {
	const fxUrl = url.replace('https://twitter.com/', 'https://api.fxtwitter.com/');
	const r = await fetch(fxUrl, {
		headers: new Headers({
			'User-Agent': 'tiankaima-bot/1.0 (t.me/tiankaima)',
		}),
	}).then((res) => res.json());

	console.info(r);

	if (r['message'] !== 'OK') {
		console.error(r);
	}
	return r['tweet'];
};

export * as TwitterAPI from './twitter';
