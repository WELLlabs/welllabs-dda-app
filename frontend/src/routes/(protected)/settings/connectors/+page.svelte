<script>
	import { onMount } from 'svelte';
	import {
		connectQFieldAccount,
		disconnectQFieldAccount,
		getQFieldStatus
	} from '$lib/modules/accounts/api.js';

	let qfStatus = $state({ connected: false });
	let qfLoading = $state(true);
	let qfError = $state('');
	let qfShowForm = $state(false);
	let qfUsername = $state('');
	let qfPassword = $state('');
	let qfBusy = $state(false);

	onMount(async () => {
		await loadQFieldStatus();
	});

	async function loadQFieldStatus() {
		qfLoading = true;
		qfError = '';
		try {
			qfStatus = await getQFieldStatus();
		} catch (err) {
			qfError = String(err.message ?? err);
		} finally {
			qfLoading = false;
		}
	}

	async function handleConnect(e) {
		e.preventDefault();
		if (!qfUsername.trim() || !qfPassword) return;
		qfBusy = true;
		qfError = '';
		try {
			await connectQFieldAccount(qfUsername.trim(), qfPassword);
			qfUsername = '';
			qfPassword = '';
			qfShowForm = false;
			await loadQFieldStatus();
		} catch (err) {
			qfError = String(err.message ?? err);
		} finally {
			qfBusy = false;
		}
	}

	async function handleDisconnect() {
		if (!confirm('Disconnect your QField Cloud account?')) return;
		qfBusy = true;
		qfError = '';
		try {
			await disconnectQFieldAccount();
			qfStatus = { connected: false };
		} catch (err) {
			qfError = String(err.message ?? err);
		} finally {
			qfBusy = false;
		}
	}

	function isExpired(expiresAt) {
		if (!expiresAt) return false;
		return new Date(expiresAt) < new Date();
	}
</script>

<svelte:head>
	<title>Connectors · Settings</title>
</svelte:head>

<div class="max-w-2xl space-y-5">
	<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">Connectors</h2>

	<section class="rounded-2xl border border-brand-navy/10 bg-white shadow-sm">
		<div class="border-b border-brand-navy/8 px-5 py-4">
			<h3 class="m-0 font-headline text-sm font-semibold tracking-wide text-brand-navy/60 uppercase">
				QField Cloud
			</h3>
		</div>

		<div class="px-5 py-4">
			{#if qfLoading}
				<p class="m-0 text-sm text-brand-steel">Checking connection…</p>
			{:else if qfStatus.connected && !qfShowForm}
				<div class="flex items-center justify-between gap-3">
					<div>
						<p class="m-0 font-body text-sm font-medium text-brand-navy">
							Connected as <span class="font-semibold">{qfStatus.qfield_username}</span>
						</p>
						{#if qfStatus.expires_at}
							{#if isExpired(qfStatus.expires_at)}
								<p class="m-0 mt-1 text-xs text-red-600">
									Token expired — reconnect to continue using QField Cloud.
								</p>
							{:else}
								<p class="m-0 mt-1 text-xs text-brand-steel">
									Expires {new Date(qfStatus.expires_at).toLocaleDateString()}
								</p>
							{/if}
						{/if}
					</div>
					<div class="flex gap-2">
						{#if isExpired(qfStatus.expires_at)}
							<button
								type="button"
								class="cursor-pointer rounded-lg bg-brand-blue px-3 py-1.5 font-body text-sm font-medium text-white hover:bg-brand-deep"
								onclick={() => (qfShowForm = true)}
							>
								Reconnect
							</button>
						{/if}
						<button
							type="button"
							class="cursor-pointer rounded-lg border border-red-300 bg-white px-3 py-1.5 font-body text-sm text-red-600 hover:bg-red-50 disabled:opacity-60"
							disabled={qfBusy}
							onclick={handleDisconnect}
						>
							Disconnect
						</button>
					</div>
				</div>
			{:else}
				{#if !qfShowForm && !qfStatus.connected}
					<p class="m-0 mb-3 text-sm text-brand-steel">
						Connect your QField Cloud account to package and sync diagnoses from the field.
					</p>
					<button
						type="button"
						class="cursor-pointer rounded-lg bg-brand-blue px-3 py-1.5 font-body text-sm font-medium text-white hover:bg-brand-deep"
						onclick={() => (qfShowForm = true)}
					>
						Connect QField Account
					</button>
				{/if}

				{#if qfShowForm}
					<form onsubmit={handleConnect} class="flex flex-col gap-3 rounded-lg bg-brand-sky/10 p-4">
						<p class="m-0 text-sm text-brand-steel">
							Enter your <a href="https://app.qfield.cloud" target="_blank" rel="noopener" class="text-brand-blue underline">QField Cloud</a> credentials.
						</p>
						<input
							type="text"
							required
							placeholder="QField username or email"
							autocomplete="username"
							class="rounded-lg border border-brand-navy/15 px-3 py-2 font-body text-sm outline-none focus:border-brand-blue"
							bind:value={qfUsername}
						/>
						<input
							type="password"
							required
							placeholder="Password"
							autocomplete="current-password"
							class="rounded-lg border border-brand-navy/15 px-3 py-2 font-body text-sm outline-none focus:border-brand-blue"
							bind:value={qfPassword}
						/>
						<div class="flex gap-2">
							<button
								type="submit"
								class="cursor-pointer rounded-lg bg-brand-blue px-4 py-2 font-body text-sm font-medium text-white disabled:opacity-60"
								disabled={qfBusy || !qfUsername.trim() || !qfPassword}
							>
								{qfBusy ? 'Connecting…' : 'Connect'}
							</button>
							<button
								type="button"
								class="cursor-pointer rounded-lg border border-brand-navy/15 bg-white px-3 py-2 font-body text-sm text-brand-navy"
								onclick={() => {
									qfShowForm = false;
									qfError = '';
								}}
							>
								Cancel
							</button>
						</div>
					</form>
				{/if}
			{/if}

			{#if qfError}
				<p class="m-0 mt-3 text-sm text-red-600">{qfError}</p>
			{/if}
		</div>
	</section>
</div>
