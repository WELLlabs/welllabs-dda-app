/** Helpers for MEL form explore (table / map / charts). */

/**
 * @typedef {{ name: string, label: string, type: 'date'|'geopoint'|'number'|'text' }} Column
 * @typedef {Record<string, any>} Row
 */

const BAR_PREFER = /(moist|water.?level|level|height|depth|yield|value|avg)/i;
const LINE_PREFER = /(rain|precip)/i;
const COORD_PREC = 5;

/** @param {Column[]} columns @param {Row[]} rows */
export function numericColumns(columns) {
	return (columns || []).filter(
		(c) =>
			c.type === 'number' &&
			!/^(lat|lon|altitude|accuracy)$/i.test(c.name) &&
			!/altitude|accuracy/i.test(c.name)
	);
}

/** @param {Column[]} columns */
export function dateColumn(columns) {
	return (
		(columns || []).find((c) => c.type === 'date') ||
		(columns || []).find((c) => /date|time/i.test(c.name)) ||
		null
	);
}

/** @param {Column[]} columns @param {Row[]} rows @param {string} name */
function nonNullRate(rows, name) {
	if (!rows.length) return 0;
	let n = 0;
	for (const row of rows) {
		const v = row[name];
		if (v !== null && v !== undefined && v !== '' && !Number.isNaN(Number(v))) n += 1;
	}
	return n / rows.length;
}

/**
 * Schema-driven defaults for any form.
 * @param {Column[]} columns
 * @param {Row[]} rows
 */
export function pickExploreDefaults(columns, rows) {
	const nums = [...numericColumns(columns)].sort(
		(a, b) => nonNullRate(rows, b.name) - nonNullRate(rows, a.name)
	);
	const dateCol = dateColumn(columns);
	const bar =
		nums.find((c) => BAR_PREFER.test(c.name) || BAR_PREFER.test(c.label)) || nums[0] || null;
	const lineCandidates = nums.filter((c) => !bar || c.name !== bar.name);
	const line =
		lineCandidates.find((c) => LINE_PREFER.test(c.name) || LINE_PREFER.test(c.label)) ||
		lineCandidates[0] ||
		null;

	return {
		dateField: dateCol?.name || null,
		barField: bar?.name || null,
		lineField: line?.name || bar?.name || null,
		boxField: bar?.name || null,
		timeGrain: 'daily',
		lineTimeGrain: 'daily',
		boxTimeGrain: 'daily',
		sizeField: bar?.name || null,
		colorField: bar?.name || null
	};
}

/** @param {number|null|undefined} lat @param {number|null|undefined} lon */
export function siteKey(lat, lon) {
	if (lat == null || lon == null || Number.isNaN(lat) || Number.isNaN(lon)) return null;
	return `${Number(lat).toFixed(COORD_PREC)},${Number(lon).toFixed(COORD_PREC)}`;
}

/**
 * @param {Row[]} rows
 * @returns {Array<{ key: string, lat: number, lon: number, rows: Row[], latest: Row }>}
 */
export function groupSites(rows) {
	/** @type {Map<string, { key: string, lat: number, lon: number, rows: Row[] }>} */
	const map = new Map();
	for (const row of rows || []) {
		const key = siteKey(row.lat, row.lon);
		if (!key) continue;
		let site = map.get(key);
		if (!site) {
			site = { key, lat: row.lat, lon: row.lon, rows: [] };
			map.set(key, site);
		}
		site.rows.push(row);
	}
	return [...map.values()].map((site) => {
		const sorted = [...site.rows].sort((a, b) => String(b.observation_date || b._submittedAt || '').localeCompare(String(a.observation_date || a._submittedAt || '')));
		return { ...site, rows: sorted, latest: sorted[0] };
	});
}

/** @param {string|Date} value */
export function toDate(value) {
	if (!value) return null;
	const d = value instanceof Date ? value : new Date(value);
	return Number.isNaN(d.getTime()) ? null : d;
}

/** @param {Date} d @param {'daily'|'weekly'|'monthly'} grain */
export function bucketKey(d, grain) {
	const y = d.getUTCFullYear();
	const m = String(d.getUTCMonth() + 1).padStart(2, '0');
	const day = String(d.getUTCDate()).padStart(2, '0');
	if (grain === 'monthly') return `${y}-${m}`;
	if (grain === 'weekly') {
		const tmp = new Date(Date.UTC(y, d.getUTCMonth(), d.getUTCDate()));
		const dayNum = tmp.getUTCDay() || 7;
		tmp.setUTCDate(tmp.getUTCDate() + 4 - dayNum);
		const yearStart = new Date(Date.UTC(tmp.getUTCFullYear(), 0, 1));
		const week = Math.ceil(((tmp - yearStart) / 86400000 + 1) / 7);
		return `${tmp.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
	}
	return `${y}-${m}-${day}`;
}

/**
 * Aggregate numeric field by time grain (mean of values in bucket).
 * @param {Row[]} rows
 * @param {{ dateField: string, valueField: string, grain: 'daily'|'weekly'|'monthly' }} opts
 */
export function aggregateSeries(rows, { dateField, valueField, grain }) {
	/** @type {Map<string, { sum: number, n: number, date: Date }>} */
	const buckets = new Map();
	for (const row of rows || []) {
		const d = toDate(row[dateField]);
		if (!d) continue;
		const raw = row[valueField];
		if (raw === null || raw === undefined || raw === '') continue;
		const num = Number(raw);
		if (Number.isNaN(num)) continue;
		const key = bucketKey(d, grain);
		const cur = buckets.get(key) || { sum: 0, n: 0, date: d };
		cur.sum += num;
		cur.n += 1;
		if (d < cur.date) cur.date = d;
		buckets.set(key, cur);
	}
	return [...buckets.entries()]
		.map(([key, v]) => ({ key, date: v.date, value: v.sum / v.n, count: v.n }))
		.sort((a, b) => a.key.localeCompare(b.key));
}

/**
 * Quartiles for a sorted numeric array (inclusive method).
 * @param {number[]} sorted
 */
function quartiles(sorted) {
	if (!sorted.length) return null;
	const q = (p) => {
		const idx = (sorted.length - 1) * p;
		const lo = Math.floor(idx);
		const hi = Math.ceil(idx);
		if (lo === hi) return sorted[lo];
		return sorted[lo] * (1 - (idx - lo)) + sorted[hi] * (idx - lo);
	};
	return {
		min: sorted[0],
		q1: q(0.25),
		median: q(0.5),
		q3: q(0.75),
		max: sorted[sorted.length - 1]
	};
}

/**
 * Box-plot stats per time grain (distribution of raw values in each bucket).
 * @param {Row[]} rows
 * @param {{ dateField: string, valueField: string, grain: 'daily'|'weekly'|'monthly' }} opts
 */
export function boxPlotSeries(rows, { dateField, valueField, grain }) {
	/** @type {Map<string, { values: number[], date: Date }>} */
	const buckets = new Map();
	for (const row of rows || []) {
		const d = toDate(row[dateField]);
		if (!d) continue;
		const raw = row[valueField];
		if (raw === null || raw === undefined || raw === '') continue;
		const num = Number(raw);
		if (Number.isNaN(num)) continue;
		const key = bucketKey(d, grain);
		const cur = buckets.get(key) || { values: [], date: d };
		cur.values.push(num);
		if (d < cur.date) cur.date = d;
		buckets.set(key, cur);
	}
	return [...buckets.entries()]
		.map(([key, v]) => {
			const sorted = [...v.values].sort((a, b) => a - b);
			const stats = quartiles(sorted);
			return {
				key,
				date: v.date,
				count: sorted.length,
				...stats
			};
		})
		.sort((a, b) => a.key.localeCompare(b.key));
}

/**
 * Daily collection counts + optional value for heatmap.
 * @param {Row[]} rows
 * @param {{ dateField: string, valueField?: string|null }} opts
 */
export function dailyActivity(rows, { dateField, valueField = null }) {
	/** @type {Map<string, { date: Date, count: number, sum: number, n: number }>} */
	const map = new Map();
	for (const row of rows || []) {
		const d = toDate(row[dateField]);
		if (!d) continue;
		const key = bucketKey(d, 'daily');
		const cur = map.get(key) || { date: d, count: 0, sum: 0, n: 0 };
		cur.count += 1;
		if (valueField != null && row[valueField] !== null && row[valueField] !== undefined && row[valueField] !== '') {
			const num = Number(row[valueField]);
			if (!Number.isNaN(num)) {
				cur.sum += num;
				cur.n += 1;
			}
		}
		map.set(key, cur);
	}
	return [...map.entries()].map(([key, v]) => ({
		key,
		date: v.date,
		count: v.count,
		value: v.n ? v.sum / v.n : null
	}));
}

/**
 * Auto-pick a month-aligned start/end that covers most collection days.
 * Finds the shortest window covering ≥90% of active days, then expands to
 * full calendar months (capped at 18 months for readability).
 * @param {Array<{ date: Date, key?: string }>} activity
 * @returns {{ start: Date, end: Date, label: string } | null}
 *   `end` is exclusive (first day of the month after the last included month).
 */
export function autoCalendarRange(activity) {
	const dates = (activity || [])
		.map((d) => (d.date instanceof Date ? d.date : toDate(d.date || d.key)))
		.filter(Boolean)
		.sort((a, b) => a - b);
	if (!dates.length) return null;

	const n = dates.length;
	const need = Math.max(1, Math.ceil(n * 0.9));
	let bestLo = 0;
	let bestHi = n - 1;
	let bestSpan = dates[n - 1].getTime() - dates[0].getTime();
	for (let i = 0; i + need - 1 < n; i += 1) {
		const j = i + need - 1;
		const span = dates[j].getTime() - dates[i].getTime();
		if (span < bestSpan) {
			bestSpan = span;
			bestLo = i;
			bestHi = j;
		}
	}

	let start = d3UtcMonthFloor(dates[bestLo]);
	let end = d3UtcMonthAdd(d3UtcMonthFloor(dates[bestHi]), 1);

	const maxMonths = 18;
	const months = utcMonthDiff(start, end);
	if (months > maxMonths) {
		// Keep the recent side of the densest window
		end = d3UtcMonthAdd(d3UtcMonthFloor(dates[bestHi]), 1);
		start = d3UtcMonthAdd(end, -maxMonths);
	}
	if (end <= start) end = d3UtcMonthAdd(start, 1);

	return {
		start,
		end,
		startIdx: monthIndex(start),
		endIdx: monthIndex(end),
		months: utcMonthDiff(start, end),
		label: `${formatMonthYear(start)} – ${formatMonthYear(d3UtcMonthAdd(end, -1))}`
	};
}

/** @param {Date} d */
export function monthIndex(d) {
	return d.getUTCFullYear() * 12 + d.getUTCMonth();
}

/** @param {number} index */
export function dateFromMonthIndex(index) {
	const year = Math.floor(index / 12);
	const month = ((index % 12) + 12) % 12;
	return new Date(Date.UTC(year, month, 1));
}

/**
 * Hard pan limits as month indices (inclusive start, exclusive end).
 * Left = month of first ever value; right end = month after today.
 * @param {Row[]} rows
 * @param {string|null} dateField
 * @returns {{ minStart: number, maxEnd: number } | null}
 */
export function calendarPanLimits(rows, dateField) {
	if (!dateField) return null;
	let first = null;
	for (const row of rows || []) {
		const d = toDate(row[dateField]);
		if (!d) continue;
		if (!first || d < first) first = d;
	}
	if (!first) return null;
	const today = new Date();
	const todayUtc = new Date(
		Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate())
	);
	return {
		minStart: monthIndex(d3UtcMonthFloor(first)),
		maxEnd: monthIndex(d3UtcMonthFloor(todayUtc)) + 1
	};
}

/**
 * @param {number} startIdx
 * @param {number} months
 * @param {{ minStart: number, maxEnd: number }} limits
 */
export function clampCalendarWindow(startIdx, months, limits) {
	const span = Math.max(1, months || 1);
	let s = startIdx;
	let e = s + span;
	if (e > limits.maxEnd) {
		e = limits.maxEnd;
		s = e - span;
	}
	if (s < limits.minStart) {
		s = limits.minStart;
		e = s + span;
		if (e > limits.maxEnd) e = limits.maxEnd;
	}
	const start = dateFromMonthIndex(s);
	const end = dateFromMonthIndex(e);
	return {
		startIdx: s,
		endIdx: e,
		start,
		end,
		months: e - s,
		label: `${formatMonthYear(start)} – ${formatMonthYear(dateFromMonthIndex(e - 1))}`,
		canPanLeft: s > limits.minStart,
		canPanRight: e < limits.maxEnd
	};
}

export function shiftCalendarWindow(window, deltaMonths, limits) {
	if (!window || !limits) return window;
	return clampCalendarWindow(window.startIdx + deltaMonths, window.months, limits);
}

function d3UtcMonthFloor(d) {
	return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
}

function d3UtcMonthAdd(d, n) {
	return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1));
}

function utcMonthDiff(a, b) {
	return (b.getUTCFullYear() - a.getUTCFullYear()) * 12 + (b.getUTCMonth() - a.getUTCMonth());
}

function formatMonthYear(d) {
	const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
	return `${months[d.getUTCMonth()]} ${d.getUTCFullYear()}`;
}

/**
 * Fields that describe a site for the side panel.
 * Prefers the latest submission value; falls back to the modal non-empty value.
 * @param {Row[]} siteRows
 * @param {Column[]} columns
 * @param {Row|null} latest
 * @param {string[]} excludeNames
 */
export function siteMetadata(siteRows, columns, latest = null, excludeNames = []) {
	const exclude = new Set(excludeNames);
	const rows = siteRows || [];
	const head = latest || rows[0] || null;
	const meta = [];
	const prefer = [/district/i, /village/i, /structure/i, /practice/i, /plot/i, /name/i];

	const ranked = [...(columns || [])].sort((a, b) => {
		const ai = prefer.findIndex((re) => re.test(a.name) || re.test(a.label));
		const bi = prefer.findIndex((re) => re.test(b.name) || re.test(b.label));
		return (ai === -1 ? 99 : ai) - (bi === -1 ? 99 : bi);
	});

	for (const col of ranked) {
		if (exclude.has(col.name)) continue;
		if (col.type === 'geopoint' || col.type === 'date') continue;
		if (col.type === 'number') continue;
		if (col.name === 'instanceId' || col.name === 'lat' || col.name === 'lon') continue;

		let value = head?.[col.name];
		if (value === null || value === undefined || String(value).trim() === '') {
			const values = rows
				.map((r) => r[col.name])
				.filter((v) => v !== null && v !== undefined && String(v).trim() !== '');
			if (!values.length) continue;
			const counts = new Map();
			for (const v of values) counts.set(String(v).trim(), (counts.get(String(v).trim()) || 0) + 1);
			let mode = String(values[0]).trim();
			let best = 0;
			for (const [k, n] of counts) {
				if (n > best) {
					best = n;
					mode = k;
				}
			}
			value = mode;
		}

		const text = String(value ?? '').trim();
		if (!text) continue;
		meta.push({ name: col.name, label: col.label, value: text });
	}
	return meta;
}

/** @param {string} xmlFormId @param {object} prefs */
export function saveExplorePrefs(xmlFormId, prefs) {
	try {
		sessionStorage.setItem(`mel-explore:${xmlFormId}`, JSON.stringify(prefs));
	} catch {
		/* ignore */
	}
}

/** @param {string} xmlFormId */
export function loadExplorePrefs(xmlFormId) {
	try {
		const raw = sessionStorage.getItem(`mel-explore:${xmlFormId}`);
		return raw ? JSON.parse(raw) : null;
	} catch {
		return null;
	}
}

/** Synthetic picker column for lat/lon site keys. */
export const SITE_COORD_COLUMN = '__coordinate__';

/**
 * Representative value of a column for one site (latest non-empty, else mode).
 * @param {{ key: string, rows: Row[], latest?: Row }} site
 * @param {string} columnName
 */
export function siteColumnValue(site, columnName) {
	if (!site) return null;
	if (columnName === SITE_COORD_COLUMN) {
		return `${Number(site.lat).toFixed(COORD_PREC)}, ${Number(site.lon).toFixed(COORD_PREC)}`;
	}
	const rows = site.rows || [];
	const head = site.latest || rows[0] || null;
	const fromHead = head?.[columnName];
	if (fromHead !== null && fromHead !== undefined && String(fromHead).trim() !== '') {
		return String(fromHead).trim();
	}
	const values = rows
		.map((r) => r[columnName])
		.filter((v) => v !== null && v !== undefined && String(v).trim() !== '')
		.map((v) => String(v).trim());
	if (!values.length) return null;
	const counts = new Map();
	for (const v of values) counts.set(v, (counts.get(v) || 0) + 1);
	let best = values[0];
	let bestN = 0;
	for (const [k, n] of counts) {
		if (n > bestN) {
			bestN = n;
			best = k;
		}
	}
	return best;
}

/**
 * Columns for picking a site: coordinates, plus id / code fields only.
 * @param {Array<{ key: string, lat: number, lon: number, rows: Row[], latest?: Row }>} sites
 * @param {Column[]} columns
 */
export function sitePickerColumns(sites, columns) {
	/** @type {{ name: string, label: string, unique: boolean }[]} */
	const options = [
		{ name: SITE_COORD_COLUMN, label: 'Coordinates', unique: true }
	];
	if (!sites?.length) return options;

	const idName = /^(id|instanceid|instance_id)$|(_id$)|(^id_)|(code$)|(_code$)|(site.?id)|(plot.?id)|(well.?id)|(structure.?id)/i;

	for (const col of columns || []) {
		if (!col?.name) continue;
		if (col.type === 'geopoint' || col.type === 'date') continue;
		if (/^(lat|lon|altitude|accuracy)$/i.test(col.name)) continue;
		if (col.name === SITE_COORD_COLUMN) continue;

		const label = col.label || col.name;
		if (!idName.test(col.name) && !idName.test(label)) continue;

		const pairs = sites
			.map((site) => ({ key: site.key, value: siteColumnValue(site, col.name) }))
			.filter((p) => p.value != null && p.value !== '');
		if (!pairs.length) continue;

		const byValue = new Map();
		for (const p of pairs) {
			if (!byValue.has(p.value)) byValue.set(p.value, new Set());
			byValue.get(p.value).add(p.key);
		}
		const unique =
			[...byValue.values()].every((set) => set.size === 1) && byValue.size === pairs.length;

		options.push({
			name: col.name,
			label,
			unique
		});
	}

	options.sort((a, b) => {
		if (a.name === SITE_COORD_COLUMN) return -1;
		if (b.name === SITE_COORD_COLUMN) return 1;
		return a.label.localeCompare(b.label);
	});

	return options;
}

/**
 * Distinct values for a picker column, each mapped to a site key.
 * @param {Array<{ key: string, lat: number, lon: number, rows: Row[], latest?: Row }>} sites
 * @param {string} columnName
 */
export function sitePickerValues(sites, columnName) {
	/** @type {Map<string, { value: string, label: string, siteKey: string }>} */
	const byValue = new Map();
	for (const site of sites || []) {
		const value = siteColumnValue(site, columnName);
		if (value == null || value === '') continue;
		if (byValue.has(value)) {
			const existing = byValue.get(value);
			if (existing.siteKey !== site.key) {
				// Ambiguous value — keep first site, append coord hint to later entries via unique key
				const labeled = `${value} (${Number(site.lat).toFixed(COORD_PREC)}, ${Number(site.lon).toFixed(COORD_PREC)})`;
				byValue.set(`${value}@@${site.key}`, {
					value: labeled,
					label: labeled,
					siteKey: site.key
				});
			}
			continue;
		}
		byValue.set(value, {
			value,
			label:
				columnName === SITE_COORD_COLUMN
					? value
					: value,
			siteKey: site.key
		});
	}
	return [...byValue.values()].sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
}

/** Green sequential palette for map / heatmap */
export const ASSESS_BLUE = '#1b75e0';
export const BLUE_SCALE = ['#e8f1fc', '#7dc3ff', '#3969a7', '#1565c0', '#0d2c4c'];
