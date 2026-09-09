/** Generic fetch helpers, reused by each module's API client (e.g. diagnose/api.js). */

async function parseErrorMessage(res) {
	const text = await res.text();
	if (text.includes('error code: 1101') || text.includes('Worker threw exception')) {
		return (
			'Cloudflare Worker error (1101): POST requests to the API are blocked. ' +
			'An admin must disable or fix the Worker on beta.welllabs.org (see devops/cloudflare/README.md).'
		);
	}
	if (
		res.status === 502 ||
		res.status === 504 ||
		/bad gateway|504: gateway time-out|cloudflare/i.test(text)
	) {
		if (text.trimStart().startsWith('<!') || /cf-error-details|Bad gateway/i.test(text)) {
			return (
				`Upstream API error (${res.status}): the server timed out or crashed while ` +
				'resolving this location. Try another nearby point, or retry in a moment.'
			);
		}
	}
	let message = text || res.statusText;
	try {
		const json = JSON.parse(text);
		if (json.detail) message = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
	} catch {
		// keep raw text — but never dump full HTML pages into the UI
		if (text.trimStart().startsWith('<!')) {
			message = `Request failed (${res.status} ${res.statusText || 'error'})`;
		}
	}
	return message;
}

/**
 * Build a `request(path, init)` helper scoped to a module's API base path
 * (e.g. `/api/diagnose`), with consistent JSON + error handling.
 * @param {string} basePath
 * @param {{ retries?: number, retryDelayMs?: number }} [defaults]
 */
export function createApiClient(basePath, defaults = {}) {
	const defaultRetries = defaults.retries ?? 0;
	const defaultDelay = defaults.retryDelayMs ?? 700;

	return async function request(path, init = {}) {
		const { headers, retries = defaultRetries, retryDelayMs = defaultDelay, ...rest } = init;
		/** @type {RequestInit} */
		const opts = {
			credentials: 'include',
			...rest
		};
		if (headers !== undefined) {
			opts.headers = headers;
		}

		let lastError = null;
		const attempts = Math.max(1, Number(retries) + 1);
		for (let attempt = 0; attempt < attempts; attempt++) {
			try {
				const res = await fetch(`${basePath}${path}`, opts);
				if (!res.ok) {
					const message = await parseErrorMessage(res);
					const retryable = res.status === 502 || res.status === 503 || res.status === 504;
					if (retryable && attempt < attempts - 1 && !opts.signal?.aborted) {
						await new Promise((r) => setTimeout(r, retryDelayMs * (attempt + 1)));
						continue;
					}
					throw new Error(message);
				}
				if (res.status === 204) return undefined;
				return res.json();
			} catch (err) {
				lastError = err;
				if (err?.name === 'AbortError' || opts.signal?.aborted) throw err;
				const msg = err instanceof Error ? err.message : String(err);
				const retryable =
					/502|503|504|timed out|Bad gateway|Failed to fetch|NetworkError/i.test(msg);
				if (retryable && attempt < attempts - 1) {
					await new Promise((r) => setTimeout(r, retryDelayMs * (attempt + 1)));
					continue;
				}
				throw err;
			}
		}
		throw lastError ?? new Error('Request failed');
	};
}

/**
 * Read a Server-Sent Events response stream, dispatching `progress` / `done` /
 * `error` events to the given handlers. Used for long-running operations
 * (e.g. QField packaging/sync) that report incremental progress.
 * @param {string} url
 * @param {RequestInit} init
 * @param {{ onProgress?: (percent: number, message: string, time?: string) => void, onDone?: (result: object) => void, onError?: (message: string) => void }} handlers
 */
export async function streamSSE(url, init, handlers = {}) {
	const { onProgress, onDone, onError } = handlers;
	const res = await fetch(url, init);

	if (!res.ok) {
		throw new Error(await parseErrorMessage(res));
	}
	if (!res.body) {
		throw new Error('No response stream from server');
	}

	const reader = res.body.getReader();
	const decoder = new TextDecoder();
	let buffer = '';

	while (true) {
		const { done, value } = await reader.read();
		if (done) break;

		buffer += decoder.decode(value, { stream: true });
		const parts = buffer.split('\n\n');
		buffer = parts.pop() ?? '';

		for (const part of parts) {
			const line = part.split('\n').find((l) => l.startsWith('data: '));
			if (!line) continue;

			let event;
			try {
				event = JSON.parse(line.slice(6));
			} catch {
				continue;
			}

			if (event.type === 'progress') {
				onProgress?.(event.percent ?? 0, event.message ?? '', event.time);
			} else if (event.type === 'done') {
				onDone?.(event.result);
				return event.result;
			} else if (event.type === 'error') {
				const msg = event.message ?? 'Operation failed';
				onError?.(msg);
				throw new Error(msg);
			}
		}
	}

	throw new Error('Stream ended unexpectedly');
}
