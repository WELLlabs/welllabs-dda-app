<script>
	import { base } from '$app/paths';
</script>

<footer class="relative border-t border-hairline bg-transparent px-6 py-12 md:px-10">
	<div class="mx-auto flex max-w-6xl flex-col items-center gap-8">
		<div class="flex flex-col items-center gap-3 text-center">
			<p class="m-0 max-w-xl font-body text-[13px] leading-relaxed text-ink-dim sm:text-[14px]">
				Built by WELL Labs with the support of Environmental Defense Fund
			</p>
			<div class="flex flex-wrap items-center justify-center gap-8 sm:gap-12">
				<a
					href="https://welllabs.org/"
					target="_blank"
					rel="noopener noreferrer"
					class="opacity-90 transition-opacity hover:opacity-100"
					aria-label="WELL Labs"
				>
					<img
						src="{base}/logos/well-labs-logo.png"
						alt="WELL Labs"
						class="h-10 w-auto object-contain sm:h-12"
					/>
				</a>
				<a
					href="https://www.edf.org/"
					target="_blank"
					rel="noopener noreferrer"
					class="opacity-90 transition-opacity hover:opacity-100"
					aria-label="Environmental Defense Fund"
				>
					<img
						src="{base}/logos/edf-logo.svg"
						alt="Environmental Defense Fund"
						class="h-9 w-auto object-contain sm:h-11"
					/>
				</a>
			</div>
		</div>

		<span class="font-mono text-[11px] text-ink-faint"
			>Water Security Toolbox · Diagnose, Design &amp; Assess</span
		>
	</div>
</footer>
