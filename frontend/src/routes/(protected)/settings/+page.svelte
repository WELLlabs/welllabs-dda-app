<script>
	import { goto } from '$app/navigation';
	import { deleteMe, forgotPassword, updateMe } from '$lib/modules/accounts/api.js';
	import { session } from '$lib/shared/session.svelte.js';
	import { appPath } from '$lib/shared/paths.js';

	let name = $state(session.user?.name ?? '');
	let nameBusy = $state(false);
	let nameMsg = $state('');
	let nameErr = $state('');

	let passwordBusy = $state(false);
	let passwordMsg = $state('');
	let passwordErr = $state('');

	let newPassword = $state('');
	let confirmPassword = $state('');
	let changePwBusy = $state(false);
	let changePwMsg = $state('');
	let changePwErr = $state('');

	let dangerBusy = $state(false);
	let dangerErr = $state('');

	$effect(() => {
		if (session.user?.name && !nameBusy) {
			name = session.user.name;
		}
	});

	async function saveName(e) {
		e.preventDefault();
		const next = name.trim();
		if (!next || next === session.user?.name) return;
		nameBusy = true;
		nameMsg = '';
		nameErr = '';
		try {
			const user = await updateMe({ name: next });
			session.setUser(user);
			nameMsg = 'Profile name updated.';
		} catch (err) {
			nameErr = String(err.message ?? err);
		} finally {
			nameBusy = false;
		}
	}

	async function sendResetEmail() {
		passwordBusy = true;
		passwordMsg = '';
		passwordErr = '';
		try {
			await forgotPassword(session.user.email);
			passwordMsg = 'Password reset email sent — check your inbox.';
		} catch (err) {
			passwordErr = String(err.message ?? err);
		} finally {
			passwordBusy = false;
		}
	}

	async function changePassword(e) {
		e.preventDefault();
		changePwMsg = '';
		changePwErr = '';
		if (newPassword.length < 8) {
			changePwErr = 'Password must be at least 8 characters.';
			return;
		}
		if (newPassword !== confirmPassword) {
			changePwErr = 'Passwords do not match.';
			return;
		}
		changePwBusy = true;
		try {
			const user = await updateMe({ password: newPassword });
			session.setUser(user);
			newPassword = '';
			confirmPassword = '';
			changePwMsg = 'Password updated.';
		} catch (err) {
			changePwErr = String(err.message ?? err);
		} finally {
			changePwBusy = false;
		}
	}

	async function deactivateAccount() {
		if (
			!confirm(
				'Deactivate your account? You will be signed out and will not be able to sign in until an administrator reactivates it.'
			)
		) {
			return;
		}
		dangerBusy = true;
		dangerErr = '';
		try {
			await updateMe({ is_active: false });
			await session.logout();
			goto(appPath('/'));
		} catch (err) {
			dangerErr = String(err.message ?? err);
			dangerBusy = false;
		}
	}

	async function deleteAccount() {
		const typed = prompt('Type DELETE to permanently remove your account. This cannot be undone.');
		if (typed !== 'DELETE') return;
		dangerBusy = true;
		dangerErr = '';
		try {
			await deleteMe();
			session.setUser(null);
			goto(appPath('/'));
		} catch (err) {
			dangerErr = String(err.message ?? err);
			dangerBusy = false;
		}
	}
</script>

<svelte:head>
	<title>Account · Settings</title>
</svelte:head>

<div class="mx-auto flex max-w-2xl flex-col gap-6">
	<div>
		<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">Account</h2>
		<p class="m-0 mt-1 text-sm text-brand-steel">Manage your profile and sign-in options.</p>
	</div>

	{#if session.user}
		<section class="rounded-2xl border border-brand-navy/10 bg-white p-5 shadow-sm">
			<div class="mb-4 flex items-center gap-4">
				<div
					class="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-brand-navy text-lg font-semibold text-white"
				>
					{(session.user.name ?? '?').charAt(0).toUpperCase()}
				</div>
				<div>
					<p class="m-0 font-body text-base font-medium text-brand-navy">{session.user.name}</p>
					<p class="m-0 mt-1 text-sm text-brand-steel">{session.user.email}</p>
				</div>
			</div>

			<form onsubmit={saveName} class="flex flex-col gap-3 border-t border-brand-navy/8 pt-4">
				<label class="font-mono text-[11px] uppercase tracking-wide text-brand-steel" for="profile-name">
					Profile name
				</label>
				<div class="flex flex-col gap-2 sm:flex-row">
					<input
						id="profile-name"
						type="text"
						required
						maxlength="200"
						class="w-full rounded-lg border border-brand-navy/15 bg-white px-3 py-2 text-sm text-brand-navy outline-none focus:border-brand-blue"
						bind:value={name}
					/>
					<button
						type="submit"
						class="cursor-pointer rounded-lg bg-brand-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
						disabled={nameBusy || !name.trim() || name.trim() === session.user.name}
					>
						{nameBusy ? 'Saving…' : 'Save name'}
					</button>
				</div>
				{#if nameMsg}<p class="m-0 text-sm text-brand-forest">{nameMsg}</p>{/if}
				{#if nameErr}<p class="m-0 text-sm text-red-600">{nameErr}</p>{/if}
			</form>
		</section>

		<section class="rounded-2xl border border-brand-navy/10 bg-white p-5 shadow-sm">
			<h3 class="m-0 font-headline text-base font-semibold text-brand-navy">Change password</h3>
			<p class="m-0 mt-1 text-sm text-brand-steel">
				Set a new password here, or email yourself a reset link.
			</p>

			<form onsubmit={changePassword} class="mt-4 flex flex-col gap-3">
				<div>
					<label class="mb-1 block font-mono text-[11px] uppercase tracking-wide text-brand-steel" for="new-password"
						>New password</label
					>
					<input
						id="new-password"
						type="password"
						minlength="8"
						autocomplete="new-password"
						class="w-full rounded-lg border border-brand-navy/15 bg-white px-3 py-2 text-sm outline-none focus:border-brand-blue"
						bind:value={newPassword}
					/>
				</div>
				<div>
					<label
						class="mb-1 block font-mono text-[11px] uppercase tracking-wide text-brand-steel"
						for="confirm-password">Confirm password</label
					>
					<input
						id="confirm-password"
						type="password"
						minlength="8"
						autocomplete="new-password"
						class="w-full rounded-lg border border-brand-navy/15 bg-white px-3 py-2 text-sm outline-none focus:border-brand-blue"
						bind:value={confirmPassword}
					/>
				</div>
				<button
					type="submit"
					class="w-fit cursor-pointer rounded-lg bg-brand-blue px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
					disabled={changePwBusy || !newPassword || !confirmPassword}
				>
					{changePwBusy ? 'Updating…' : 'Update password'}
				</button>
				{#if changePwMsg}<p class="m-0 text-sm text-brand-forest">{changePwMsg}</p>{/if}
				{#if changePwErr}<p class="m-0 text-sm text-red-600">{changePwErr}</p>{/if}
			</form>

			<div class="mt-5 border-t border-brand-navy/8 pt-4">
				<button
					type="button"
					class="cursor-pointer rounded-lg border border-brand-navy/15 bg-white px-4 py-2 text-sm text-brand-navy hover:bg-brand-sky/10 disabled:opacity-50"
					onclick={sendResetEmail}
					disabled={passwordBusy}
				>
					{passwordBusy ? 'Sending…' : 'Email me a reset link'}
				</button>
				{#if passwordMsg}<p class="m-0 mt-2 text-sm text-brand-forest">{passwordMsg}</p>{/if}
				{#if passwordErr}<p class="m-0 mt-2 text-sm text-red-600">{passwordErr}</p>{/if}
			</div>
		</section>

		<section class="rounded-2xl border border-red-200 bg-white p-5 shadow-sm">
			<h3 class="m-0 font-headline text-base font-semibold text-red-700">Danger zone</h3>
			<p class="m-0 mt-1 text-sm text-brand-steel">
				Deactivating disables sign-in. Deleting permanently removes your account.
			</p>
			<div class="mt-4 flex flex-wrap gap-2">
				<button
					type="button"
					class="cursor-pointer rounded-lg border border-red-200 bg-white px-4 py-2 text-sm text-red-700 hover:bg-red-50 disabled:opacity-50"
					onclick={deactivateAccount}
					disabled={dangerBusy}
				>
					Deactivate account
				</button>
				<button
					type="button"
					class="cursor-pointer rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
					onclick={deleteAccount}
					disabled={dangerBusy}
				>
					Delete account
				</button>
			</div>
			{#if dangerErr}<p class="m-0 mt-2 text-sm text-red-600">{dangerErr}</p>{/if}
		</section>
	{/if}
</div>
