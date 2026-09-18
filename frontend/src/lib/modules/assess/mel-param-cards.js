export function isAssetSelectId(id) {
	const key = String(id || '').toLowerCase();
	return key.endsWith('select_the_asset_id') || key === 'asset_id';
}

export const ASSET_SELECT_LOCK_IDS = [
	'fp_cm_select_the_asset_id',
	'bm_cm_select_the_asset_id'
];

export const INPUT_TYPE_OPTIONS = [
	{ id: 'text', label: 'Text' },
	{ id: 'integer', label: 'Whole number' },
	{ id: 'decimal', label: 'Decimal' },
	{ id: 'date', label: 'Date' },
	{ id: 'geopoint', label: 'Location' },
	{ id: 'select_one', label: 'Single select' },
	{ id: 'select_multiple', label: 'Multi select' },
	{ id: 'select_one_yes_no', label: 'Yes / No' },
	{ id: 'note', label: 'Note / instruction' }
];

const TYPE_ALIASES = {
	text: 'text',
	integer: 'integer',
	decimal: 'decimal',
	date: 'date',
	coordinate: 'geopoint',
	geopoint: 'geopoint',
	'single select': 'select_one',
	'multi select': 'select_multiple',
	select_one: 'select_one',
	select_multiple: 'select_multiple',
	select_one_yes_no: 'select_one_yes_no',
	note: 'note',
	string: 'text',
	number: 'decimal'
};

export function normalizeInputType(t) {
	const key = String(t || 'text').trim().toLowerCase();
	return TYPE_ALIASES[key] || TYPE_ALIASES[key.replace(/_/g, ' ')] || 'text';
}

export function typeLabel(t) {
	const id = normalizeInputType(t);
	return INPUT_TYPE_OPTIONS.find((o) => o.id === id)?.label || id;
}

export function usesOptions(typeId) {
	const id = normalizeInputType(typeId);
	return id === 'select_one' || id === 'select_multiple' || id === 'select_one_yes_no';
}

export function defaultOptionsForType(typeId) {
	const id = normalizeInputType(typeId);
	if (id === 'select_one_yes_no') return ['Yes', 'No'];
	if (id === 'select_one' || id === 'select_multiple') return ['Option 1', 'Option 2'];
	return [];
}

function optionLabels(raw) {
	if (!Array.isArray(raw)) return [];
	return raw
		.map((o) => {
			if (o == null) return '';
			if (typeof o === 'string') return o.trim();
			return String(o.label || o.value || '').trim();
		})
		.filter(Boolean);
}

function isPlaceholderOptions(list, inputType) {
	const defaults = defaultOptionsForType(inputType);
	if (!Array.isArray(list) || list.length === 0) return true;
	if (!defaults.length || list.length !== defaults.length) return false;
	return list.every((v, i) => String(v) === defaults[i]);
}

function pickOptions(inputType, sources, allowEmpty = false) {
	for (const raw of sources) {
		const list = optionLabels(raw);
		if (list.length && !isPlaceholderOptions(list, inputType)) return list;
	}
	if (allowEmpty || !usesOptions(inputType)) return [];
	return defaultOptionsForType(inputType);
}

function normalizeOptions(raw, inputType) {
	return pickOptions(inputType, [raw]);
}

/**
 * Build editable cards from catalog questions + optional saved overrides.
 * @param {any[]} questions
 * @param {any[] | null | undefined} saved
 * @param {{ lockIds?: string[] }} [opts]
 */
export function buildParamCards(questions, saved = null, opts = {}) {
	const lockIds = new Set(opts.lockIds || []);
	const byId = new Map();
	for (const s of saved || []) {
		if (s?.id) byId.set(s.id, s);
	}

	const cards = (questions || [])
		.filter((q) => q.variable_name || q.id)
		.map((q, i) => {
			const id = q.variable_name || q.id;
			const prev = byId.get(id);
			const inputType = normalizeInputType(
				prev?.input_type || q.input_type || 'text'
			);
			const options = pickOptions(
				inputType,
				[prev?.options, prev?.selectors, q.selectors, q.options, q.choices],
				lockIds.has(id)
			);
			return {
				id,
				label: prev?.label || q.question || q.label || `Parameter ${i + 1}`,
				input_type: inputType,
				metric: prev?.metric ?? q.metric ?? '',
				hint: prev?.hint ?? q.skip_logic ?? q.hint ?? '',
				skip_logic: prev?.skip_logic ?? q.skip_logic ?? '',
				options,
				selectors: options,
				included: prev?.included !== false,
				locked: lockIds.has(id) || !!prev?.locked,
				required: !!(prev?.required || lockIds.has(id) || prev?.locked),
				order: prev?.order ?? i
			};
		});

	cards.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
	return cards.map((c, i) => ({ ...c, order: i }));
}

/** Persist-safe slice of cards for plan_json. */
export function serializeParamCards(cards) {
	return (cards || []).map((c, i) => {
		const inputType = normalizeInputType(c.input_type || 'text');
		const options = usesOptions(inputType)
			? normalizeOptions(c.options ?? c.selectors, inputType)
			: [];
		return {
			id: c.id,
			label: c.label,
			included: c.included !== false,
			locked: !!c.locked,
			required: !!(c.required || c.locked),
			order: i,
			input_type: inputType,
			metric: c.metric || '',
			hint: c.hint || '',
			skip_logic: c.skip_logic || '',
			options,
			selectors: options
		};
	});
}

export function moveCard(cards, id, dir) {
	const list = [...(cards || [])];
	const idx = list.findIndex((c) => c.id === id);
	const j = idx + dir;
	if (idx < 0 || j < 0 || j >= list.length) return list;
	[list[idx], list[j]] = [list[j], list[idx]];
	return list.map((c, i) => ({ ...c, order: i }));
}

export function patchCard(cards, id, patch) {
	return (cards || []).map((c) => {
		if (c.id !== id) return c;
		const next = { ...c, ...patch };
		if ('input_type' in patch) {
			next.input_type = normalizeInputType(patch.input_type);
			if (usesOptions(next.input_type)) {
				const existing = next.options?.length ? next.options : next.selectors;
				next.options = normalizeOptions(existing, next.input_type);
				next.selectors = next.options;
			} else {
				next.options = [];
				next.selectors = [];
			}
		}
		if ('options' in patch || 'selectors' in patch) {
			next.options = normalizeOptions(patch.options ?? patch.selectors, next.input_type);
			next.selectors = next.options;
		}
		return next;
	});
}

export function includedCards(cards) {
	return (cards || []).filter((c) => c.included !== false);
}

export function setOptionAt(cards, id, index, value) {
	return (cards || []).map((c) => {
		if (c.id !== id) return c;
		const options = [...(c.options || [])];
		options[index] = value;
		return { ...c, options, selectors: options };
	});
}

export function addOption(cards, id, value = '') {
	return (cards || []).map((c) => {
		if (c.id !== id) return c;
		const options = [...(c.options || []), value || `Option ${(c.options || []).length + 1}`];
		return { ...c, options, selectors: options };
	});
}

export function removeOption(cards, id, index) {
	return (cards || []).map((c) => {
		if (c.id !== id) return c;
		const options = (c.options || []).filter((_, i) => i !== index);
		return { ...c, options, selectors: options };
	});
}
