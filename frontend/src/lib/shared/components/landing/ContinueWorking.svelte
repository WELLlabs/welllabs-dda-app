<script lang="ts">
	import { recentItems, quickActions } from '$lib/data/mock';
</script>

<section id="continue" class="relative bg-void px-6 py-20 md:px-10">
	<div class="mx-auto max-w-6xl">
		<div class="mb-10 flex items-end justify-between">
			<div>
				<span class="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-faint">Where you left off</span>
				<h2 class="mt-2 font-display text-3xl text-ink md:text-4xl">Continue working.</h2>
			</div>
		</div>

		<div class="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
			<!-- Recent items -->
			<div class="rounded-[20px] border border-hairline bg-panel shadow-glass">
				<div class="flex items-center justify-between border-b border-hairline px-6 py-4">
					<span class="font-body text-[13px] text-ink-dim">Recent projects &amp; surveys</span>
					<span class="font-mono text-[11px] text-ink-faint">{recentItems.length} items</span>
				</div>
				<ul>
					{#each recentItems as item, i}
						<li
							class="group flex items-center justify-between gap-4 px-6 py-4 transition-colors hover:bg-panel-raised"
							class:border-b={i < recentItems.length - 1}
							class:border-hairline={i < recentItems.length - 1}
						>
							<div class="flex items-center gap-4">
								<span
									class="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-hairline font-mono text-[10px] uppercase text-ink-faint"
								>
									{item.kind === 'project' ? 'PR' : 'SV'}
								</span>
								<div>
									<p class="font-body text-[14px] text-ink">{item.title}</p>
									<p class="font-mono text-[11px] text-ink-faint">{item.sub}</p>
								</div>
							</div>

							<div class="flex items-center gap-4">
								<div class="hidden w-28 items-center gap-2 sm:flex">
									<div class="h-1 flex-1 overflow-hidden rounded-full bg-hairline">
										<div class="h-full rounded-full bg-diagnose" style="width:{item.progress}%"></div>
									</div>
									<span class="font-mono text-[10px] text-ink-faint">{item.progress}%</span>
								</div>
								<span class="font-mono text-[11px] text-ink-faint">{item.updated}</span>
							</div>
						</li>
					{/each}
				</ul>
			</div>

			<!-- Quick actions -->
			<div class="rounded-[20px] border border-hairline bg-panel shadow-glass">
				<div class="border-b border-hairline px-6 py-4">
					<span class="font-body text-[13px] text-ink-dim">Quick actions</span>
				</div>
				<div class="grid grid-cols-1 gap-px bg-hairline">
					{#each quickActions as action}
						<button class="group flex items-center justify-between bg-panel px-6 py-4 text-left transition-colors hover:bg-panel-raised">
							<span class="font-body text-[14px] text-ink">{action.label}</span>
							<span class="font-mono text-[10px] uppercase tracking-wide text-ink-faint transition-colors group-hover:text-diagnose">
								{action.hint}
							</span>
						</button>
					{/each}
				</div>
			</div>
		</div>
	</div>
</section>
