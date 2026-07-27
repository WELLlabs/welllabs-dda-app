<script>
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { session } from '$lib/shared/session.svelte.js';

	/** @type {{ variant?: 'dark' | 'light' }} */
	let { variant = 'dark' } = $props();

	let open = $state(false);
	let menuEl = $state(null);

	function toggle() {
		open = !open;
	}

	function close(e) {
		if (menuEl && !menuEl.contains(e.target)) {
			open = false;
		}
	}

	onMount(() => {
		document.addEventListener('click', close, true);
		return () => document.removeEventListener('click', close, true);
	});

	function nav(path) {
		open = false;
		goto(path);
	}

	async function handleSignOut() {
		open = false;
		await session.logout();
		goto('/');
	}

</script>

{#if session.user}
	<div class="relative" bind:this={menuEl}>
		<button
			type="button"
			class="user"
			onclick={toggle}
			aria-label="Account menu"
		>
			<span class="avatar">{(session.user.name ?? 'DD').trim().split(/\s+/)
			.map((p) => p[0])
			.slice(0, 2)
			.join('')
			.toUpperCase()}</span>
			<span class="hidden text-left sm:block">
				<span class="block font-body text-[13px] leading-tight user-name">{session.user.name || 'Guest'}</span>
				
			</span>
			<svg
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="2"
				class="chev h-3.5 w-3.5 {open ? 'rotate-180' : ''}"
			>
				<path d="M6 9l6 6 6-6" stroke-linecap="round" stroke-linejoin="round" />
			</svg>
		</button>

		{#if open}
			<div class="menu">
				<button
					type="button"
					class="menu-item"
					onclick={() => nav('/settings/organizations')}
				>
					Organizations
				</button>
				<button
					type="button"
					class="menu-item"
					onclick={() => nav('/settings/connectors')}
				>
					Connectors
				</button>
				<div class="menu-sep"></div>
				<button type="button" class="menu-item danger" onclick={handleSignOut}>Sign out</button>
			</div>
		{/if}
	</div>
{/if}

<style>
	.user {
		display: inline-flex;
		align-items: center;
		gap: 0.6rem;
		padding: 0.35rem 0.6rem 0.35rem 0.4rem;
		border-radius: 12px;
		border: 1px solid transparent;
		background: none;
		cursor: pointer;
		transition: border-color 0.25s ease, background 0.25s ease;
	}

	.user:hover {
		border-color: rgba(20, 40, 60, 0.1);
		background: rgba(20, 40, 60, 0.04);
	}

	.user-name {
		color: #1a2530;
	}

	.user-role {
		color: #7a8794;
	}

	.chev {
		color: #7a8794;
		transition: transform 0.25s ease;
	}

	.avatar {
		display: grid;
		place-items: center;
		height: 2.1rem;
		width: 2.1rem;
		border-radius: 10px;
		font-family: var(--font-mono, monospace);
		font-size: 12px;
		font-weight: 600;
		color: #ffffff;
		background: linear-gradient(135deg, #0fb3a3, #7c5ce6);
		box-shadow: 0 6px 16px -8px rgba(124, 92, 230, 0.55);
	}

	.menu {
		position: absolute;
		right: 0;
		top: calc(100% + 0.5rem);
		min-width: 11rem;
		padding: 0.4rem;
		border-radius: 14px;
		border: 1px solid rgba(20, 40, 60, 0.08);
		background: #ffffff;
		box-shadow: 0 20px 45px -20px rgba(20, 40, 60, 0.35);
		animation: pop 0.18s ease;
	}

	@keyframes pop {
		from {
			opacity: 0;
			transform: translateY(-6px) scale(0.98);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}

	.menu-item {
		display: block;
		width: 100%;
		padding: 0.5rem 0.7rem;
		border: 0;
		border-radius: 9px;
		background: transparent;
		font-family: var(--font-body, sans-serif);
		font-size: 13px;
		text-align: left;
		color: #24303a;
		transition: background 0.2s ease;
		cursor: pointer;
	}

	.menu-item:hover {
		background: rgba(20, 40, 60, 0.05);
	}

	.menu-item.danger {
		color: #d64545;
	}

	.menu-sep {
		height: 1px;
		margin: 0.3rem 0;
		background: rgba(20, 40, 60, 0.08);
	}
</style>
