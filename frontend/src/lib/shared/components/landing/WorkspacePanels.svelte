<script lang="ts">
	import { animate } from 'motion';
	import { workspaces, type WorkspaceKey } from '$lib/data/mock';

	let panelEls: Partial<Record<WorkspaceKey, HTMLElement>> = {};
	let overlayEl: HTMLDivElement;
	let expandedKey: WorkspaceKey | null = null;
	let animating = false;
	let originRect: { top: number; left: number; width: number; height: number } | null = null;

	const easing = [0.16, 1, 0.3, 1] as const;

	function openPanel(key: WorkspaceKey) {
		if (animating) return;
		const el = panelEls[key];
		if (!el) return;
		const rect = el.getBoundingClientRect();
		originRect = { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
		expandedKey = key;
		animating = true;

		requestAnimationFrame(() => {
			if (!overlayEl || !originRect) return;
			Object.assign(overlayEl.style, {
				top: originRect.top + 'px',
				left: originRect.left + 'px',
				width: originRect.width + 'px',
				height: originRect.height + 'px',
				borderRadius: '20px'
			});
			overlayEl.getBoundingClientRect();
			const anim = animate(
				overlayEl,
				{
					top: '0px',
					left: '0px',
					width: window.innerWidth + 'px',
					height: window.innerHeight + 'px',
					borderRadius: '0px'
				},
				{ duration: 0.65, easing }
			);
			anim.finished.then(() => (animating = false));
		});
	}

	function closePanel() {
		if (animating || !overlayEl || !originRect) return;
		animating = true;
		const anim = animate(
			overlayEl,
			{
				top: originRect.top + 'px',
				left: originRect.left + 'px',
				width: originRect.width + 'px',
				height: originRect.height + 'px',
				borderRadius: '20px'
			},
			{ duration: 0.5, easing }
		);
		anim.finished.then(() => {
			animating = false;
			expandedKey = null;
			originRect = null;
		});
	}

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && expandedKey) closePanel();
	}

	const activeWorkspace = () => workspaces.find((w) => w.key === expandedKey)!;
</script>

<svelte:window on:keydown={onKeydown} />

<section id="workspaces" class="relative bg-transparent px-6 py-28 md:px-10">
	<div class="mx-auto max-w-6xl">
		<div class="mb-14 flex flex-col gap-2">
			<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">Three tools, one field</span>
			<h2 class="font-display text-3xl text-ink md:text-4xl">Enter a workspace.</h2>
		</div>

		<div class="grid gap-5 md:grid-cols-3">
			<!-- Diagnose -->
			<button
				bind:this={panelEls.diagnose}
				on:click={() => openPanel('diagnose')}
				class="group relative flex h-[420px] flex-col justify-between overflow-hidden rounded-[20px] border border-hairline bg-panel p-6 text-left shadow-glass transition-all duration-500 hover:-translate-y-1 hover:border-diagnose/40"
				style="visibility:{expandedKey === 'diagnose' ? 'hidden' : 'visible'}"
			>
				<div class="absolute inset-0 opacity-60 transition-opacity duration-500 group-hover:opacity-100">
					<svg viewBox="0 0 400 300" class="h-full w-full" preserveAspectRatio="xMidYMid slice">
						<defs>
							<pattern id="mesh-d" width="20" height="20" patternUnits="userSpaceOnUse">
								<path d="M20 0 L0 0 0 20" fill="none" stroke="#e1e7ef" stroke-width="0.5" />
							</pattern>
						</defs>
						<rect width="400" height="300" fill="url(#mesh-d)" />
						<line x1="0" y1="90" x2="400" y2="90" stroke="#0d983b" stroke-width="1" opacity="0.7">
							<animate attributeName="y1" values="20;280;20" dur="5s" repeatCount="indefinite" />
							<animate attributeName="y2" values="20;280;20" dur="5s" repeatCount="indefinite" />
						</line>
						<circle cx="140" cy="150" r="4" fill="#0d983b" opacity="0.9">
							<animate attributeName="r" values="3;7;3" dur="2.4s" repeatCount="indefinite" />
						</circle>
						<circle cx="260" cy="190" r="3" fill="#0d983b" opacity="0.6" />
					</svg>
				</div>
				<div class="relative z-10 flex items-center justify-between font-mono text-[11px] text-diagnose">
					<span>DIAGNOSE</span>
					<span class="opacity-70">01</span>
				</div>
				<div class="relative z-10">
					<h3 class="font-display text-2xl text-ink">Reads the watershed</h3>
					<p class="mt-2 max-w-[26ch] font-body text-[13px] leading-relaxed text-ink-dim">
						Live sensor and imagery overlays surface blockages and flow anomalies as they happen.
					</p>
					<span class="mt-4 inline-flex items-center gap-1.5 font-mono text-[11px] text-diagnose opacity-0 transition-opacity duration-300 group-hover:opacity-100">
						Enter workspace →
					</span>
				</div>
			</button>

			<!-- Design -->
			<button
				bind:this={panelEls.design}
				on:click={() => openPanel('design')}
				class="group relative flex h-[420px] flex-col justify-between overflow-hidden rounded-[20px] border border-hairline bg-panel p-6 text-left shadow-glass transition-all duration-500 hover:-translate-y-1 hover:border-design/40"
				style="visibility:{expandedKey === 'design' ? 'hidden' : 'visible'}"
			>
				<div class="absolute inset-0 opacity-60 transition-opacity duration-500 group-hover:opacity-100">
					<svg viewBox="0 0 400 300" class="h-full w-full" preserveAspectRatio="xMidYMid slice">
						<path d="M60 220 L150 90 L250 150 L340 60" fill="none" stroke="#d5b443" stroke-width="1.2" opacity="0.85" stroke-dasharray="5 5" />
						{#each [[60, 220], [150, 90], [250, 150], [340, 60]] as [x, y]}
							<circle cx={x} cy={y} r="4" fill="#ffffff" stroke="#d5b443" stroke-width="1.4" />
						{/each}
						<rect x="130" y="70" width="40" height="40" fill="none" stroke="#d5b443" stroke-width="0.7" opacity="0.5" class="group-hover:animate-pulse-soft" />
					</svg>
				</div>
				<div class="relative z-10 flex items-center justify-between font-mono text-[11px] text-design">
					<span>DESIGN</span>
					<span class="opacity-70">02</span>
				</div>
				<div class="relative z-10">
					<h3 class="font-display text-2xl text-ink">Plans the intervention</h3>
					<p class="mt-2 max-w-[26ch] font-body text-[13px] leading-relaxed text-ink-dim">
						Draft channel and structure geometry directly on terrain with survey-grade precision.
					</p>
					<span class="mt-4 inline-flex items-center gap-1.5 font-mono text-[11px] text-design opacity-0 transition-opacity duration-300 group-hover:opacity-100">
						Enter workspace →
					</span>
				</div>
			</button>

			<!-- Assess -->
			<button
				bind:this={panelEls.assess}
				on:click={() => openPanel('assess')}
				class="group relative flex h-[420px] flex-col justify-between overflow-hidden rounded-[20px] border border-hairline bg-panel p-6 text-left shadow-glass transition-all duration-500 hover:-translate-y-1 hover:border-assess/40"
				style="visibility:{expandedKey === 'assess' ? 'hidden' : 'visible'}"
			>
				<div class="absolute inset-0 opacity-60 transition-opacity duration-500 group-hover:opacity-100">
					<svg viewBox="0 0 400 300" class="h-full w-full" preserveAspectRatio="xMidYMid slice">
						<circle cx="200" cy="150" r="90" fill="none" stroke="#e1e7ef" stroke-width="1" />
						<circle cx="200" cy="150" r="60" fill="none" stroke="#e1e7ef" stroke-width="1" />
						<circle cx="200" cy="150" r="30" fill="none" stroke="#e1e7ef" stroke-width="1" />
						<line x1="200" y1="150" x2="200" y2="60" stroke="#3969a7" stroke-width="1.4" opacity="0.9">
							<animateTransform attributeName="transform" type="rotate" from="0 200 150" to="360 200 150" dur="7s" repeatCount="indefinite" />
						</line>
						<circle cx="200" cy="150" r="3" fill="#3969a7" />
					</svg>
				</div>
				<div class="relative z-10 flex items-center justify-between font-mono text-[11px] text-assess">
					<span>ASSESS</span>
					<span class="opacity-70">03</span>
				</div>
				<div class="relative z-10">
					<h3 class="font-display text-2xl text-ink">Scores the risk</h3>
					<p class="mt-2 max-w-[26ch] font-body text-[13px] leading-relaxed text-ink-dim">
						Every design is scored against flood, cost, and compliance models before ground breaks.
					</p>
					<span class="mt-4 inline-flex items-center gap-1.5 font-mono text-[11px] text-assess opacity-0 transition-opacity duration-300 group-hover:opacity-100">
						Enter workspace →
					</span>
				</div>
			</button>
		</div>
	</div>
</section>

{#if expandedKey}
	<div
		bind:this={overlayEl}
		class="fixed z-[100] overflow-hidden bg-panel shadow-glass-lg"
		style="top:0; left:0; width:100vw; height:100vh;"
	>
		<div class="relative flex h-full w-full flex-col bg-void">
			<div class="absolute inset-0 opacity-40">
				<svg viewBox="0 0 1000 700" class="h-full w-full" preserveAspectRatio="xMidYMid slice">
					<defs>
						<pattern id="mesh-full" width="34" height="34" patternUnits="userSpaceOnUse">
							<path d="M34 0 L0 0 0 34" fill="none" stroke="#e1e7ef" stroke-width="0.6" />
						</pattern>
					</defs>
					<rect width="1000" height="700" fill="url(#mesh-full)" />
				</svg>
			</div>

			<div class="relative z-10 flex items-center justify-between border-b border-hairline px-8 py-5">
				<div class="flex items-center gap-3 font-mono text-[11px] uppercase tracking-[0.2em]" style="color:{activeWorkspace().accentHex}">
					<span class="h-1.5 w-1.5 rounded-full bg-current"></span>
					{activeWorkspace().label} workspace
				</div>
				<button
					on:click={closePanel}
					class="rounded-full border border-hairline px-4 py-1.5 font-mono text-[11px] text-ink-dim transition-colors hover:border-ink-dim hover:text-ink"
				>
					Close  Esc
				</button>
			</div>

			<div class="relative z-10 flex flex-1 items-center px-8 py-10 md:px-16">
				<div class="grid w-full items-center gap-12 md:grid-cols-2">
					<div>
						<span class="font-mono text-[11px] text-ink-faint">{activeWorkspace().verb}</span>
						<h3 class="mt-3 font-display text-4xl leading-tight text-ink md:text-5xl">{activeWorkspace().label}</h3>
						<p class="mt-5 max-w-md font-body text-[15px] leading-relaxed text-ink-dim">
							{activeWorkspace().description}
						</p>
						<div class="mt-8 flex flex-wrap gap-3">
							<span class="rounded-full border border-hairline bg-panel-raised px-3 py-1.5 font-mono text-[11px] text-ink-dim">Live data</span>
							<span class="rounded-full border border-hairline bg-panel-raised px-3 py-1.5 font-mono text-[11px] text-ink-dim">Field synced</span>
							<span class="rounded-full border border-hairline bg-panel-raised px-3 py-1.5 font-mono text-[11px] text-ink-dim">Multi-basin</span>
						</div>
					</div>

					<div class="relative aspect-[4/3] w-full overflow-hidden rounded-2xl border border-hairline bg-panel-raised shadow-glass">
						<div class="absolute left-4 top-4 flex gap-1.5">
							<span class="h-2 w-2 rounded-full bg-ink-faint/40"></span>
							<span class="h-2 w-2 rounded-full bg-ink-faint/40"></span>
							<span class="h-2 w-2 rounded-full bg-ink-faint/40"></span>
						</div>
						<svg viewBox="0 0 400 300" class="h-full w-full opacity-80">
							<circle cx="200" cy="150" r="120" fill="none" stroke={activeWorkspace().accentHex} stroke-width="0.6" opacity="0.3" />
							<circle cx="200" cy="150" r="80" fill="none" stroke={activeWorkspace().accentHex} stroke-width="0.6" opacity="0.4" />
							<circle cx="200" cy="150" r="40" fill="none" stroke={activeWorkspace().accentHex} stroke-width="0.6" opacity="0.5" />
							<circle cx="200" cy="150" r="4" fill={activeWorkspace().accentHex}>
								<animate attributeName="r" values="4;9;4" dur="2.6s" repeatCount="indefinite" />
							</circle>
						</svg>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}
 