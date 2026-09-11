/**
 * Cross-route navigation lock for Diagnose.
 *
 * Survives ProjectPicker unmount → project page mount so rapid open/back/open
 * cannot stack prewarm + batch analysis requests (Cloudflare 502s).
 */

/** @type {{ projectId: string | null, mode: 'idle' | 'creating' | 'opening' | 'booting' | 'leaving' }} */
let state = { projectId: null, mode: 'idle' };

/** @type {Set<() => void>} */
const listeners = new Set();

function notify() {
	for (const fn of listeners) {
		try {
			fn();
		} catch {
			/* ignore */
		}
	}
}

export function getDiagnoseNavLock() {
	return { ...state };
}

export function isDiagnoseNavBusy() {
	return state.mode !== 'idle';
}

/**
 * @param {'creating' | 'opening' | 'booting' | 'leaving'} mode
 * @param {string | null} [projectId]
 * @returns {boolean} false if another navigation is already in progress
 */
export function beginDiagnoseNav(mode, projectId = null) {
	// Block new opens while leave/abort is draining.
	if (state.mode === 'leaving') return false;
	if (state.mode === 'idle') {
		state = { projectId, mode };
		notify();
		return true;
	}
	// Same project handoff: creating → opening → booting (picker → map).
	if (projectId && state.projectId && projectId !== state.projectId) {
		return false;
	}
	const order = { creating: 1, opening: 2, booting: 3, leaving: 4, idle: 0 };
	const from = order[state.mode] ?? 0;
	const to = order[mode] ?? 0;
	if (to >= from) {
		state = { projectId: projectId ?? state.projectId, mode };
		notify();
		return true;
	}
	return false;
}

export function clearDiagnoseNav(projectId = null) {
	if (projectId && state.projectId && projectId !== state.projectId) return;
	state = { projectId: null, mode: 'idle' };
	notify();
}

/** Mark leave-in-progress so remounted picker won't open another project yet. */
export function beginDiagnoseLeave() {
	state = { projectId: state.projectId, mode: 'leaving' };
	notify();
}

/**
 * Subscribe to lock changes. Returns unsubscribe.
 * @param {() => void} fn
 */
export function subscribeDiagnoseNav(fn) {
	listeners.add(fn);
	return () => listeners.delete(fn);
}
