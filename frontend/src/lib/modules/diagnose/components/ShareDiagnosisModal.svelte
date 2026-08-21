<script>
	import { onMount } from 'svelte';
	import {
		addOrgAccess,
		addUserAccess,
		fetchOrgAccess,
		fetchUserAccess,
		removeOrgAccess,
		removeUserAccess
	} from '$lib/modules/diagnose/api';
	import { fetchOrgs, lookupUserByEmail } from '$lib/modules/accounts/api.js';

	/** @type {{ project: object, onClose: () => void }} */
	let { project, onClose } = $props();

	let loading = $state(true);
	let error = $state('');

	let sharedUsers = $state([]);
	let sharedOrgs = $state([]);
	let myOrgs = $state([]);

	let emailInput = $state('');
	let lookupResult = $state(null);
	let lookupError = $state('');
	let lookingUp = $state(false);
	let addingUser = $state(false);

	let selectedOrgId = $state('');
	let addingOrg = $state(false);
	let orgError = $state('');

	onMount(loadAll);

	async function loadAll() {
		loading = true;
		error = '';
		try {
			const [users, orgs, mine] = await Promise.all([
				fetchUserAccess(project.id),
				fetchOrgAccess(project.id),
				fetchOrgs()
			]);
			sharedUsers = users;
			sharedOrgs = orgs;
			myOrgs = mine;
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			loading = false;
		}
	}

	const availableOrgs = $derived(
		myOrgs.filter((org) => !sharedOrgs.some((shared) => shared.id === org.id))
	);

	async function handleLookup() {
		const email = emailInput.trim();
		if (!email) return;
		lookingUp = true;
		lookupError = '';
		lookupResult = null;
		try {
			lookupResult = await lookupUserByEmail(email);
		} catch (err) {
			lookupError = String(err.message ?? err);
		} finally {
			lookingUp = false;
		}
	}

	async function handleAddUser() {
		if (!lookupResult) return;
		addingUser = true;
		try {
			await addUserAccess(project.id, lookupResult.email);
			sharedUsers = await fetchUserAccess(project.id);
			emailInput = '';
			lookupResult = null;
		} catch (err) {
			lookupError = String(err.message ?? err);
		} finally {
			addingUser = false;
		}
	}

	async function handleRemoveUser(user) {
		if (!confirm(`Remove ${user.name} from this project?`)) return;
		try {
			await removeUserAccess(project.id, user.id);
			sharedUsers = sharedUsers.filter((u) => u.id !== user.id);
		} catch (err) {
			error = String(err.message ?? err);
		}
	}

	async function handleAddOrg() {
		if (!selectedOrgId) return;
		addingOrg = true;
		orgError = '';
		try {
			await addOrgAccess(project.id, selectedOrgId);
			sharedOrgs = await fetchOrgAccess(project.id);
			selectedOrgId = '';
		} catch (err) {
			orgError = String(err.message ?? err);
		} finally {
			addingOrg = false;
		}
	}

	async function handleRemoveOrg(org) {
		if (!confirm(`Remove "${org.name}" from this project?`)) return;
		try {
			await removeOrgAccess(project.id, org.id);
			sharedOrgs = sharedOrgs.filter((o) => o.id !== org.id);
		} catch (err) {
			error = String(err.message ?? err);
		}
	}
</script>

<div
	class="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
	role="presentation"
	onclick={(e) => {
		if (e.target === e.currentTarget) onClose();
	}}
>
	<div class="w-full max-w-lg rounded-2xl bg-white p-6 shadow-xl">
		<div class="mb-4 flex items-start justify-between gap-3">
			<div>
				<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">Share project</h2>
				<p class="m-0 mt-1 text-sm text-brand-steel">{project.name}</p>
			</div>
			<button
				type="button"
				class="cursor-pointer rounded border-0 bg-transparent p-1 text-brand-steel hover:text-brand-navy"
				aria-label="Close"
				onclick={onClose}
			>
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="h-5 w-5">
					<path
						fill-rule="evenodd"
						d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
						clip-rule="evenodd"
					/>
				</svg>
			</button>
		</div>

		{#if error}
			<p class="m-0 mb-3 text-sm text-red-600">{error}</p>
		{/if}

		{#if loading}
			<p class="m-0 text-sm text-brand-steel">Loading…</p>
		{:else}
			<section class="mb-5">
				<h3 class="m-0 mb-2 font-body text-sm font-semibold text-brand-navy">People</h3>

				{#if sharedUsers.length > 0}
					<ul class="m-0 mb-3 flex flex-col gap-1.5 p-0">
						{#each sharedUsers as user (user.id)}
							<li class="flex items-center justify-between gap-2 text-sm">
								<span class="min-w-0 truncate text-brand-navy"
									>{user.name} <span class="text-brand-steel">· {user.email}</span></span
								>
								<button
									type="button"
									class="shrink-0 cursor-pointer rounded border-0 bg-transparent px-1.5 py-0.5 text-xs text-red-600 hover:bg-red-50"
									onclick={() => handleRemoveUser(user)}
								>
									Remove
								</button>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="m-0 mb-3 text-sm text-brand-steel">No one else has access yet.</p>
				{/if}

				<div class="flex gap-2">
					<input
						type="email"
						placeholder="Add by email"
						class="flex-1 rounded border border-brand-navy/20 px-2 py-1.5 font-body text-sm"
						bind:value={emailInput}
						onkeydown={(e) => {
							if (e.key === 'Enter') {
								e.preventDefault();
								handleLookup();
							}
						}}
					/>
					<button
						type="button"
						class="cursor-pointer rounded bg-brand-blue px-3 py-1.5 font-body text-sm text-white disabled:opacity-60"
						disabled={lookingUp || !emailInput.trim()}
						onclick={handleLookup}
					>
						{lookingUp ? 'Looking up…' : 'Look up'}
					</button>
				</div>

				{#if lookupError}
					<p class="m-0 mt-2 text-xs text-red-600">{lookupError}</p>
				{:else if lookupResult}
					<div class="mt-2 flex items-center justify-between gap-2 rounded-lg bg-brand-sky/15 px-3 py-2">
						<span class="text-sm text-brand-navy">{lookupResult.name} · {lookupResult.email}</span>
						<button
							type="button"
							class="cursor-pointer rounded bg-brand-blue px-2.5 py-1 font-body text-xs text-white disabled:opacity-60"
							disabled={addingUser}
							onclick={handleAddUser}
						>
							{addingUser ? 'Adding…' : 'Add'}
						</button>
					</div>
				{/if}
			</section>

			<section>
				<h3 class="m-0 mb-2 font-body text-sm font-semibold text-brand-navy">Organizations</h3>

				{#if sharedOrgs.length > 0}
					<ul class="m-0 mb-3 flex flex-col gap-1.5 p-0">
						{#each sharedOrgs as org (org.id)}
							<li class="flex items-center justify-between gap-2 text-sm">
								<span class="min-w-0 truncate text-brand-navy">{org.name}</span>
								<button
									type="button"
									class="shrink-0 cursor-pointer rounded border-0 bg-transparent px-1.5 py-0.5 text-xs text-red-600 hover:bg-red-50"
									onclick={() => handleRemoveOrg(org)}
								>
									Remove
								</button>
							</li>
						{/each}
					</ul>
				{:else}
					<p class="m-0 mb-3 text-sm text-brand-steel">No organizations have access yet.</p>
				{/if}

				{#if availableOrgs.length > 0}
					<div class="flex gap-2">
						<select
							class="flex-1 rounded border border-brand-navy/20 px-2 py-1.5 font-body text-sm"
							bind:value={selectedOrgId}
						>
							<option value="">Select an organization…</option>
							{#each availableOrgs as org (org.id)}
								<option value={org.id}>{org.name}</option>
							{/each}
						</select>
						<button
							type="button"
							class="cursor-pointer rounded bg-brand-blue px-3 py-1.5 font-body text-sm text-white disabled:opacity-60"
							disabled={addingOrg || !selectedOrgId}
							onclick={handleAddOrg}
						>
							{addingOrg ? 'Adding…' : 'Add'}
						</button>
					</div>
					{#if orgError}
						<p class="m-0 mt-2 text-xs text-red-600">{orgError}</p>
					{/if}
				{:else}
					<p class="m-0 text-xs text-brand-steel">
						You have no other organizations to add. Create one from your profile.
					</p>
				{/if}
			</section>
		{/if}
	</div>
</div>
