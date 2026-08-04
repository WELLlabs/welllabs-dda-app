<script>
	import { goto } from '$app/navigation';
	import { session } from '$lib/shared/session.svelte.js';
	import DashboardHeader from '$lib/shared/components/landing/DashboardHeader.svelte';
	import ContourBackground from '$lib/shared/components/landing/ContourBackground.svelte';

	const modules = [
		{
			id: 'diagnose',
			href: '/diagnose',
			title: 'Diagnose',
			description:
				'Map watersheds, draw observation zones, and capture geotagged field notes — synced offline with QField.',
			status: 'Available',
			accent: '#0FB3A3',
			accentClass: 'text-diagnose',
			borderClass: 'hover:border-diagnose/50',
			badgeClass: 'text-diagnose border-diagnose/30 bg-diagnose/10',
			icon: 'diagnose',
			available: true
		},
		{
			id: 'design',
			href: '/design',
			title: 'Design',
			description: 'Plan and design interventions on top of diagnosed watersheds.',
			status: 'Coming soon',
			accent: '#C98A16',
			accentClass: 'text-design',
			borderClass: 'hover:border-design/50',
			badgeClass: 'text-design border-design/30 bg-design/10',
			icon: 'design',
			available: false
		},
		{
			id: 'assess',
			href: '/assess',
			title: 'Assess',
			description: 'Track outcomes and assess impact of implemented designs over time.',
			status: 'Coming soon',
			accent: '#7C5CE6',
			accentClass: 'text-assess',
			borderClass: 'hover:border-assess/50',
			badgeClass: 'text-assess border-assess/30 bg-assess/10',
			icon: 'assess',
			available: false
		}
	];

	let mounted = $state(false);
	$effect(() => {
		mounted = true;
	});

	function openModule(mod) {
		goto(mod.href);
	}

	function handlePointer(event) {
		const el = event.currentTarget;
		const rect = el.getBoundingClientRect();
		el.style.setProperty('--mx', `${event.clientX - rect.left}px`);
		el.style.setProperty('--my', `${event.clientY - rect.top}px`);
	}
</script>

<svelte:head>
	<title>Dashboard · DDA</title>
</svelte:head>

<div class="page relative min-h-screen overflow-hidden font-body">
	

	<!-- soft ambient wash -->
	<div class="pointer-events-none absolute inset-0 z-0 overflow-hidden">
		<div class="glow glow-a"></div>
		<div class="glow glow-b"></div>
		<div class="glow glow-c"></div>
	</div>

	<DashboardHeader name={session.user?.name ?? ''} />

	<main class="relative z-10 px-6 py-16 md:px-10">
		<div class="mx-auto max-w-6xl">
			<div class="intro" class:in={mounted}>
				<span class="badge-eyebrow font-mono text-[11px] uppercase tracking-[0.25em]">
					<span class="dot"></span> Where you left off
				</span>

				<h1 class="mt-4 font-display text-4xl leading-[1.05] md:text-5xl">
					Welcome,
					<span class="name-grad">{session.user?.name ?? 'there'}</span>.
				</h1>

				<p class="mt-4 max-w-xl font-body text-[15px] leading-relaxed">
					Pick a module below to get started, or continue right where you left off. Every step —
					from diagnosis to impact — lives here.
				</p>
			</div>

			<div class="mt-14 mb-6 flex items-center gap-3">
				<h2 class="section-label font-mono text-[11px] uppercase tracking-[0.25em]">
					Choose a module
				</h2>
				<span class="divider h-px flex-1"></span>
			</div>

			<div class="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
				{#each modules as mod, i (mod.id)}
					<button
						type="button"
						class="card group"
						class:in={mounted}
						style="--accent: {mod.accent}; --delay: {i * 90}ms;"
						onpointermove={handlePointer}
						onclick={() => openModule(mod)}
					>
						<span class="card-spotlight" aria-hidden="true"></span>
						<span class="card-topline" aria-hidden="true"></span>

						<div class="relative z-10 flex w-full flex-col items-start gap-4">
							<div class="icon-wrap">
								{#if mod.icon === 'diagnose'}
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke={mod.accent} stroke-width="1.75" class="h-6 w-6">
										<circle cx="12" cy="12" r="7.5" />
										<path d="M12 4.5v15M4.5 12h15" />
										<circle cx="12" cy="12" r="1.75" fill={mod.accent} stroke="none" />
									</svg>
								{:else if mod.icon === 'design'}
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke={mod.accent} stroke-width="1.75" class="h-6 w-6">
										<path d="M4 19.5V16l9-9 3.5 3.5-9 9H4z" stroke-linejoin="round" />
										<path d="M13 7l3.5 3.5" />
										<path d="M17.5 4.5 19.5 6.5" stroke-linecap="round" />
									</svg>
								{:else}
									<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke={mod.accent} stroke-width="1.75" class="h-6 w-6">
										<path d="M4 19h16" stroke-linecap="round" />
										<path d="M7 19v-5M12 19V8M17 19v-9" stroke-linecap="round" />
									</svg>
								{/if}
							</div>

							<div class="flex w-full items-center justify-between gap-2">
								<h3 class="card-title m-0 font-display text-xl">{mod.title}</h3>
								<span class="badge {mod.badgeClass}" class:live={mod.available}>
									{#if mod.available}<span class="pulse"></span>{/if}
									{mod.status}
								</span>
							</div>

							<p class="card-desc m-0 font-body text-[13.5px] leading-relaxed">
								{mod.description}
							</p>

							<span class="cta mt-2 font-mono text-[12px] {mod.accentClass}">
								Open {mod.title}
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" class="arrow h-3.5 w-3.5">
									<path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
								</svg>
							</span>
						</div>
					</button>
				{/each}
			</div>
		</div>
	</main>
</div>

<style>
	/* light theme surface */
	.page {
		background: linear-gradient(180deg, #f7f9fb 0%, #eef2f6 100%);
		color: #24303a;
	}

	/* ---- ambient glows (soft, pastel) ---- */
	.glow {
		position: absolute;
		border-radius: 9999px;
		filter: blur(90px);
		opacity: 0.55;
		animation: drift 18s ease-in-out infinite;
	}
	.glow-a {
		top: -8%;
		left: -6%;
		width: 42vw;
		height: 42vw;
		background: radial-gradient(circle, rgba(15, 179, 163, 0.22), transparent 70%);
	}
	.glow-b {
		bottom: -12%;
		right: -8%;
		width: 46vw;
		height: 46vw;
		background: radial-gradient(circle, rgba(124, 92, 230, 0.18), transparent 70%);
		animation-delay: -6s;
	}
	.glow-c {
		top: 30%;
		right: 20%;
		width: 26vw;
		height: 26vw;
		background: radial-gradient(circle, rgba(201, 138, 22, 0.16), transparent 70%);
		animation-delay: -11s;
	}
	@keyframes drift {
		0%, 100% { transform: translate(0, 0) scale(1); }
		50% { transform: translate(3%, 4%) scale(1.08); }
	}

	/* ---- intro entrance ---- */
	.intro {
		opacity: 0;
		transform: translateY(14px);
		transition: opacity 0.7s ease, transform 0.7s cubic-bezier(0.2, 0.8, 0.2, 1);
	}
	.intro.in { opacity: 1; transform: none; }
	.intro h1 { color: #16212b; }
	.intro p { color: #56646f; }

	.badge-eyebrow { display: inline-flex; align-items: center; gap: 0.5rem; color: #6b7885; }
	.badge-eyebrow .dot {
		width: 7px;
		height: 7px;
		border-radius: 9999px;
		background: #0fb3a3;
		animation: ping 2.2s ease-out infinite;
	}
	@keyframes ping {
		0% { box-shadow: 0 0 0 0 rgba(15, 179, 163, 0.5); }
		70%, 100% { box-shadow: 0 0 0 8px rgba(15, 179, 163, 0); }
	}

	.name-grad {
		background: linear-gradient(100deg, #0fb3a3, #7c5ce6 60%, #c98a16);
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		background-size: 200% auto;
		animation: shimmer 6s ease-in-out infinite;
	}
	@keyframes shimmer {
		0%, 100% { background-position: 0% center; }
		50% { background-position: 100% center; }
	}

	.section-label { color: #6b7885; }
	.divider { background: linear-gradient(to right, rgba(20, 40, 60, 0.14), transparent); }

	/* ---- cards ---- */
	.card {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		overflow: hidden;
		border-radius: 22px;
		border: 1px solid rgba(20, 40, 60, 0.08);
		background: rgba(255, 255, 255, 0.85);
		padding: 1.6rem;
		text-align: left;
		cursor: pointer;
		backdrop-filter: blur(6px);
		box-shadow: 0 1px 0 rgba(255, 255, 255, 0.8) inset, 0 12px 28px -20px rgba(20, 40, 60, 0.35);
		opacity: 0;
		transform: translateY(24px);
		transition:
			transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1),
			box-shadow 0.35s ease,
			border-color 0.35s ease,
			opacity 0.6s ease;
	}
	.card.in {
		opacity: 1;
		transform: translateY(0);
		transition-delay: var(--delay);
	}
	.card:hover {
		transform: translateY(-6px);
		border-color: color-mix(in srgb, var(--accent) 45%, transparent);
		box-shadow:
			0 1px 0 rgba(255, 255, 255, 0.9) inset,
			0 24px 44px -22px color-mix(in srgb, var(--accent) 50%, transparent);
	}
	.card:active { transform: translateY(-2px) scale(0.995); }
	.card:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }

	.card-spotlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		opacity: 0;
		transition: opacity 0.3s ease;
		background: radial-gradient(
			320px circle at var(--mx, 50%) var(--my, 0%),
			color-mix(in srgb, var(--accent) 14%, transparent),
			transparent 60%
		);
	}
	.card:hover .card-spotlight { opacity: 1; }

	.card-topline {
		position: absolute;
		top: 0;
		left: 0;
		height: 3px;
		width: 100%;
		transform: scaleX(0);
		transform-origin: left;
		background: linear-gradient(90deg, var(--accent), transparent);
		transition: transform 0.4s cubic-bezier(0.2, 0.8, 0.2, 1);
	}
	.card:hover .card-topline { transform: scaleX(1); }

	.card-title { color: #1a2530; }
	.card-desc { color: #56646f; }

	.icon-wrap {
		display: flex;
		height: 3rem;
		width: 3rem;
		align-items: center;
		justify-content: center;
		border-radius: 14px;
		border: 1px solid rgba(20, 40, 60, 0.06);
		background: color-mix(in srgb, var(--accent) 12%, white);
		transition: transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1), box-shadow 0.35s ease;
	}
	.card:hover .icon-wrap {
		transform: scale(1.08) rotate(-4deg);
		box-shadow: 0 10px 24px -12px color-mix(in srgb, var(--accent) 60%, transparent);
	}

	.badge {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		flex-shrink: 0;
		border-radius: 9999px;
		border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
		background: color-mix(in srgb, var(--accent) 12%, white);
		color: color-mix(in srgb, var(--accent) 75%, black);
		padding: 0.15rem 0.6rem;
		font-family: var(--font-mono, monospace);
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}
	.badge .pulse {
		width: 6px;
		height: 6px;
		border-radius: 9999px;
		background: var(--accent);
		animation: ping 2s ease-out infinite;
	}

	.cta { display: inline-flex; align-items: center; gap: 0.35rem; color: color-mix(in srgb, var(--accent) 80%, black); }
	.cta .arrow { transition: transform 0.3s ease; }
	.card:hover .cta .arrow { transform: translateX(4px); }

	@media (prefers-reduced-motion: reduce) {
		.glow, .badge-eyebrow .dot, .name-grad, .badge .pulse { animation: none; }
		.card, .intro { transition: none; opacity: 1; transform: none; }
	}
</style>
