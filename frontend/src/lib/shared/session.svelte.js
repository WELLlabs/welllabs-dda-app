/** Reactive current-user session store, backed by the HttpOnly session cookie. */

import { me as fetchMe, logout as apiLogout } from '$lib/modules/accounts/api.js';

let user = $state(null);
let loading = $state(true);
let loaded = $state(false);

async function loadSession() {
	loading = true;
	try {
		user = await fetchMe();
	} catch {
		user = null;
	} finally {
		loading = false;
		loaded = true;
	}
}

function setUser(next) {
	user = next;
	loaded = true;
	loading = false;
}

async function logout() {
	try {
		await apiLogout();
	} finally {
		user = null;
	}
}

export const session = {
	get user() {
		return user;
	},
	get loading() {
		return loading;
	},
	get loaded() {
		return loaded;
	},
	loadSession,
	setUser,
	logout
};
