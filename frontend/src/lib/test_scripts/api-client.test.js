import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApiClient, streamSSE } from '../shared/api-client.js';

describe('createApiClient', () => {
	beforeEach(() => {
		vi.stubGlobal('fetch', vi.fn());
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	it('GETs JSON from the scoped base path', async () => {
		fetch.mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => ({ id: 'p1' })
		});

		const request = createApiClient('/api/diagnose');
		const data = await request('/projects');

		expect(fetch).toHaveBeenCalledWith('/api/diagnose/projects', { credentials: 'include' });
		expect(data).toEqual({ id: 'p1' });
	});

	it('forwards init options (method, headers, body)', async () => {
		fetch.mockResolvedValue({
			ok: true,
			status: 200,
			json: async () => ({ ok: true })
		});

		const request = createApiClient('/api/accounts');
		await request('/auth/login', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com', password: 'x' })
		});

		expect(fetch).toHaveBeenCalledWith('/api/accounts/auth/login', {
			credentials: 'include',
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ email: 'a@b.com', password: 'x' })
		});
	});

	it('returns undefined for 204 responses', async () => {
		fetch.mockResolvedValue({
			ok: true,
			status: 204,
			json: async () => {
				throw new Error('should not parse body');
			}
		});

		const request = createApiClient('/api/diagnose');
		await expect(request('/projects/1', { credentials: 'include', method: 'DELETE' })).resolves.toBeUndefined();
	});

	it('throws with detail string from JSON error body', async () => {
		fetch.mockResolvedValue({
			ok: false,
			status: 400,
			statusText: 'Bad Request',
			text: async () => JSON.stringify({ detail: 'Name required' })
		});

		const request = createApiClient('/api/diagnose');
		await expect(request('/projects', { method: 'POST' })).rejects.toThrow('Name required');
	});

	it('throws stringified detail when detail is an object/array', async () => {
		fetch.mockResolvedValue({
			ok: false,
			status: 422,
			statusText: 'Unprocessable',
			text: async () => JSON.stringify({ detail: [{ msg: 'invalid' }] })
		});

		const request = createApiClient('/api/diagnose');
		await expect(request('/projects')).rejects.toThrow('[{"msg":"invalid"}]');
	});

	it('falls back to raw text when error body is not JSON', async () => {
		fetch.mockResolvedValue({
			ok: false,
			status: 500,
			statusText: 'Internal Server Error',
			text: async () => 'upstream failed'
		});

		const request = createApiClient('/api/diagnose');
		await expect(request('/projects')).rejects.toThrow('upstream failed');
	});
});

describe('streamSSE', () => {
	afterEach(() => {
		vi.unstubAllGlobals();
		vi.restoreAllMocks();
	});

	function mockStream(chunks) {
		const encoder = new TextEncoder();
		let i = 0;
		return {
			ok: true,
			body: {
				getReader() {
					return {
						async read() {
							if (i >= chunks.length) return { done: true, value: undefined };
							const value = encoder.encode(chunks[i++]);
							return { done: false, value };
						}
					};
				}
			}
		};
	}

	it('dispatches progress and done events', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(
				mockStream([
					'data: {"type":"progress","percent":40,"message":"Packaging"}\n\n',
					'data: {"type":"done","result":{"package_id":"pkg-1"}}\n\n'
				])
			)
		);

		const onProgress = vi.fn();
		const onDone = vi.fn();
		const result = await streamSSE('/api/diagnose/package', { method: 'POST' }, { onProgress, onDone });

		expect(onProgress).toHaveBeenCalledWith(40, 'Packaging', undefined);
		expect(onDone).toHaveBeenCalledWith({ package_id: 'pkg-1' });
		expect(result).toEqual({ package_id: 'pkg-1' });
	});

	it('throws on error events and calls onError', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(mockStream(['data: {"type":"error","message":"Sync failed"}\n\n']))
		);

		const onError = vi.fn();
		await expect(streamSSE('/api/diagnose/sync', {}, { onError })).rejects.toThrow('Sync failed');
		expect(onError).toHaveBeenCalledWith('Sync failed');
	});

	it('throws when response is not ok', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: false,
			status: 503,
			statusText: 'Unavailable',
			text: async () => JSON.stringify({ detail: 'Busy' }),
			body: null
		}));

		await expect(streamSSE('/api/diagnose/sync', {})).rejects.toThrow('Busy');
	});

	it('throws when response has no body stream', async () => {
		vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
			ok: true,
			body: null
		}));

		await expect(streamSSE('/api/diagnose/sync', {})).rejects.toThrow('No response stream from server');
	});

	it('throws when stream ends without a done event', async () => {
		vi.stubGlobal(
			'fetch',
			vi.fn().mockResolvedValue(mockStream(['data: {"type":"progress","percent":10,"message":"Start"}\n\n']))
		);

		await expect(streamSSE('/api/diagnose/sync', {})).rejects.toThrow('Stream ended unexpectedly');
	});
});
