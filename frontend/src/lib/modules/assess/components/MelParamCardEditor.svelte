<script>
	import {
		INPUT_TYPE_OPTIONS,
		addOption,
		patchCard,
		removeOption,
		setOptionAt,
		typeLabel,
		usesOptions
	} from '$lib/modules/assess/mel-param-cards.js';

	/** @type {{
	 *   cards: any[],
	 *   onChange: (next: any[]) => void,
	 *   emptyLabel?: string,
	 *   title?: string,
	 *   subtitle?: string
	 * }} */
	let {
		cards = [],
		onChange,
		emptyLabel = 'No parameters yet.',
		title = '',
		subtitle = 'Review each field, then click Edit to change labels, types, or options.'
	} = $props();

	let editingId = $state(null);

	function update(id, patch) {
		onChange(patchCard(cards, id, patch));
	}

	function remove(id) {
		const card = cards.find((c) => c.id === id);
		if (!card || card.locked) return;
		if (editingId === id) editingId = null;
		onChange(patchCard(cards, id, { included: false, required: false }));
	}

	function restore(id) {
		onChange(patchCard(cards, id, { included: true }));
	}
</script>

<section class="fwa-editor">
	{#if title}
		<header class="fwa-head">
			<h2>{title}</h2>
			{#if subtitle}
				<p>{subtitle}</p>
			{/if}
		</header>
	{:else if subtitle}
		<p class="fwa-lead">{subtitle}</p>
	{/if}

	{#if !cards.length}
		<p class="empty">{emptyLabel}</p>
	{:else}
		<div class="field-list" role="list">
			{#each cards as card, index (card.id)}
				{@const editing = editingId === card.id && card.included !== false}
				<article class="field-card" class:excluded={!card.included} class:editing role="listitem">
					{#if !editing}
						<div class="view-row">
							<h3 class="field-title">{card.label || `Field ${index + 1}`}</h3>
							<span class="dot" aria-hidden="true">·</span>
							<span class="meta">{typeLabel(card.input_type)}</span>
							{#if card.required || card.locked}
								<span class="dot" aria-hidden="true">·</span>
								<span class="meta">Required</span>
							{/if}
							{#if card.metric}
								<span class="dot" aria-hidden="true">·</span>
								<span class="meta">{card.metric}</span>
							{/if}
							{#if card.included === false}
								<span class="dot" aria-hidden="true">·</span>
								<span class="meta">Removed</span>
							{:else if usesOptions(card.input_type) && (card.options || []).length}
								<span class="dot" aria-hidden="true">·</span>
								<span class="meta opts" title={(card.options || []).join(', ')}>
									{(card.options || []).join(', ')}
								</span>
							{/if}
							<div class="field-actions">
								{#if card.included === false}
									<button type="button" class="remove-btn restore" onclick={() => restore(card.id)}
										>Restore</button
									>
								{:else}
									<button type="button" class="edit-btn" onclick={() => (editingId = card.id)}
										>Edit</button
									>
								{/if}
							</div>
						</div>
					{:else}
						<div class="field-top">
							<div class="field-title-wrap">
								<h3 class="field-title">{card.label || `Field ${index + 1}`}</h3>
								<span class="default-pill">default</span>
							</div>
							<div class="field-actions">
								{#if !card.locked}
									<button type="button" class="remove-btn" onclick={() => remove(card.id)}>Remove</button>
								{/if}
								<button type="button" class="done-btn" onclick={() => (editingId = null)}>Done</button>
							</div>
						</div>
						<div class="field-grid">
							<label class="ctl">
								<span>Display label</span>
								<input
									type="text"
									value={card.label}
									oninput={(e) => update(card.id, { label: e.currentTarget.value })}
								/>
							</label>
							<label class="ctl">
								<span>Widget type</span>
								<select
									value={card.input_type}
									onchange={(e) => update(card.id, { input_type: e.currentTarget.value })}
								>
									{#each INPUT_TYPE_OPTIONS as opt (opt.id)}
										<option value={opt.id}>{opt.label}</option>
									{/each}
								</select>
							</label>
							<label class="required">
								<input
									type="checkbox"
									checked={!!(card.required || card.locked)}
									disabled={card.locked}
									onchange={(e) => update(card.id, { required: e.currentTarget.checked })}
								/>
								Required
							</label>
						</div>
						{#if usesOptions(card.input_type)}
							<div class="options">
								<div class="options-head">
									<span>Dropdown options</span>
									<button type="button" class="link" onclick={() => onChange(addOption(cards, card.id))}
										>+ Add option</button
									>
								</div>
								{#each card.options || [] as opt, oi}
									<div class="option-row">
										<input
											type="text"
											value={opt}
											placeholder={`Option ${oi + 1}`}
											oninput={(e) =>
												onChange(setOptionAt(cards, card.id, oi, e.currentTarget.value))}
										/>
										<button
											type="button"
											class="link muted"
											disabled={(card.options || []).length <= 1}
											onclick={() => onChange(removeOption(cards, card.id, oi))}
										>
											Remove
										</button>
									</div>
								{/each}
							</div>
						{/if}
					{/if}
				</article>
			{/each}
		</div>
	{/if}
</section>

<style>
	.fwa-editor {
		--ink: #0f172a;
		--muted: #64748b;
		--line: #e2e8f0;
		--accent: #1b75e0;
		--paper: #f8fafc;
		display: flex;
		flex-direction: column;
		gap: 0.85rem;
		container-type: inline-size;
		container-name: fwa;
	}
	.fwa-head h2 {
		margin: 0;
		font-size: 1.15rem;
		font-weight: 700;
		color: var(--ink);
	}
	.fwa-head p,
	.fwa-lead {
		margin: 0.35rem 0 0;
		font-size: 0.875rem;
		line-height: 1.45;
		color: var(--muted);
	}
	.fwa-lead {
		margin: 0;
	}
	.empty {
		margin: 0;
		padding: 1rem;
		border-radius: 0.75rem;
		border: 1px dashed var(--line);
		background: white;
		color: var(--muted);
		font-size: 0.875rem;
	}
	.field-list {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}
	.field-card {
		border-radius: 0.75rem;
		border: 1px solid var(--line);
		background: white;
		padding: 0.55rem 0.9rem;
	}
	.field-card.editing {
		padding: 0.9rem 1rem 1rem;
		border-color: color-mix(in srgb, var(--accent) 45%, var(--line));
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 10%, transparent);
	}
	.field-card.excluded {
		opacity: 0.55;
		border-style: dashed;
		background: var(--paper);
	}
	.view-row {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		min-width: 0;
		white-space: nowrap;
	}
	.view-row .field-title {
		flex: 0 1 auto;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.dot {
		color: #cbd5e1;
		flex-shrink: 0;
	}
	.meta {
		flex-shrink: 0;
		color: var(--muted);
		font-size: 0.8rem;
	}
	.meta.opts {
		flex: 1 1 auto;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.view-row .field-actions {
		margin-left: auto;
		flex-shrink: 0;
	}
	.field-top {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.75rem;
		margin-bottom: 0.75rem;
	}
	.field-title-wrap {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		min-width: 0;
	}
	.field-title {
		margin: 0;
		font-size: 0.95rem;
		font-weight: 700;
		color: var(--ink);
	}
	.default-pill {
		flex-shrink: 0;
		border-radius: 999px;
		background: #dbeafe;
		color: #1d4ed8;
		padding: 0.12rem 0.45rem;
		font-size: 0.68rem;
		font-weight: 600;
		line-height: 1.2;
	}
	.field-actions {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		flex-shrink: 0;
	}
	.remove-btn,
	.edit-btn,
	.done-btn {
		border: none;
		background: transparent;
		font-size: 0.875rem;
		cursor: pointer;
		padding: 0;
	}
	.remove-btn {
		color: #94a3b8;
	}
	.remove-btn:hover {
		color: #64748b;
	}
	.remove-btn.restore,
	.edit-btn,
	.done-btn {
		color: var(--accent);
		font-weight: 600;
	}
	.field-grid {
		display: grid;
		grid-template-columns: minmax(0, 1.2fr) minmax(8rem, 0.9fr) auto;
		gap: 0.75rem 0.85rem;
		align-items: end;
	}
	.ctl {
		display: grid;
		gap: 0.3rem;
		min-width: 0;
	}
	.ctl span {
		font-size: 0.8rem;
		font-weight: 500;
		color: #334155;
	}
	.ctl input,
	.ctl select,
	.option-row input {
		width: 100%;
		border-radius: 0.45rem;
		border: 1px solid #cbd5e1;
		background: white;
		padding: 0.5rem 0.65rem;
		font-size: 0.875rem;
		color: var(--ink);
		outline: none;
	}
	.ctl input:focus,
	.ctl select:focus,
	.option-row input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
	}
	.required {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		padding-bottom: 0.55rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: #334155;
		white-space: nowrap;
	}
	.required input {
		width: 1rem;
		height: 1rem;
		accent-color: var(--accent);
	}
	.options {
		margin-top: 0.85rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--line);
		display: grid;
		gap: 0.45rem;
	}
	.options-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		font-size: 0.8rem;
		font-weight: 600;
		color: #334155;
	}
	.option-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.link {
		border: none;
		background: transparent;
		cursor: pointer;
		font-size: 0.8rem;
		font-weight: 600;
		color: var(--accent);
		padding: 0;
		white-space: nowrap;
	}
	.link.muted {
		color: #94a3b8;
		font-weight: 500;
	}
	.link:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	@media (max-width: 860px) {
		.field-grid {
			grid-template-columns: 1fr;
			align-items: stretch;
		}
		.required {
			padding-bottom: 0;
		}
	}
	@container fwa (max-width: 520px) {
		.field-grid {
			grid-template-columns: 1fr;
			align-items: stretch;
		}
		.required {
			padding-bottom: 0;
		}
	}
</style>
