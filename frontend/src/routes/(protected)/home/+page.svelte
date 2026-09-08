<script>
	import { goto } from '$app/navigation';
	import { session } from '$lib/shared/session.svelte.js';
	import { appPath } from '$lib/shared/paths.js';
	import DashboardHeader from '$lib/shared/components/landing/DashboardHeader.svelte';

	const modules = [
		{
			id: 'diagnose',
			href: '/diagnose',
			title: 'Problem Diagnosis',
			description:
				'The Problem Diagnosis tool brings together secondary data on a watershed, letting a user mark observation zones and log hypotheses against them. Field teams verify these hypotheses using QField, a mobile app that syncs with the web tool and captures geotagged photographs, audio, and notes, arriving at community-validated landscape objectives.',
			accent: '#1b75e0',
			accentClass: 'text-diagnose',
			icon: 'diagnose',
			available: true
		},
		{
			id: 'design',
			href: '/design',
			title: 'Solution Design',
			description:
				'The Solutions Basket tool matches field-validated objectives to landscape conditions such as slope, stream order, and land use, shortlisting technically feasible interventions from a repository of over 100 solutions. Each shortlisted solution is reviewed with the community before being finalised.',
			accent: '#C98A16',
			accentClass: 'text-design',
			icon: 'design',
			available: false
		},
		{
			id: 'assess',
			href: '/assess',
			title: 'MEL',
			description:
				'This two-in-one tool, which includes the MEL Plan and MEL Dashboard, tracks whether finalised solutions deliver real water and socio-economic outcomes, using low-cost manual instruments and continuous field monitoring rather than one-off estimates. Community resource persons record data through mobile forms, which feed real-time visualisations and impact reports.',
			accent: '#186d13',
			accentClass: 'text-brand-forest',
			icon: 'assess',
			available: true
		}
	];

	let mounted = $state(false);
	$effect(() => {
		mounted = true;
	});

	function openModule(mod) {
		if (!mod.available) return;
		goto(appPath(mod.href));
	}

	function handlePointer(event) {
		const el = event.currentTarget;
		const rect = el.getBoundingClientRect();
		el.style.setProperty('--mx', `${event.clientX - rect.left}px`);
		el.style.setProperty('--my', `${event.clientY - rect.top}px`);
	}
</script>

<svelte:head>
	<title>Dashboard · Water Security Toolbox</title>
</svelte:head>

<div class="page relative min-h-screen overflow-hidden font-body">
	<div class="pointer-events-none absolute inset-0 z-0 overflow-hidden">
		<div class="glow glow-a"></div>
		<div class="glow glow-b"></div>
		<div class="glow glow-c"></div>
	</div>

	<DashboardHeader name={session.user?.name ?? ''} />

	<main class="relative z-10 px-6 py-16 md:px-10">
		<div class="mx-auto max-w-6xl">
			<div class="intro" class:in={mounted}>
				<h1 class="font-display text-4xl leading-[1.05] md:text-5xl">
					Welcome,
					<span class="name-grad">{session.user?.name ?? 'there'}</span>.
				</h1>

				<p class="mt-4 max-w-xl font-body text-[15px] leading-relaxed">
					Diagnose, design, assess: pick your next move.
				</p>
			</div>

			<div class="mt-12 grid gap-6 lg:grid-cols-3">
				{#each modules as mod, i (mod.id)}
					<article
						class="card group"
						class:in={mounted}
						class:unavailable={!mod.available}
						style="--accent: {mod.accent}; --delay: {i * 90}ms;"
						onpointermove={handlePointer}
					>
						<span class="card-spotlight" aria-hidden="true"></span>
						<span class="card-topline" aria-hidden="true"></span>

						<div class="relative z-10 flex w-full flex-col items-start gap-4">
							<div class="icon-wrap">
								{#if mod.icon === 'diagnose'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 24 24"
										fill="none"
										stroke={mod.accent}
										stroke-width="1.75"
										class="h-6 w-6"
									>
										<circle cx="12" cy="12" r="7.5" />
										<path d="M12 4.5v15M4.5 12h15" />
										<circle cx="12" cy="12" r="1.75" fill={mod.accent} stroke="none" />
									</svg>
								{:else if mod.icon === 'design'}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 24 24"
										fill="none"
										stroke={mod.accent}
										stroke-width="1.75"
										class="h-6 w-6"
									>
										<path d="M4 19.5V16l9-9 3.5 3.5-9 9H4z" stroke-linejoin="round" />
										<path d="M13 7l3.5 3.5" />
										<path d="M17.5 4.5 19.5 6.5" stroke-linecap="round" />
									</svg>
								{:else}
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 24 24"
										fill="none"
										stroke={mod.accent}
										stroke-width="1.75"
										class="h-6 w-6"
									>
										<path d="M4 19h16" stroke-linecap="round" />
										<path d="M7 19v-5M12 19V8M17 19v-9" stroke-linecap="round" />
									</svg>
								{/if}
							</div>

							<h2 class="card-title m-0 font-display text-xl">{mod.title}</h2>

							<p class="card-desc m-0 flex-1 font-body text-[13.5px] leading-relaxed">
								{mod.description}
							</p>

							{#if mod.available}
								<button
									type="button"
									class="cta mt-1 font-mono text-[12px] {mod.accentClass}"
									onclick={() => openModule(mod)}
								>
									Open the tool
									<svg
										xmlns="http://www.w3.org/2000/svg"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="2"
										class="arrow h-3.5 w-3.5"
									>
										<path
											d="M5 12h14M13 6l6 6-6 6"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								</button>
							{:else}
								<span class="cta mt-1 font-mono text-[12px] opacity-60 {mod.accentClass}">
									Coming soon
								</span>
							{/if}
						</div>
					</article>
				{/each}
			</div>
		</div>
	</main>
</div>

<style>
	.page {
		background: linear-gradient(180deg, #f7f9fb 0%, #eef2f6 100%);
		color: #24303a;
	}

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
		background: radial-gradient(circle, rgba(27, 117, 224, 0.22), transparent 70%);
	}
	.glow-b {
		bottom: -12%;
		right: -8%;
		width: 46vw;
		height: 46vw;
		background: radial-gradient(circle, rgba(24, 109, 19, 0.16), transparent 70%);
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
		0%,
		100% {
			transform: translate(0, 0) scale(1);
		}
		50% {
			transform: translate(3%, 4%) scale(1.08);
		}
	}

	.intro {
		opacity: 0;
		transform: translateY(14px);
		transition:
			opacity 0.7s ease,
			transform 0.7s cubic-bezier(0.2, 0.8, 0.2, 1);
	}
	.intro.in {
		opacity: 1;
		transform: none;
	}
	.intro h1 {
		color: #16212b;
		user-select: text;
	}
	.intro p {
		color: #56646f;
		user-select: text;
	}

	.name-grad {
		background: linear-gradient(100deg, #1b75e0, #3969a7 60%, #7c5ce6);
		-webkit-background-clip: text;
		background-clip: text;
		color: transparent;
		background-size: 200% auto;
		animation: shimmer 6s ease-in-out infinite;
	}
	@keyframes shimmer {
		0%,
		100% {
			background-position: 0% center;
		}
		50% {
			background-position: 100% center;
		}
	}

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
		backdrop-filter: blur(6px);
		box-shadow:
			0 1px 0 rgba(255, 255, 255, 0.8) inset,
			0 12px 28px -20px rgba(20, 40, 60, 0.35);
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
		transform: translateY(-4px);
		border-color: color-mix(in srgb, var(--accent) 45%, transparent);
		box-shadow:
			0 1px 0 rgba(255, 255, 255, 0.9) inset,
			0 24px 44px -22px color-mix(in srgb, var(--accent) 50%, transparent);
	}
	.card.unavailable {
		opacity: 0.92;
	}

	.card-spotlight {
		position: absolute;
		inset: 0;
		z-index: 0;
		opacity: 0;
		pointer-events: none;
		transition: opacity 0.3s ease;
		background: radial-gradient(
			320px circle at var(--mx, 50%) var(--my, 0%),
			color-mix(in srgb, var(--accent) 14%, transparent),
			transparent 60%
		);
	}
	.card:hover .card-spotlight {
		opacity: 1;
	}

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
	.card:hover .card-topline {
		transform: scaleX(1);
	}

	.card-title {
		color: #1a2530;
		user-select: text;
	}
	.card-desc {
		color: #56646f;
		user-select: text;
	}

	.icon-wrap {
		display: flex;
		height: 3rem;
		width: 3rem;
		align-items: center;
		justify-content: center;
		border-radius: 14px;
		border: 1px solid rgba(20, 40, 60, 0.06);
		background: color-mix(in srgb, var(--accent) 12%, white);
		transition:
			transform 0.35s cubic-bezier(0.2, 0.8, 0.2, 1),
			box-shadow 0.35s ease;
	}
	.card:hover .icon-wrap {
		transform: scale(1.06) rotate(-3deg);
		box-shadow: 0 10px 24px -12px color-mix(in srgb, var(--accent) 60%, transparent);
	}

	.cta {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		border: 0;
		background: none;
		padding: 0;
		cursor: pointer;
		color: color-mix(in srgb, var(--accent) 80%, black);
	}
	.cta .arrow {
		transition: transform 0.3s ease;
	}
	.card:hover .cta .arrow {
		transform: translateX(4px);
	}
	.cta:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
		border-radius: 4px;
	}

	@media (prefers-reduced-motion: reduce) {
		.glow,
		.name-grad {
			animation: none;
		}
		.card,
		.intro {
			transition: none;
			opacity: 1;
			transform: none;
		}
	}
</style>
