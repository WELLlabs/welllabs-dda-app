<script>
	/** @type {{ logframe: any, compact?: boolean, projectName?: string, planName?: string }} */
	let { logframe, compact = false, projectName = '', planName = '' } = $props();

	const hasType = $derived(Boolean(logframe?.has_outcome_type));
	const outcomes = $derived(logframe?.outcomes || []);
	const methodology = $derived(logframe?.methodology || []);
	const interventionLabel = $derived(logframe?.name || '');

	const SECTION_HEADS = new Set([
		'frequency',
		'sampling',
		'field setup for data collections',
		'what do you do with the mel plan?',
		'what do you do with the mel plan'
	]);

	const STEP_PREFIXES = [
		'Select control assets:',
		'Asset allocation:',
		'Deploy Instruments:',
		'Train community'
	];

	const BULLET_PREFIXES = [
		'For watershed management programmes',
		'Within each watershed',
		'Zones that are distinct'
	];

	/** @param {string} para */
	function normHead(para) {
		return String(para || '')
			.trim()
			.replace(/\.$/, '')
			.toLowerCase();
	}

	/** @param {string} para */
	function isSectionHead(para) {
		return SECTION_HEADS.has(normHead(para));
	}

	/** @param {string} para */
	function isStepLine(para) {
		const text = String(para || '');
		return STEP_PREFIXES.some((p) => text.startsWith(p));
	}

	/** @param {string} para */
	function isBulletLine(para) {
		const text = String(para || '');
		return BULLET_PREFIXES.some((p) => text.startsWith(p));
	}

	/** Split "Title: body" so only the title is bold. */
	function splitStep(para) {
		const text = String(para || '');
		const idx = text.indexOf(':');
		if (idx < 0) return { title: text, body: '' };
		return {
			title: text.slice(0, idx + 1),
			body: text.slice(idx + 1)
		};
	}

	/** @param {string} text */
	function assumptionItems(text) {
		const raw = String(text || '').trim();
		if (!raw) return [];
		const parts = raw
			.split(/\n(?=\s*\d+[\.\)]\s)/)
			.map((p) => p.trim())
			.filter(Boolean);
		if (parts.length > 1) return parts;
		const inline = raw.split(/(?=\b\d+[\.\)]\s)/).map((p) => p.trim()).filter(Boolean);
		if (inline.length > 1) return inline;
		return [raw];
	}

	/** @param {{ playbooks?: string, playbook_links?: { label: string, url: string }[] }} row */
	function playbookLinks(row) {
		if (Array.isArray(row?.playbook_links) && row.playbook_links.length) {
			return row.playbook_links;
		}
		return [];
	}

	const outroParts = $derived.by(() => {
		const items = /** @type {string[]} */ (logframe?.outro || []);
		const freqIdx = items.findIndex((p) => normHead(p) === 'frequency');
		const afterFreq = items.findIndex(
			(p, i) =>
				i > (freqIdx >= 0 ? freqIdx : -1) &&
				(normHead(p).startsWith('what do you do') || normHead(p) === 'sampling')
		);
		if (freqIdx >= 0 && afterFreq > freqIdx) {
			return {
				frequency: items.slice(freqIdx, afterFreq),
				field: items.slice(afterFreq)
			};
		}
		if (freqIdx === 0) {
			return { frequency: items.slice(0, 2), field: items.slice(2) };
		}
		return { frequency: [], field: items };
	});

	/**
	 * @param {string[]} paras
	 */
	function renderBlocks(paras) {
		/** @type {{ type: string, text?: string, items?: string[] }[]} */
		const blocks = [];
		let i = 0;
		while (i < paras.length) {
			const para = paras[i];
			if (isSectionHead(para)) {
				blocks.push({ type: 'h3', text: String(para).replace(/\.$/, '') });
				i += 1;
				continue;
			}
			if (isBulletLine(para)) {
				/** @type {string[]} */
				const items = [];
				while (i < paras.length && isBulletLine(paras[i])) {
					items.push(paras[i]);
					i += 1;
				}
				blocks.push({ type: 'ol', items });
				continue;
			}
			if (isStepLine(para)) {
				/** @type {string[]} */
				const items = [];
				while (i < paras.length && isStepLine(paras[i])) {
					items.push(paras[i]);
					i += 1;
				}
				blocks.push({ type: 'steps', items });
				continue;
			}
			blocks.push({ type: 'p', text: para });
			i += 1;
		}
		return blocks;
	}

	const frequencyBlocks = $derived(renderBlocks(outroParts.frequency));
	const fieldBlocks = $derived(renderBlocks(outroParts.field));

	const sections = $derived.by(() => {
		/** @type {{ id: string, label: string }[]} */
		const list = [
			{ id: 'overview', label: 'Overview' },
			{ id: 'logframe', label: 'Log frame' },
			{ id: 'methodology', label: 'Methodology' }
		];
		if (frequencyBlocks.length) list.push({ id: 'frequency', label: 'Frequency' });
		list.push({ id: 'field', label: 'Field setup' });
		return list;
	});

	/** @param {string} id */
	function sectionNum(id) {
		const idx = sections.findIndex((s) => s.id === id);
		return String(Math.max(idx, 0) + 1).padStart(2, '0');
	}

	/** In-page jump — avoid href="#id" (resolves to /wst/#id via <base>). */
	/** @param {MouseEvent} e @param {string} id */
	function jumpToSection(e, id) {
		e.preventDefault();
		document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}
</script>

{#if logframe}
	<article class="doc" class:compact>
		<aside class="doc-contents" aria-label="Contents">
			<p class="contents-label">Contents</p>
			<nav class="doc-nav">
				{#each sections as s, i}
					<a
						href="#{s.id}"
						class="doc-nav-link"
						onclick={(e) => jumpToSection(e, s.id)}
					>
						<span class="doc-nav-num">{String(i + 1).padStart(2, '0')}</span>
						{s.label}
					</a>
				{/each}
			</nav>
		</aside>

		<div class="doc-page">
			<header class="doc-hero">
				<p class="doc-eyebrow">Assess · MEL Plan</p>
				<h1 class="doc-title">Intervention MEL plans</h1>
				<div class="doc-meta">
					{#if planName}
						<p><span>Plan</span> {planName}</p>
					{/if}
					{#if projectName}
						<p><span>Project</span> {projectName}</p>
					{/if}
					{#if interventionLabel}
						<p><span>Intervention</span> {interventionLabel}</p>
					{/if}
				</div>
			</header>

			<section id="overview" class="doc-section">
				<h2 class="doc-h2"><span>{sectionNum('overview')}</span> Overview</h2>
				<div class="doc-prose">
					{#each logframe.intro || [] as para}
						<p>{para}</p>
					{/each}
				</div>
			</section>

			<section id="logframe" class="doc-section">
				<h2 class="doc-h2"><span>{sectionNum('logframe')}</span> Log frame</h2>
				<p class="doc-lead">
					Goal → outcome → output pathway with indicators and assumptions for the selected results
					chain.
				</p>
				<div class="table-wrap">
					<table class="frame-table">
						<thead>
							<tr>
								{#if hasType}<th>Outcome type</th>{/if}
								<th>Results Chain</th>
								<th>Indicators</th>
								<th>Assumptions</th>
							</tr>
						</thead>
						<tbody>
							{#each outcomes as row, i (i)}
								<tr
									class:goal={row.kind === 'goal'}
									class:output={row.kind === 'output'}
									class:cta={row.cta || row.kind === 'goal'}
								>
									{#if hasType}
										<td class="type-cell">{row.outcome_type || ''}</td>
									{/if}
									<td>
										{#if row.label}
											<span
												class="chain-label"
												class:cta-label={row.cta || row.kind === 'goal'}
												>{row.label}</span
											>
										{/if}
										<span
											class="chain-title"
											class:cta-prompt={row.cta || row.kind === 'goal'}
											class:cta-goal={row.kind === 'goal'}
											class:cta-output={row.kind === 'output' && row.cta}>{row.title}</span
										>
									</td>
									<td>
										{#if row.indicators?.length}
											<ol class="cell-list">
												{#each row.indicators as ind}
													<li>{ind}</li>
												{/each}
											</ol>
										{/if}
									</td>
									<td>
										{#if assumptionItems(row.assumptions).length}
											<ol class="cell-list assumptions-list">
												{#each assumptionItems(row.assumptions) as item}
													<li>{item.replace(/^\d+[\.\)]\s*/, '')}</li>
												{/each}
											</ol>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
				{#if logframe.note}
					<aside class="doc-note" role="note">
						<span class="doc-note-label">Note</span>
						<p>{logframe.note.replace(/^Please note:\s*/i, '')}</p>
					</aside>
				{/if}
			</section>

			<section id="methodology" class="doc-section">
				<h2 class="doc-h2"><span>{sectionNum('methodology')}</span> Methodology</h2>
				<p class="doc-lead">
					{logframe.methodology_heading || 'Data and methodology for indicators'}
				</p>
				<div class="table-wrap">
					<table class="method-table">
						<thead>
							<tr>
								<th>Indicator</th>
								<th>Type of monitoring</th>
								<th>Data</th>
								<th>Method/Instrumentation</th>
								<th>Frequency of monitoring</th>
								<th>Playbooks</th>
							</tr>
						</thead>
						<tbody>
							{#each methodology as row, i (i)}
								<tr>
									<td class="ind-name">{row.indicator}</td>
									<td>{row.monitoring_type}</td>
									<td class="pre">{row.data}</td>
									<td class="pre">{row.method}</td>
									<td>{row.frequency}</td>
									<td class="playbooks">
										{#if playbookLinks(row).length}
											{#each playbookLinks(row) as link, li (link.url + li)}
												<a
													class="playbook-link"
													href={link.url}
													target="_blank"
													rel="noopener noreferrer">{link.label}</a
												>
											{/each}
										{:else if row.playbooks}
											<span class="pre">{row.playbooks}</span>
										{:else}
											<span class="muted">—</span>
										{/if}
									</td>
								</tr>
							{/each}
							{#if !methodology.length}
								<tr>
									<td colspan="6" class="empty">No methodology rows for the selected indicators.</td>
								</tr>
							{/if}
						</tbody>
					</table>
				</div>
			</section>

			{#if frequencyBlocks.length}
				<section id="frequency" class="doc-section">
					<h2 class="doc-h2"><span>{sectionNum('frequency')}</span> Frequency</h2>
					<div class="doc-prose">
						{#each frequencyBlocks as block}
							{#if block.type === 'p'}
								<p>{block.text}</p>
							{/if}
						{/each}
					</div>
				</section>
			{/if}

			<section id="field" class="doc-section">
				<h2 class="doc-h2"><span>{sectionNum('field')}</span> Field setup</h2>
				<div class="doc-prose">
					{#each fieldBlocks as block}
						{#if block.type === 'h3'}
							<h3 class="doc-h3">{block.text}</h3>
						{:else if block.type === 'ol'}
							<ol class="doc-list">
								{#each block.items || [] as item}
									<li>{item}</li>
								{/each}
							</ol>
						{:else if block.type === 'steps'}
							<ol class="doc-steps">
								{#each block.items || [] as item}
									{@const step = splitStep(item)}
									<li>
										<strong>{step.title}</strong><span>{step.body}</span>
									</li>
								{/each}
							</ol>
						{:else}
							<p>{block.text}</p>
						{/if}
					{/each}
				</div>
			</section>
		</div>
	</article>
{/if}

<style>
	.doc {
		display: grid;
		grid-template-columns: 14.5rem minmax(0, 58rem);
		gap: 2rem;
		align-items: start;
		width: fit-content;
		max-width: 100%;
		margin-inline: auto;
		color: #1a2530;
	}
	.doc-contents {
		position: sticky;
		top: 0.5rem;
		padding: 0.35rem 0.15rem 1rem;
	}
	.contents-label {
		margin: 0 0 0.85rem;
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: #8a96a1;
	}
	.doc-nav {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.doc-nav-link {
		display: flex;
		align-items: baseline;
		gap: 0.55rem;
		font-size: 0.95rem;
		font-weight: 600;
		line-height: 1.35;
		color: #56646f;
		text-decoration: none;
		padding: 0.5rem 0.55rem;
		border-radius: 0.35rem;
		border-left: 2px solid transparent;
	}
	.doc-nav-link:hover {
		color: #0d2c4c;
		background: rgba(27, 117, 224, 0.07);
		border-left-color: #1b75e0;
	}
	.doc-nav-num {
		flex-shrink: 0;
		font-variant-numeric: tabular-nums;
		font-size: 0.75rem;
		letter-spacing: 0.04em;
		color: #1b75e0;
	}
	.doc-page {
		width: 100%;
		min-width: 0;
		padding: 0 0 2.75rem;
		background: #fff;
		border: 1px solid rgba(13, 44, 76, 0.1);
		border-radius: 0.4rem;
		box-shadow: 0 1px 3px rgba(13, 44, 76, 0.05);
		overflow: hidden;
	}
	@media (max-width: 900px) {
		.doc {
			grid-template-columns: 1fr;
			width: 100%;
		}
		.doc-contents {
			position: static;
			padding: 0 0 0.5rem;
			border-bottom: 1px solid rgba(13, 44, 76, 0.1);
		}
		.doc-nav {
			flex-direction: row;
			flex-wrap: wrap;
			gap: 0.25rem 0.5rem;
		}
	}
	.doc-hero {
		margin: 0 0 0.25rem;
		padding: 1.35rem 1.75rem 1.25rem;
		background: linear-gradient(180deg, #eef6ff 0%, #f7fbff 70%, #ffffff 100%);
		border-bottom: 2.5px solid #1b75e0;
	}
	.doc-eyebrow {
		margin: 0 0 0.4rem;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: #1b75e0;
	}
	.doc-title {
		margin: 0;
		font-family: var(--font-headline, ui-sans-serif, system-ui, sans-serif);
		font-size: clamp(1.5rem, 2.4vw, 2rem);
		font-weight: 700;
		line-height: 1.2;
		letter-spacing: -0.01em;
		color: #0d2c4c;
	}
	.doc-meta {
		display: flex;
		flex-direction: column;
		gap: 0.2rem;
		margin: 0.85rem 0 0;
	}
	.doc-meta p {
		margin: 0;
		font-size: 0.88rem;
		line-height: 1.4;
		color: #3b4a58;
	}
	.doc-meta span {
		display: inline-block;
		min-width: 5.5rem;
		margin-right: 0.35rem;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #8a96a1;
	}
	.doc-note {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.65rem 0.85rem;
		align-items: start;
		margin: 1rem 0 0;
		padding: 0.8rem 0.95rem;
		border-radius: 0.35rem;
		border: 1px solid rgba(180, 83, 9, 0.25);
		background: #fff8ef;
	}
	.doc-note-label {
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: #b45309;
		padding-top: 0.12rem;
	}
	.doc-note p {
		margin: 0;
		font-size: 0.875rem;
		line-height: 1.55;
		color: #5c4630;
	}
	.doc-section {
		padding: 1.65rem 1.75rem;
		border-bottom: 1px solid rgba(13, 44, 76, 0.08);
	}
	.doc-section:last-child {
		border-bottom: none;
		padding-bottom: 0.25rem;
	}
	.doc-h2 {
		display: flex;
		align-items: baseline;
		gap: 0.65rem;
		margin: 0 0 0.7rem;
		font-family: var(--font-headline, ui-sans-serif, system-ui, sans-serif);
		font-size: 1.15rem;
		font-weight: 700;
		color: #0d2c4c;
	}
	.doc-h2 span {
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.08em;
		color: #1b75e0;
	}
	.doc-h3 {
		margin: 1.4rem 0 0.55rem;
		padding-bottom: 0.35rem;
		font-size: 1rem;
		font-weight: 700;
		color: #0d2c4c;
		border-bottom: 1px solid rgba(27, 117, 224, 0.2);
	}
	.doc-h3:first-child {
		margin-top: 0.1rem;
	}
	.doc-lead {
		margin: 0 0 0.95rem;
		font-size: 0.875rem;
		line-height: 1.55;
		color: #56646f;
	}
	.doc-prose {
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
	}
	.doc-prose p {
		margin: 0;
		font-size: 0.95rem;
		line-height: 1.7;
		color: #3b4a58;
	}
	.doc-list,
	.doc-steps,
	.cell-list {
		margin: 0.15rem 0 0.35rem;
		padding-left: 0;
		list-style: none;
		counter-reset: mel-num;
		display: flex;
		flex-direction: column;
		gap: 0.55rem;
	}
	.doc-list li,
	.doc-steps li,
	.cell-list li {
		position: relative;
		padding-left: 1.7rem;
		font-size: 0.92rem;
		line-height: 1.6;
		color: #3b4a58;
		counter-increment: mel-num;
	}
	.doc-list li::before,
	.doc-steps li::before,
	.cell-list li::before {
		content: counter(mel-num) '.';
		position: absolute;
		left: 0;
		top: 0;
		width: 1.4rem;
		font-weight: 700;
		font-variant-numeric: tabular-nums;
		color: #1b75e0;
	}
	.doc-steps li {
		color: #1a2530;
	}
	.doc-steps strong {
		font-weight: 700;
		color: #0d2c4c;
		margin-right: 0.2rem;
	}
	.cell-list {
		margin: 0;
		gap: 0.28rem;
	}
	.cell-list li {
		font-size: inherit;
		line-height: 1.45;
		padding-left: 1.35rem;
	}
	.cell-list li::before {
		width: 1.15rem;
		font-size: 0.72rem;
	}
	.assumptions-list {
		color: #3b4a58;
	}
	.table-wrap {
		overflow: auto;
		width: 100%;
		border: 1px solid rgba(13, 44, 76, 0.14);
		background: #fff;
		border-radius: 0.2rem;
	}
	table {
		width: 100%;
		border-collapse: collapse;
		font-size: 0.78rem;
		line-height: 1.45;
	}
	th {
		text-align: left;
		padding: 0.65rem 0.75rem;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: #fff;
		background: #0d2c4c;
		vertical-align: top;
	}
	.frame-table th {
		background: #1b75e0;
	}
	td {
		padding: 0.65rem 0.75rem;
		border-top: 1px solid rgba(13, 44, 76, 0.1);
		vertical-align: top;
		color: #1a2530;
	}
	tr.goal td {
		background: #fff6e8;
	}
	tr.output td {
		background: #e8f7f2;
	}
	tr.cta td {
		border-top-color: rgba(13, 44, 76, 0.12);
	}
	.chain-label.cta-label {
		color: #0d2c4c;
	}
	.chain-title.cta-prompt {
		font-weight: 500;
		font-style: italic;
	}
	.chain-title.cta-goal {
		color: #b45309;
	}
	.chain-title.cta-output {
		color: #0f766e;
	}
	.type-cell {
		font-weight: 650;
		color: #1b75e0;
		white-space: nowrap;
	}
	.chain-label {
		display: block;
		font-size: 0.65rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: #1b75e0;
		margin-bottom: 0.2rem;
	}
	.chain-title {
		display: block;
		font-weight: 600;
		white-space: pre-line;
	}
	.pre {
		white-space: pre-line;
	}
	.playbooks {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 0.35rem;
		min-width: 8rem;
	}
	.playbook-link {
		color: #1b75e0;
		font-weight: 600;
		text-decoration: underline;
		text-underline-offset: 2px;
		line-height: 1.35;
	}
	.playbook-link:hover {
		color: #0d2c4c;
	}
	.muted {
		color: #6b7885;
	}
	.ind-name {
		font-weight: 650;
		min-width: 9rem;
	}
	.empty {
		color: #6b7885;
		font-style: italic;
		text-align: center;
	}
	.compact .doc-prose p,
	.compact .doc-lead,
	.compact .doc-list li,
	.compact .doc-steps li {
		font-size: 0.85rem;
	}
</style>
