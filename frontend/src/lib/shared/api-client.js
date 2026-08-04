/** Generic fetch helpers, reused by each module's API client (e.g. diagnose/api.js). */

async function parseErrorMessage(res) {
	const text = await res.text();
	let message = text || res.statusText;
	try {
		const json = JSON.parse(text);
		if (json.detail) message = typeof json.detail === 'string' ? json.detail : JSON.stringify(json.detail);
	} catch {
		// keep raw text
	}
	return message;
}

/**
 * Build a `request(path, init)` helper scoped to a module's API base path
 * (e.g. `/api/diagnose`), with consistent JSON + error handling.
 * @param {string} basePath
 */
export function createApiClient(basePath) {
	return async function request(path, init = {}) {
		const { headers, ...rest } = init;
		/** @type {RequestInit} */
		const opts = {
			credentials: 'include',
			...rest
		};
		if (headers !== undefined) {
			opts.headers = headers;
		}
		const res = await fetch(`${basePath}${path}`, opts);
		if (!res.ok) {
			throw new Error(await parseErrorMessage(res));
		}
		if (res.status === 204) return undefined;
		return res.json();
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
