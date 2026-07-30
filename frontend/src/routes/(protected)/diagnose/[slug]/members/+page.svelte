<script>
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { session } from '$lib/shared/session.svelte.js';
	import { findBySlug } from '$lib/shared/slug.js';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import {
		fetchProjects,
		fetchProject,
		fetchUserAccess,
		fetchOrgAccess,
		addUserAccess,
		removeUserAccess,
		updateUserAccessRole,
		addOrgAccess,
		removeOrgAccess
	} from '$lib/modules/diagnose/api';
	import { fetchOrgs, lookupUserByEmail } from '$lib/modules/accounts/api.js';

	let slug = $derived(page.params.slug);

	let project = $state(null);
	let loading = $state(true);
	let loadError = $state('');

	let users = $state([]);
	let orgs = $state([]);
	let myOrgs = $state([]);
	let dataLoading = $state(true);
	let error = $state('');

	let emailInput = $state('');
	let lookupResult = $state(null);
	let lookupError = $state('');
	let lookingUp = $state(false);
	let addingUser = $state(false);
	let newUserRole = $state('member');

	let selectedOrgId = $state('');
	let addingOrg = $state(false);
	let orgError = $state('');

	const isOwner = $derived(project && session.user && project.owner_id === session.user.id);
	const isAdmin = $derived(
		isOwner ||
			(session.user && users.some((u) => u.id === session.user.id && u.role === 'admin'))
	);
	const availableOrgs = $derived(myOrgs.filter((o) => !orgs.some((s) => s.id === o.id)));

	async function loadProject(slugValue) {
		loading = true;
		loadError = '';
		project = null;
		try {
			const data = await fetchProjects();
			const match = findBySlug(data.projects ?? [], slugValue);
			if (!match) {
				loadError = 'Project not found';
				return;
			}
			project = await fetchProject(match.id);
		} catch (err) {
			loadError = String(err);
		} finally {
			loading = false;
		}
	}

	async function loadAccess() {
		if (!project) return;
		dataLoading = true;
		error = '';
		try {
			const [u, o, mine] = await Promise.all([
				fetchUserAccess(project.id),
				fetchOrgAccess(project.id),
				fetchOrgs()
			]);
			users = u;
			orgs = o;
			myOrgs = mine;
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			dataLoading = false;
		}
	}

	$effect(() => {
		loadProject(slug);
	});

	$effect(() => {
		if (project) loadAccess();
	});

	function backToProject() {
		goto(`/diagnose/${slug}`);
	}

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
		if (!lookupResult || !project) return;
		addingUser = true;
		try {
			await addUserAccess(project.id, lookupResult.email);
			emailInput = '';
			lookupResult = null;
			users = await fetchUserAccess(project.id);
		} catch (err) {
			lookupError = String(err.message ?? err);
		} finally {
			addingUser = false;
		}
	}

	async function handleRemoveUser(member) {
		if (!project || !confirm(`Remove ${member.name} from this project?`)) return;
		try {
			await removeUserAccess(project.id, member.id);
			users = users.filter((u) => u.id !== member.id);
		} catch (err) {
			error = String(err.message ?? err);
		}
	}

	async function handleLeaveProject() {
		if (!project || !session.user) return;
		if (!confirm('Leave this project? You will lose access.')) return;
		try {
			await removeUserAccess(project.id, session.user.id);
			goto('/diagnose');
		} catch (err) {
			error = String(err.message ?? err);
		}
	}

	async function handleToggleRole(member) {
		if (!project) return;
		const next = member.role === 'admin' ? 'member' : 'admin';
		const action = next === 'admin' ? 'Promote' : 'Demote';
		if (!confirm(`${action} ${member.name} to ${next}?`)) return;
		try {
			await updateUserAccessRole(project.id, member.id, next);
			users = await fetchUserAccess(project.id);
		} catch (err) {
			error = String(err.message ?? err);
		}
	}

	async function handleAddOrg() {
		if (!selectedOrgId || !project) return;
		addingOrg = true;
		orgError = '';
		try {
			await addOrgAccess(project.id, selectedOrgId);
			orgs = await fetchOrgAccess(project.id);
			selectedOrgId = '';
		} catch (err) {
			orgError = String(err.message ?? err);
		} finally {
			addingOrg = false;
		}
	}

	async function handleRemoveOrg(org) {
		if (!project || !confirm(`Remove "${org.name}" from this project?`)) return;
		try {
			await removeOrgAccess(project.id, org.id);
			orgs = orgs.filter((o) => o.id !== org.id);
		} catch (err) {
			error = String(err.message ?? err);
		}
	}
</script>

<svelte:head>
	<title>{project ? `Members · ${project.name}` : 'Members'}</title>
</svelte:head>

{#if loading}
	<div class="flex h-screen items-center justify-center bg-white font-body text-brand-steel">
		Loading…
	</div>
{:else if loadError || !project}
	<div class="flex h-screen flex-col items-center justify-center gap-4 bg-white font-body">
		<p class="m-0 text-brand-navy">{loadError || 'Project not found'}</p>
		<button
			class="cursor-pointer rounded bg-brand-blue px-4 py-2 font-body text-white hover:bg-brand-deep"
			onclick={() => goto('/diagnose')}
		>
			← Back to projects
		</button>
	</div>
{:else}
	<div class="flex min-h-screen flex-col bg-gray-50 font-body">
		<ModuleHeader
			title="Diagnose"
			titleHref="/diagnose"
			project={project.name}
			subtitle="Members & Access"
			wide
		>
			<button type="button" onclick={backToProject}>Back to map</button>
		</ModuleHeader>

		<main class="flex-1 overflow-auto p-6">
			<div class="mx-auto max-w-2xl space-y-6">
				{#if error}
					<div class="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
						{error}
						<button
							class="ml-2 cursor-pointer text-red-500 underline"
							onclick={() => (error = '')}
						>
							dismiss
						</button>
					</div>
				{/if}

				<!-- People section -->
				<section class="rounded-2xl border border-brand-navy/10 bg-white shadow-sm">
					<div class="border-b border-brand-navy/8 px-5 py-4">
						<h2 class="m-0 font-headline text-sm font-semibold tracking-wide text-brand-navy/60 uppercase">
							People
						</h2>
					</div>

					{#if dataLoading}
						<div class="px-5 py-6 text-center text-sm text-brand-steel">Loading members…</div>
					{:else}
						<div class="divide-y divide-brand-navy/6">
							<!-- Owner row (always first) -->
							<div class="flex items-center gap-3 px-5 py-3">
								<div
									class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-navy text-sm font-semibold text-white"
								>
									{(project.owner_name ?? 'O').charAt(0).toUpperCase()}
								</div>
								<div class="min-w-0 flex-1">
									<p class="m-0 truncate text-sm font-medium text-brand-navy">
										{project.owner_name}
										{#if isOwner}
											<span class="text-brand-steel">(you)</span>
										{/if}
									</p>
									<p class="m-0 truncate text-xs text-brand-steel">{project.owner_email}</p>
								</div>
								<span
									class="rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase"
									style="background: color-mix(in srgb, #7c3aed 14%, transparent); color: #7c3aed;"
								>
									owner
								</span>
							</div>

							<!-- Other members -->
							{#each users as member (member.id)}
								{@const isSelf = session.user && member.id === session.user.id}
								<div class="flex items-center gap-3 px-5 py-3">
									<div
										class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-brand-sky/20 text-sm font-semibold text-brand-navy"
									>
										{(member.name ?? '?').charAt(0).toUpperCase()}
									</div>
									<div class="min-w-0 flex-1">
										<p class="m-0 truncate text-sm font-medium text-brand-navy">
											{member.name}
											{#if isSelf}
												<span class="text-brand-steel">(you)</span>
											{/if}
										</p>
										<p class="m-0 truncate text-xs text-brand-steel">{member.email}</p>
									</div>
									<span
										class="rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase"
										style:background-color={member.role === 'admin'
											? 'color-mix(in srgb, #0d983b 14%, transparent)'
											: 'color-mix(in srgb, #1b75e0 14%, transparent)'}
										style:color={member.role === 'admin' ? '#0d983b' : '#1b75e0'}
									>
										{member.role}
									</span>
									{#if isSelf && !isOwner}
										<button
											type="button"
											class="shrink-0 cursor-pointer rounded border-0 bg-transparent px-2 py-1 text-xs text-red-600 hover:bg-red-50"
											onclick={handleLeaveProject}
										>
											Leave
										</button>
									{:else if isAdmin && !isSelf}
										<div class="flex shrink-0 gap-1">
											<button
												type="button"
												class="cursor-pointer rounded border-0 bg-transparent px-2 py-1 text-xs text-brand-blue hover:bg-brand-sky/15"
												onclick={() => handleToggleRole(member)}
											>
												{member.role === 'admin' ? 'Demote' : 'Make admin'}
											</button>
											<button
												type="button"
												class="cursor-pointer rounded border-0 bg-transparent px-2 py-1 text-xs text-red-600 hover:bg-red-50"
												onclick={() => handleRemoveUser(member)}
											>
												Remove
											</button>
										</div>
									{/if}
								</div>
							{/each}
						</div>

						{#if isAdmin}
							<div class="border-t border-brand-navy/8 px-5 py-4">
								<p class="m-0 mb-3 text-xs font-medium text-brand-steel uppercase">Add a person</p>
								<div class="flex gap-2">
									<input
										type="email"
										placeholder="Enter email address"
										class="flex-1 rounded-lg border border-brand-navy/15 px-3 py-2 font-body text-sm outline-none focus:border-brand-blue"
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
										class="cursor-pointer rounded-lg bg-brand-blue px-4 py-2 font-body text-sm font-medium text-white hover:bg-brand-deep disabled:opacity-60"
										disabled={lookingUp || !emailInput.trim()}
										onclick={handleLookup}
									>
										{lookingUp ? 'Searching…' : 'Look up'}
									</button>
								</div>

								{#if lookupError}
									<p class="m-0 mt-2 text-xs text-red-600">{lookupError}</p>
								{:else if lookupResult}
									<div class="mt-3 flex items-center gap-3 rounded-lg bg-brand-sky/10 px-4 py-3">
										<div
											class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-sky/30 text-xs font-semibold text-brand-navy"
										>
											{(lookupResult.name ?? '?').charAt(0).toUpperCase()}
										</div>
										<div class="min-w-0 flex-1">
											<p class="m-0 text-sm font-medium text-brand-navy">{lookupResult.name}</p>
											<p class="m-0 text-xs text-brand-steel">{lookupResult.email}</p>
										</div>
										<button
											type="button"
											class="cursor-pointer rounded-lg bg-brand-blue px-3 py-1.5 font-body text-xs font-medium text-white hover:bg-brand-deep disabled:opacity-60"
											disabled={addingUser}
											onclick={handleAddUser}
										>
											{addingUser ? 'Adding…' : 'Add'}
										</button>
									</div>
								{/if}
							</div>
						{/if}
					{/if}
				</section>

				<!-- Organizations section -->
				<section class="rounded-2xl border border-brand-navy/10 bg-white shadow-sm">
					<div class="border-b border-brand-navy/8 px-5 py-4">
						<h2 class="m-0 font-headline text-sm font-semibold tracking-wide text-brand-navy/60 uppercase">
							Organizations
						</h2>
					</div>

					{#if dataLoading}
						<div class="px-5 py-6 text-center text-sm text-brand-steel">Loading…</div>
					{:else}
						<div class="divide-y divide-brand-navy/6">
							{#if orgs.length === 0}
								<div class="px-5 py-6 text-center text-sm text-brand-steel">
									No organizations have access yet.
								</div>
							{/if}

							{#each orgs as org (org.id)}
								<div class="flex items-center gap-3 px-5 py-3">
									<div
										class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-amber-100 text-sm font-semibold text-amber-700"
									>
										{(org.name ?? '?').charAt(0).toUpperCase()}
									</div>
									<div class="min-w-0 flex-1">
										<p class="m-0 truncate text-sm font-medium text-brand-navy">{org.name}</p>
									</div>
									{#if isAdmin}
										<button
											type="button"
											class="cursor-pointer rounded border-0 bg-transparent px-2 py-1 text-xs text-red-600 hover:bg-red-50"
											onclick={() => handleRemoveOrg(org)}
										>
											Remove
										</button>
									{/if}
								</div>
							{/each}
						</div>

						{#if isAdmin}
							<div class="border-t border-brand-navy/8 px-5 py-4">
								{#if availableOrgs.length > 0}
									<p class="m-0 mb-3 text-xs font-medium text-brand-steel uppercase">
										Add an organization
									</p>
									<div class="flex gap-2">
										<select
											class="flex-1 rounded-lg border border-brand-navy/15 px-3 py-2 font-body text-sm outline-none focus:border-brand-blue"
											bind:value={selectedOrgId}
										>
											<option value="">Select an organization…</option>
											{#each availableOrgs as org (org.id)}
												<option value={org.id}>{org.name}</option>
											{/each}
										</select>
										<button
											type="button"
											class="cursor-pointer rounded-lg bg-brand-blue px-4 py-2 font-body text-sm font-medium text-white hover:bg-brand-deep disabled:opacity-60"
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
										You have no other organizations to add. Create one from
										<a href="/settings/organizations" class="text-brand-blue underline">settings</a>.
									</p>
								{/if}
							</div>
						{/if}
					{/if}
				</section>
			</div>
		</main>
	</div>
{/if}
