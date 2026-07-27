<script>
	import UserMenu from '$lib/shared/components/UserMenu.svelte';

	/** @type {{ title?: string, project?: string, subtitle?: string, homeHref?: string }} */
	let { title = '', project = '', subtitle = '', homeHref = '/home' } = $props();
</script>

<header class="hdr">
	<div class="mx-auto flex max-w-6xl items-center justify-between px-6 md:px-10">
		<!-- brand + breadcrumb -->
		<a href={homeHref} class="brand group">
			<span class="brand-mark">
				<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" class="h-5 w-5">
					<path d="M12 3c3.5 4 6 7 6 10a6 6 0 1 1-12 0c0-3 2.5-6 6-10z" stroke-linejoin="round" />
				</svg>
			</span>
			<span class="crumb">
				<span class="brand-name font-display">Water security Tool</span>
				{#if title}
					<span class="sep">/</span>
					<span class="crumb-module font-display">{title}</span>
				{/if}
				{#if project}
					<span class="sep">/</span>
					<span class="crumb-project font-body">{project}</span>
				{/if}
			</span>
		</a>

		<!-- user -->
		<UserMenu variant="light" />
	</div>
</header>

<style>
	.hdr {
		position: sticky;
		top: 0;
		z-index: 40;
		padding: 0.85rem 0;
		border-bottom: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.72);
		backdrop-filter: blur(14px);
	}

	.brand { display: inline-flex; align-items: center; gap: 0.7rem; min-width: 0; }
	.brand-mark {
		display: grid;
		place-items: center;
		height: 2.25rem;
		width: 2.25rem;
		flex: none;
		border-radius: 12px;
		color: #0fb3a3;
		border: 1px solid color-mix(in srgb, #0fb3a3 28%, transparent);
		background: color-mix(in srgb, #0fb3a3 12%, white);
		transition: transform 0.3s ease, box-shadow 0.3s ease;
	}
	.brand:hover .brand-mark {
		transform: rotate(-6deg) scale(1.05);
		box-shadow: 0 10px 22px -12px rgba(15, 179, 163, 0.6);
	}

	.crumb {
		display: inline-flex;
		align-items: baseline;
		gap: 0.5rem;
		min-width: 0;
		overflow: hidden;
		white-space: nowrap;
	}
	.brand-name {
		font-size: 1.15rem;
		letter-spacing: 0.04em;
		background: linear-gradient(100deg, #0fb3a3, #7c5ce6);
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
	}
	.sep { color: #b3bcc5; font-size: 1rem; }
	.crumb-module {
		font-size: 1.05rem;
		font-weight: 600;
		color: #1a2530;
	}
	.crumb-project {
		font-size: 0.95rem;
		color: #6b7885;
		overflow: hidden;
		text-overflow: ellipsis;
	}
</style>
