<script>
	import { onMount } from 'svelte';
	import { session } from '$lib/shared/session.svelte.js';
	import {
		addOrgMember,
		createOrg,
		deleteOrg,
		fetchOrgMembers,
		fetchOrgProjects,
		fetchOrgs,
		removeOrgMember,
		updateMemberRole
	} from '$lib/modules/accounts/api.js';

	let orgs = $state([]);
	let loading = $state(true);
	let error = $state('');

	let showCreate = $state(false);
	let newOrgName = $state('');
	let creating = $state(false);

	let expandedOrgId = $state(null);
	let activeTab = $state({});
	let members = $state({});
	let projects = $state({});
	let membersLoading = $state({});
	let projectsLoading = $state({});

	let addEmailByOrg = $state({});
	let addBusyOrgId = $state(null);
	let addErrorByOrg = $state({});

	onMount(loadOrgs);

	async function loadOrgs() {
		loading = true;
		error = '';
		try {
			orgs = await fetchOrgs();
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			loading = false;
		}
	}

	async function toggleOrg(org) {
		if (expandedOrgId === org.id) {
			expandedOrgId = null;
			return;
		}
		expandedOrgId = org.id;
		if (!activeTab[org.id]) activeTab = { ...activeTab, [org.id]: 'members' };
		await loadOrgMembers(org.id);
	}

	function switchTab(orgId, tab) {
		activeTab = { ...activeTab, [orgId]: tab };
		if (tab === 'members' && !members[orgId]) loadOrgMembers(orgId);
		if (tab === 'projects' && !projects[orgId]) loadOrgProjects(orgId);
	}

	async function loadOrgMembers(orgId) {
		if (members[orgId]) return;
		membersLoading = { ...membersLoading, [orgId]: true };
		try {
			members = { ...members, [orgId]: await fetchOrgMembers(orgId) };
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			membersLoading = { ...membersLoading, [orgId]: false };
		}
	}

	async function loadOrgProjects(orgId) {
		if (projects[orgId]) return;
		projectsLoading = { ...projectsLoading, [orgId]: true };
		try {
			projects = { ...projects, [orgId]: await fetchOrgProjects(orgId) };
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			projectsLoading = { ...projectsLoading, [orgId]: false };
		}
	}

	async function handleCreateOrg(e) {
		e.preventDefault();
		if (!newOrgName.trim()) return;
		creating = true;
		error = '';
		try {
			await createOrg(newOrgName.trim());
			newOrgName = '';
			showCreate = false;
			await loadOrgs();
		} catch (err) {
			error = String(err.message ?? err);
		} finally {
			creating = false;
		}
	}

	async function handleAddMember(org) {
		const email = (addEmailByOrg[org.id] ?? '').trim();
		if (!email) return;
		addBusyOrgId = org.id;
		addErrorByOrg = { ...addErrorByOrg, [org.id]: '' };
		try {
			await addOrgMember(org.id, email);
			addEmailByOrg = { ...addEmailByOrg, [org.id]: '' };
			members = { ...members, [org.id]: await fetchOrgMembers(org.id) };
		} catch (err) {
			addErrorByOrg = { ...addErrorByOrg, [org.id]: String(err.message ?? err) };
		} finally {
			addBusyOrgId = null;
		}
	}

	async function handleRemoveMember(org, member) {
		if (!confirm(`Remove ${member.name} from ${org.name}?`)) return;
		try {
			await removeOrgMember(org.id, member.id);
			members = { ...members, [org.id]: await fetchOrgMembers(org.id) };
		} catch (err) {
			error = String(err.message ?? err);
		}
	}

	async function handleToggleAdmin(org, member) {
		const newRole = member.role === 'admin' ? 'member' : 'admin';
		const action = newRole === 'admin' ? 'Promote' : 'Demote';
		if (!confirm(`${action} ${member.name} to ${newRole}?`)) return;
		try {
			await updateMemberRole(org.id, member.id, newRole);
			members = { ...members, [org.id]: await fetchOrgMembers(org.id) };
		} catch (err) {
			error = String(err.message ?? err);
		}
	}

	async function handleLeaveOrg(org) {
		if (!session.user) return;
		if (!confirm(`Leave "${org.name}"? You will lose access to shared projects.`)) return;
		try {
			await removeOrgMember(org.id, session.user.id);
			expandedOrgId = null;
			await loadOrgs();
		} catch (err) {
			error = String(err.message ?? err);
		}
	}

	async function handleDeleteOrg(org) {
		if (!confirm(`Delete "${org.name}"? Members will lose org-level access to shared projects. The projects themselves will not be deleted.`))
			return;
		try {
			await deleteOrg(org.id);
			expandedOrgId = null;
			await loadOrgs();
		} catch (err) {
			error = String(err.message ?? err);
		}
	}
</script>

<svelte:head>
	<title>Organizations · Settings</title>
</svelte:head>

<div class="max-w-2xl">
	<div class="mb-5 flex items-center justify-between">
		<h2 class="m-0 font-headline text-lg font-semibold text-brand-navy">Organizations</h2>
		<button
			type="button"
			class="cursor-pointer rounded-lg bg-brand-blue px-3 py-1.5 font-body text-sm font-medium text-white hover:bg-brand-deep"
			onclick={() => (showCreate = !showCreate)}
		>
			{showCreate ? 'Cancel' : '+ New'}
		</button>
	</div>

	{#if showCreate}
		<form onsubmit={handleCreateOrg} class="mb-5 flex gap-2 rounded-xl border border-brand-navy/10 bg-white p-4 shadow-sm">
			<input
				type="text"
				required
				placeholder="Organization name"
				class="flex-1 rounded-lg border border-brand-navy/15 px-3 py-2 font-body text-sm outline-none focus:border-brand-blue"
				bind:value={newOrgName}
			/>
			<button
				type="submit"
				class="cursor-pointer rounded-lg bg-brand-blue px-4 py-2 font-body text-sm font-medium text-white disabled:opacity-60"
				disabled={creating || !newOrgName.trim()}
			>
				{creating ? 'Creating…' : 'Create'}
			</button>
		</form>
	{/if}

	{#if error}
		<div class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
			{error}
			<button class="ml-2 cursor-pointer text-red-500 underline" onclick={() => (error = '')}>dismiss</button>
		</div>
	{/if}

	{#if loading}
		<p class="m-0 text-center text-sm text-brand-steel">Loading organizations…</p>
	{:else if orgs.length === 0}
		<div class="rounded-2xl border border-brand-navy/10 bg-white p-8 text-center shadow-sm">
			<p class="m-0 text-sm text-brand-steel">
				You're not part of any organization yet. Create one to share diagnoses with your team.
			</p>
		</div>
	{:else}
		<div class="space-y-3">
			{#each orgs as org (org.id)}
				<div class="rounded-2xl border border-brand-navy/10 bg-white shadow-sm">
					<button
						type="button"
						class="flex w-full cursor-pointer items-center gap-3 rounded-2xl border-0 bg-transparent px-5 py-4 text-left"
						onclick={() => toggleOrg(org)}
					>
						<div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-sm font-semibold text-amber-700">
							{(org.name ?? '?').charAt(0).toUpperCase()}
						</div>
						<span class="min-w-0 flex-1 font-body text-sm font-medium text-brand-navy">{org.name}</span>
						<span
							class="rounded-full px-2.5 py-0.5 text-[10px] font-semibold tracking-wide uppercase"
							style:background-color={org.role === 'admin'
								? 'color-mix(in srgb, #1b75e0 14%, transparent)'
								: 'color-mix(in srgb, #1b75e0 14%, transparent)'}
							style:color={org.role === 'admin' ? '#1b75e0' : '#1b75e0'}
						>
							{org.role}
						</span>
						<svg
							xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor"
							class="h-4 w-4 text-brand-steel transition-transform {expandedOrgId === org.id ? 'rotate-180' : ''}"
						>
							<path fill-rule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" clip-rule="evenodd" />
						</svg>
					</button>

					{#if expandedOrgId === org.id}
						<div class="border-t border-brand-navy/8">
							<!-- Tabs -->
							<div class="flex gap-0 border-b border-brand-navy/8 px-5">
								<button
									type="button"
									class="cursor-pointer border-0 bg-transparent px-3 py-2.5 font-body text-sm font-medium {(activeTab[org.id] ?? 'members') === 'members'
										? 'border-b-2 border-brand-blue text-brand-navy'
										: 'text-brand-steel hover:text-brand-navy'}"
									onclick={() => switchTab(org.id, 'members')}
								>
									Members
								</button>
								<button
									type="button"
									class="cursor-pointer border-0 bg-transparent px-3 py-2.5 font-body text-sm font-medium {(activeTab[org.id] ?? 'members') === 'projects'
										? 'border-b-2 border-brand-blue text-brand-navy'
										: 'text-brand-steel hover:text-brand-navy'}"
									onclick={() => switchTab(org.id, 'projects')}
								>
									Projects
								</button>
							</div>

							<!-- Members tab -->
							{#if (activeTab[org.id] ?? 'members') === 'members'}
								{#if membersLoading[org.id]}
									<div class="px-5 py-4 text-center text-sm text-brand-steel">Loading members…</div>
								{:else}
									<div class="divide-y divide-brand-navy/6">
										{#each members[org.id] ?? [] as member (member.id)}
											{@const isSelf = session.user && member.id === session.user.id}
											<div class="flex items-center gap-3 px-5 py-2.5">
												<div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-sky/20 text-xs font-semibold text-brand-navy">
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
													class="rounded-full px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase"
													style:background-color={member.role === 'admin'
														? 'color-mix(in srgb, #1b75e0 14%, transparent)'
														: 'color-mix(in srgb, #1b75e0 14%, transparent)'}
													style:color={member.role === 'admin' ? '#1b75e0' : '#1b75e0'}
												>
													{member.role}
												</span>
												{#if org.role === 'admin' && !isSelf}
													<div class="flex shrink-0 gap-1">
														<button
															type="button"
															class="cursor-pointer rounded border-0 bg-transparent px-2 py-1 text-xs text-brand-blue hover:bg-brand-sky/15"
															onclick={() => handleToggleAdmin(org, member)}
														>
															{member.role === 'admin' ? 'Demote' : 'Make admin'}
														</button>
														<button
															type="button"
															class="cursor-pointer rounded border-0 bg-transparent px-2 py-1 text-xs text-red-600 hover:bg-red-50"
															onclick={() => handleRemoveMember(org, member)}
														>
															Remove
														</button>
													</div>
												{/if}
											</div>
										{/each}
									</div>

									{#if org.role === 'admin'}
										<div class="border-t border-brand-navy/8 px-5 py-3">
											<p class="m-0 mb-2 text-xs font-medium text-brand-steel uppercase">Add a member</p>
											<div class="flex gap-2">
												<input
													type="email"
													placeholder="Enter email address"
													class="flex-1 rounded-lg border border-brand-navy/15 px-3 py-2 font-body text-sm outline-none focus:border-brand-blue"
													bind:value={addEmailByOrg[org.id]}
													onkeydown={(e) => {
														if (e.key === 'Enter') {
															e.preventDefault();
															handleAddMember(org);
														}
													}}
												/>
												<button
													type="button"
													class="cursor-pointer rounded-lg bg-brand-blue px-3 py-2 font-body text-xs font-medium text-white disabled:opacity-60"
													disabled={addBusyOrgId === org.id || !(addEmailByOrg[org.id] ?? '').trim()}
													onclick={() => handleAddMember(org)}
												>
													{addBusyOrgId === org.id ? 'Adding…' : 'Add'}
												</button>
											</div>
											{#if addErrorByOrg[org.id]}
												<p class="m-0 mt-2 text-xs text-red-600">{addErrorByOrg[org.id]}</p>
											{/if}
										</div>
									{/if}
								{/if}
							{/if}

							<!-- Projects tab -->
							{#if (activeTab[org.id] ?? 'members') === 'projects'}
								{#if projectsLoading[org.id]}
									<div class="px-5 py-4 text-center text-sm text-brand-steel">Loading projects…</div>
								{:else if (projects[org.id] ?? []).length === 0}
									<div class="px-5 py-6 text-center text-sm text-brand-steel">
										No projects shared with this organization yet.
									</div>
								{:else}
									<div class="divide-y divide-brand-navy/6">
										{#each projects[org.id] ?? [] as project (project.id)}
											<div class="flex items-center gap-3 px-5 py-2.5">
												<div class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-brand-blue/10 text-xs font-semibold text-brand-blue">
													{(project.name ?? '?').charAt(0).toUpperCase()}
												</div>
												<div class="min-w-0 flex-1">
													<p class="m-0 truncate text-sm font-medium text-brand-navy">{project.name}</p>
													<p class="m-0 text-xs text-brand-steel">by {project.owner_name}</p>
												</div>
												<span class="text-xs text-brand-steel">
													{new Date(project.created_at).toLocaleDateString()}
												</span>
											</div>
										{/each}
									</div>
								{/if}
							{/if}

							<!-- Actions -->
							<div class="flex items-center justify-between border-t border-brand-navy/8 px-5 py-3">
								<button
									type="button"
									class="cursor-pointer rounded-lg border border-brand-navy/15 bg-white px-3 py-1.5 font-body text-xs font-medium text-brand-navy hover:bg-gray-50"
									onclick={() => handleLeaveOrg(org)}
								>
									Leave organization
								</button>
								{#if org.role === 'admin'}
									<button
										type="button"
										class="cursor-pointer rounded-lg border border-red-200 bg-white px-3 py-1.5 font-body text-xs font-medium text-red-600 hover:bg-red-50"
										onclick={() => handleDeleteOrg(org)}
									>
										Delete organization
									</button>
								{/if}
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
