const randomOneOf = (arr: any[]) => arr[Math.floor(Math.random() * arr.length)];

declare global {
	interface Array<T> {
		sample(): T | undefined;
		samples(count: number): T[];
	}
}

Array.prototype.sample = function <T>(): T | undefined {
	if (this.length === 0) return undefined;
	const index = Math.floor(Math.random() * this.length);
	return this[index];
};

Array.prototype.samples = function <T>(count: number): T[] {
	if (this.length === 0) return [];
	if (count >= this.length) return this;
	const indexes = new Set<number>();
	while (indexes.size < count) {
		indexes.add(Math.floor(Math.random() * this.length));
	}
	return Array.from(indexes).map((index) => this[index]);
};

export {};
