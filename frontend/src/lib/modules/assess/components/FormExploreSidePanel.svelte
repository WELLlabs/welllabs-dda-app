<script>
	import { onDestroy } from 'svelte';
	import * as d3 from 'd3';
	import {
		ASSESS_GREEN,
		GREEN_SCALE,
		aggregateSeries,
		autoCalendarRange,
		boxPlotSeries,
		calendarPanLimits,
		clampCalendarWindow,
		dailyActivity,
		siteMetadata
	} from '$lib/modules/assess/form-explore.js';

	/**
	 * @type {{
	 *   site: any,
	 *   columns: any[],
	 *   dateField: string|null,
	 *   barField: string,
	 *   lineField: string|null,
	 *   boxField: string|null,
	 *   timeGrain: 'daily'|'weekly'|'monthly',
	 *   lineTimeGrain: 'daily'|'weekly'|'monthly',
	 *   boxTimeGrain: 'daily'|'weekly'|'monthly',
	 *   numericFields: any[],
	 *   onChange: (patch: object) => void,
	 *   section: 'about'|'bar'|'line'|'calendar'|'box'
	 * }}
	 */
	let {
		site,
		columns = [],
		dateField = null,
		barField,
		lineField = null,
		boxField = null,
		timeGrain = 'daily',
		lineTimeGrain = 'daily',
		boxTimeGrain = 'daily',
		numericFields = [],
		onChange,
		section
	} = $props();

	let chartEl;
	let lineEl;
	let boxEl;
	let heatEl;
	/** @type {string|null} */
	let calFilterField = $state(null);
	/** @type {'gt'|'lt'|'eq'} */
	let calFilterOp = $state('gt');
	let calFilterValue = $state('');
	/** Month-index start of the visible window (plain number — safe in $state). */
	let calStartIdx = $state(/** @type {number|null} */ (null));
	let calSpanMonths = $state(12);
	/** Reset pan when site / filter baseline changes */
	let calWindowKey = $state('');

	const selectClass =
		'w-full rounded border border-brand-navy/20 px-2 py-1.5 font-body text-sm text-brand-navy outline-none focus:border-brand-navy/40';

	const meta = $derived(siteMetadata(site?.rows || [], columns, site?.latest || null, [
		barField,
		lineField,
		boxField,
		dateField,
		'sizeField',
		'colorField'
	].filter(Boolean)));

	const barSeries = $derived(
		dateField && barField
			? aggregateSeries(site?.rows || [], { dateField, valueField: barField, grain: timeGrain })
			: []
	);
	const lineSeries = $derived(
		dateField && lineField
			? aggregateSeries(site?.rows || [], {
					dateField,
					valueField: lineField,
					grain: lineTimeGrain
				})
			: []
	);
	const boxSeries = $derived(
		dateField && boxField
			? boxPlotSeries(site?.rows || [], {
					dateField,
					valueField: boxField,
					grain: boxTimeGrain
				})
			: []
	);

	const calendarRows = $derived.by(() => {
		const rows = site?.rows || [];
		const field = calFilterField || barField;
		const raw = String(calFilterValue ?? '').trim();
		if (!field || raw === '') return rows;
		const threshold = Number(raw);
		if (Number.isNaN(threshold)) return rows;
		return rows.filter((row) => {
			const v = row[field];
			if (v === null || v === undefined || v === '') return false;
			const num = Number(v);
			if (Number.isNaN(num)) return false;
			if (calFilterOp === 'gt') return num > threshold;
			if (calFilterOp === 'lt') return num < threshold;
			return num === threshold;
		});
	});

	const activity = $derived(
		dateField
			? dailyActivity(calendarRows, {
					dateField,
					valueField: calFilterField || barField
				})
			: []
	);

	const panLimits = $derived(calendarPanLimits(site?.rows || [], dateField));

	const calWindow = $derived.by(() => {
		if (calStartIdx == null || !panLimits) return null;
		return clampCalendarWindow(calStartIdx, calSpanMonths, panLimits);
	});

	const barLabel = $derived(numericFields.find((f) => f.name === barField)?.label || barField);
	const lineLabel = $derived(numericFields.find((f) => f.name === lineField)?.label || lineField);
	const boxLabel = $derived(numericFields.find((f) => f.name === boxField)?.label || boxField);
	const calFilterLabel = $derived(
		numericFields.find((f) => f.name === (calFilterField || barField))?.label ||
			calFilterField ||
			barField
	);

	$effect(() => {
		if (!calFilterField && barField) calFilterField = barField;
	});

	// Seed the window only when the site (or date field) changes.
	// Filters and pan clicks must not reset the visible range.
	$effect(() => {
		const key = `${site?.key || ''}|${dateField || ''}`;
		const limits = calendarPanLimits(site?.rows || [], dateField);
		if (!limits) {
			if (calWindowKey !== key) {
				calStartIdx = null;
				calWindowKey = key;
			}
			return;
		}
		if (key === calWindowKey && calStartIdx != null) return;

		const auto = autoCalendarRange(
			dateField
				? dailyActivity(site?.rows || [], {
						dateField,
						valueField: calFilterField || barField
					})
				: []
		);
		const next = clampCalendarWindow(
			auto?.startIdx ?? limits.minStart,
			auto?.months || 12,
			limits
		);
		calStartIdx = next.startIdx;
		calSpanMonths = next.months;
		calWindowKey = key;
	});

	$effect(() => {
		if (section !== 'bar' || !chartEl) return;
		const ro = new ResizeObserver(() => drawBar());
		ro.observe(chartEl);
		drawBar();
		return () => ro.disconnect();
	});

	$effect(() => {
		if (section !== 'line' || !lineEl) return;
		const ro = new ResizeObserver(() => drawLine());
		ro.observe(lineEl);
		drawLine();
		return () => ro.disconnect();
	});

	$effect(() => {
		if (section !== 'box' || !boxEl) return;
		const ro = new ResizeObserver(() => drawBox());
		ro.observe(boxEl);
		drawBox();
		return () => ro.disconnect();
	});

	$effect(() => {
		if (section !== 'calendar' || !heatEl) return;
		const ro = new ResizeObserver(() => drawHeat());
		ro.observe(heatEl);
		drawHeat();
		return () => ro.disconnect();
	});

	$effect(() => {
		if (section !== 'bar') return;
		barSeries;
		timeGrain;
		drawBar();
	});

	$effect(() => {
		if (section !== 'line') return;
		lineSeries;
		lineTimeGrain;
		drawLine();
	});

	$effect(() => {
		if (section !== 'box') return;
		boxSeries;
		boxTimeGrain;
		drawBox();
	});

	$effect(() => {
		if (section !== 'calendar') return;
		activity;
		calWindow;
		calFilterField;
		calFilterOp;
		calFilterValue;
		drawHeat();
	});

	onDestroy(() => {
		if (chartEl) d3.select(chartEl).selectAll('*').remove();
		if (lineEl) d3.select(lineEl).selectAll('*').remove();
		if (boxEl) d3.select(boxEl).selectAll('*').remove();
		if (heatEl) d3.select(heatEl).selectAll('*').remove();
	});

	function drawBar() {
		if (!chartEl) return;
		const width = Math.max(200, chartEl.clientWidth || 360);
		const height = Math.max(160, chartEl.clientHeight || 200);
		const margin = { top: 12, right: 12, bottom: 36, left: 40 };
		d3.select(chartEl).selectAll('*').remove();
		if (!barSeries.length) {
			d3.select(chartEl)
				.append('p')
				.attr('class', 'empty')
				.text(dateField ? 'No numeric readings for this site.' : 'No date field to chart.');
			return;
		}

		const svg = d3
			.select(chartEl)
			.append('svg')
			.attr('width', width)
			.attr('height', height)
			.attr('viewBox', `0 0 ${width} ${height}`);

		const keys = barSeries.map((d) => d.key);
		const x = d3
			.scaleBand()
			.domain(keys)
			.range([margin.left, width - margin.right])
			.padding(0.2);
		const yMax = d3.max(barSeries, (d) => d.value) || 1;
		const y = d3
			.scaleLinear()
			.domain([0, yMax * 1.1])
			.nice()
			.range([height - margin.bottom, margin.top]);

		svg
			.append('g')
			.attr('transform', `translate(0,${height - margin.bottom})`)
			.call(d3.axisBottom(x).tickValues(keys.filter((_, i) => i % Math.ceil(keys.length / 6) === 0)))
			.selectAll('text')
			.attr('transform', 'rotate(-30)')
			.style('text-anchor', 'end')
			.style('font-size', '9px');

		svg
			.append('g')
			.attr('transform', `translate(${margin.left},0)`)
			.call(d3.axisLeft(y).ticks(5))
			.selectAll('text')
			.style('font-size', '9px');

		svg
			.selectAll('rect.bar')
			.data(barSeries)
			.join('rect')
			.attr('x', (d) => x(d.key))
			.attr('y', (d) => y(d.value))
			.attr('width', x.bandwidth())
			.attr('height', (d) => Math.max(0, y(0) - y(d.value)))
			.attr('fill', ASSESS_GREEN)
			.attr('opacity', 0.85)
			.append('title')
			.text((d) => `${d.key}: ${d.value.toFixed(2)}`);
	}

	function drawLine() {
		if (!lineEl) return;
		const width = Math.max(200, lineEl.clientWidth || 360);
		const height = Math.max(160, lineEl.clientHeight || 200);
		const margin = { top: 12, right: 12, bottom: 36, left: 40 };
		d3.select(lineEl).selectAll('*').remove();
		if (!lineSeries.length) {
			d3.select(lineEl)
				.append('p')
				.attr('class', 'empty')
				.text(dateField ? 'No numeric readings for this site.' : 'No date field to chart.');
			return;
		}

		const svg = d3
			.select(lineEl)
			.append('svg')
			.attr('width', width)
			.attr('height', height)
			.attr('viewBox', `0 0 ${width} ${height}`);

		const keys = lineSeries.map((d) => d.key);
		const x = d3
			.scalePoint()
			.domain(keys)
			.range([margin.left, width - margin.right])
			.padding(0.25);
		const yMax = d3.max(lineSeries, (d) => d.value) || 1;
		const y = d3
			.scaleLinear()
			.domain([0, yMax * 1.1])
			.nice()
			.range([height - margin.bottom, margin.top]);

		svg
			.append('g')
			.attr('transform', `translate(0,${height - margin.bottom})`)
			.call(d3.axisBottom(x).tickValues(keys.filter((_, i) => i % Math.ceil(keys.length / 6) === 0)))
			.selectAll('text')
			.attr('transform', 'rotate(-30)')
			.style('text-anchor', 'end')
			.style('font-size', '9px');

		svg
			.append('g')
			.attr('transform', `translate(${margin.left},0)`)
			.call(d3.axisLeft(y).ticks(5))
			.selectAll('text')
			.style('font-size', '9px');

		const line = d3
			.line()
			.x((d) => x(d.key) ?? 0)
			.y((d) => y(d.value));

		svg
			.append('path')
			.datum(lineSeries)
			.attr('fill', 'none')
			.attr('stroke', ASSESS_GREEN)
			.attr('stroke-width', 2.25)
			.attr('d', line);

		svg
			.selectAll('circle.pt')
			.data(lineSeries)
			.join('circle')
			.attr('cx', (d) => x(d.key) ?? 0)
			.attr('cy', (d) => y(d.value))
			.attr('r', 3.5)
			.attr('fill', ASSESS_GREEN)
			.append('title')
			.text((d) => `${d.key}: ${d.value.toFixed(2)}`);
	}

	function drawBox() {
		if (!boxEl) return;
		const width = Math.max(200, boxEl.clientWidth || 360);
		const height = Math.max(160, boxEl.clientHeight || 200);
		const margin = { top: 12, right: 12, bottom: 36, left: 40 };
		d3.select(boxEl).selectAll('*').remove();
		if (!boxSeries.length) {
			d3.select(boxEl)
				.append('p')
				.attr('class', 'empty')
				.text(dateField ? 'No numeric readings for this site.' : 'No date field to chart.');
			return;
		}

		const svg = d3
			.select(boxEl)
			.append('svg')
			.attr('width', width)
			.attr('height', height)
			.attr('viewBox', `0 0 ${width} ${height}`);

		const keys = boxSeries.map((d) => d.key);
		const x = d3
			.scaleBand()
			.domain(keys)
			.range([margin.left, width - margin.right])
			.padding(0.28);
		const yMin = d3.min(boxSeries, (d) => d.min) ?? 0;
		const yMax = d3.max(boxSeries, (d) => d.max) ?? 1;
		const pad = (yMax - yMin) * 0.08 || Math.abs(yMax) * 0.05 || 1;
		const y = d3
			.scaleLinear()
			.domain([yMin - pad, yMax + pad])
			.nice()
			.range([height - margin.bottom, margin.top]);

		svg
			.append('g')
			.attr('transform', `translate(0,${height - margin.bottom})`)
			.call(d3.axisBottom(x).tickValues(keys.filter((_, i) => i % Math.ceil(keys.length / 6) === 0)))
			.selectAll('text')
			.attr('transform', 'rotate(-30)')
			.style('text-anchor', 'end')
			.style('font-size', '9px');

		svg
			.append('g')
			.attr('transform', `translate(${margin.left},0)`)
			.call(d3.axisLeft(y).ticks(5))
			.selectAll('text')
			.style('font-size', '9px');

		const g = svg
			.selectAll('g.box')
			.data(boxSeries)
			.join('g')
			.attr('class', 'box')
			.attr('transform', (d) => `translate(${x(d.key) ?? 0},0)`);

		const bw = x.bandwidth();
		const cx = bw / 2;

		g.append('line')
			.attr('x1', cx)
			.attr('x2', cx)
			.attr('y1', (d) => y(d.min))
			.attr('y2', (d) => y(d.max))
			.attr('stroke', ASSESS_GREEN)
			.attr('stroke-width', 1.25);

		g.append('line')
			.attr('x1', bw * 0.25)
			.attr('x2', bw * 0.75)
			.attr('y1', (d) => y(d.min))
			.attr('y2', (d) => y(d.min))
			.attr('stroke', ASSESS_GREEN)
			.attr('stroke-width', 1.25);

		g.append('line')
			.attr('x1', bw * 0.25)
			.attr('x2', bw * 0.75)
			.attr('y1', (d) => y(d.max))
			.attr('y2', (d) => y(d.max))
			.attr('stroke', ASSESS_GREEN)
			.attr('stroke-width', 1.25);

		g.append('rect')
			.attr('x', bw * 0.18)
			.attr('width', bw * 0.64)
			.attr('y', (d) => y(d.q3))
			.attr('height', (d) => Math.max(1, y(d.q1) - y(d.q3)))
			.attr('fill', ASSESS_GREEN)
			.attr('fill-opacity', 0.28)
			.attr('stroke', ASSESS_GREEN)
			.attr('stroke-width', 1.5);

		g.append('line')
			.attr('x1', bw * 0.18)
			.attr('x2', bw * 0.82)
			.attr('y1', (d) => y(d.median))
			.attr('y2', (d) => y(d.median))
			.attr('stroke', '#14532d')
			.attr('stroke-width', 2);

		g.append('title').text(
			(d) =>
				`${d.key}\nn=${d.count}\nmin ${d.min.toFixed(2)} · Q1 ${d.q1.toFixed(2)} · median ${d.median.toFixed(2)} · Q3 ${d.q3.toFixed(2)} · max ${d.max.toFixed(2)}`
		);
	}

	function drawHeat() {
		if (!heatEl) return;
		try {
			d3.select(heatEl).selectAll('*').remove();
			if (!calWindow) {
				d3.select(heatEl)
					.append('p')
					.attr('class', 'empty')
					.text(
						String(calFilterValue ?? '').trim()
							? 'No days match this filter.'
							: 'No collection dates.'
					);
				return;
			}

			const { start, end } = calWindow;
			const byKey = new Map(activity.map((d) => [d.key, d]));
			const days = d3.utcDays(start, end);
			const weekCount = Math.max(1, d3.utcWeek.count(start, d3.utcDay.offset(end, -1)) + 1);

			const avail = Math.max(420, heatEl.clientWidth || 560);
			const leftPad = 28;
			const topPad = 22;
			const gap = 2;
			const cell = Math.max(9, Math.min(15, Math.floor((avail - leftPad - 8) / weekCount) - gap));
			const width = leftPad + weekCount * (cell + gap);
			const height = topPad + 7 * (cell + gap) + 4;

			const maxCount = d3.max(activity, (d) => d.count) || 1;
			const color = d3.scaleQuantize().domain([0, maxCount]).range(GREEN_SCALE);

			const svg = d3
				.select(heatEl)
				.append('svg')
				.attr('width', '100%')
				.attr('viewBox', `0 0 ${width} ${height}`)
				.attr('preserveAspectRatio', 'xMidYMin meet')
				.style('max-width', '100%')
				.style('display', 'block');

			const tip = d3
				.select(heatEl)
				.append('div')
				.attr('class', 'heat-tip')
				.style('display', 'none');

			const monthNames = [
				'Jan',
				'Feb',
				'Mar',
				'Apr',
				'May',
				'Jun',
				'Jul',
				'Aug',
				'Sep',
				'Oct',
				'Nov',
				'Dec'
			];
			const monthMarks = [];
			for (let t = start.getTime(); t < end.getTime(); ) {
				const first = new Date(t);
				const label =
					first.getUTCMonth() === 0
						? `${monthNames[0]} ${String(first.getUTCFullYear()).slice(2)}`
						: monthNames[first.getUTCMonth()];
				monthMarks.push({
					label,
					x: d3.utcWeek.count(start, first) * (cell + gap)
				});
				t = Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 1);
			}

			svg
				.append('g')
				.attr('transform', `translate(${leftPad},0)`)
				.selectAll('text.month')
				.data(monthMarks)
				.join('text')
				.attr('class', 'month')
				.attr('x', (d) => d.x)
				.attr('y', 14)
				.attr('fill', '#56646f')
				.attr('font-size', 10)
				.attr('font-family', 'var(--font-body)')
				.text((d) => d.label);

			const g = svg.append('g').attr('transform', `translate(${leftPad},${topPad})`);
			const weekdays = ['M', '', 'W', '', 'F', '', ''];
			g.selectAll('text.wd')
				.data(weekdays)
				.join('text')
				.attr('x', -8)
				.attr('y', (_, i) => i * (cell + gap) + cell * 0.75)
				.attr('text-anchor', 'end')
				.attr('fill', '#6b7885')
				.attr('font-size', 9)
				.text((d) => d);

			g.selectAll('rect.day')
				.data(days)
				.join('rect')
				.attr('width', cell)
				.attr('height', cell)
				.attr('rx', 2)
				.attr('x', (d) => d3.utcWeek.count(start, d) * (cell + gap))
				.attr('y', (d) => ((d.getUTCDay() + 6) % 7) * (cell + gap))
				.attr('fill', (d) => {
					const key = d.toISOString().slice(0, 10);
					const hit = byKey.get(key);
					return hit ? color(hit.count) : '#eef1f4';
				})
				.on('mouseenter', (event, d) => {
					const key = d.toISOString().slice(0, 10);
					const hit = byKey.get(key);
					const val =
						hit?.value != null
							? `${calFilterLabel}: ${Number(hit.value).toFixed(2)}`
							: 'No reading';
					tip
						.style('display', 'block')
						.html(
							`<strong>${key}</strong><br/>${hit ? `${hit.count} submission${hit.count === 1 ? '' : 's'}` : 'No data'}<br/>${val}`
						);
					tip
						.style('left', `${event.clientX + 12}px`)
						.style('top', `${event.clientY + 12}px`);
				})
				.on('mousemove', (event) => {
					tip.style('left', `${event.clientX + 12}px`).style('top', `${event.clientY + 12}px`);
				})
				.on('mouseleave', () => tip.style('display', 'none'));
		} catch (err) {
			d3.select(heatEl).selectAll('*').remove();
			d3.select(heatEl)
				.append('p')
				.attr('class', 'empty')
				.text(`Calendar failed to render: ${err?.message || err}`);
		}
	}

	function panCalendar(deltaMonths) {
		if (calStartIdx == null || !panLimits) return;
		const next = clampCalendarWindow(calStartIdx + deltaMonths, calSpanMonths, panLimits);
		calStartIdx = next.startIdx;
		calSpanMonths = next.months;
	}

	function formatMetaValue(value) {
		const text = String(value ?? '').trim();
		if (!text) return '—';
		if (/^\d{4}-\d{2}-\d{2}T/.test(text)) {
			try {
				return new Date(text).toLocaleString(undefined, {
					year: 'numeric',
					month: 'short',
					day: 'numeric',
					hour: '2-digit',
					minute: '2-digit'
				});
			} catch {
				return text;
			}
		}
		return text;
	}
</script>

{#if section === 'about'}
	<section class="cell cell-about">
		{#if site}
			<p class="m-0 font-headline text-xs font-semibold tracking-wide text-[#16a34a] uppercase">Site</p>
			<h3 class="m-0 mt-1 font-display text-xl text-[#1a2530]">
				{site.lat.toFixed(5)}, {site.lon.toFixed(5)}
			</h3>
			<p class="m-0 mt-1 font-mono text-[11px] tracking-wide text-[#6b7885]">
				{site.rows.length} submission{site.rows.length === 1 ? '' : 's'}
			</p>
			{#if meta.length}
				<p class="m-0 mt-4 mb-2 font-headline text-xs font-semibold tracking-wide text-brand-navy/60 uppercase">
					About this location
				</p>
				<dl class="meta-grid m-0">
					{#each meta as item (item.name)}
						<div class="meta-card">
							<dt class="font-mono text-[11px] tracking-wide text-[#6b7885]">{item.label}</dt>
							<dd class="m-0 mt-0.5 font-body text-sm font-medium text-[#1a2530]">
								{formatMetaValue(item.value)}
							</dd>
						</div>
					{/each}
				</dl>
			{/if}
		{:else}
			<p class="m-0 font-headline text-xs font-semibold tracking-wide text-brand-navy/60 uppercase">Site</p>
			<p class="m-0 mt-2 font-body text-sm text-[#56646f]">Select a point on the map to view details.</p>
		{/if}
	</section>
{:else if section === 'bar'}
	<section class="cell cell-graph">
		{#if site}
			<p class="m-0 mb-2 font-headline text-xs font-semibold tracking-wide text-[#16a34a] uppercase">
				Bar chart
			</p>
			<div class="mb-3 grid gap-2 sm:grid-cols-2">
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Time on X axis</span>
					<select
						class={selectClass}
						value={timeGrain}
						onchange={(e) => onChange({ timeGrain: e.currentTarget.value })}
					>
						<option value="daily">Daily</option>
						<option value="weekly">Weekly</option>
						<option value="monthly">Monthly</option>
					</select>
				</label>
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Bar value (Y)</span>
					<select
						class={selectClass}
						value={barField}
						onchange={(e) => onChange({ barField: e.currentTarget.value })}
					>
						{#each numericFields as f (f.name)}
							<option value={f.name}>{f.label}</option>
						{/each}
					</select>
				</label>
			</div>
			<p class="m-0 mb-1 font-headline text-xs font-semibold tracking-wide text-brand-navy/60 uppercase">
				{barLabel}
			</p>
			<div bind:this={chartEl} class="chart-host"></div>
		{:else}
			<p class="m-0 font-body text-sm text-[#56646f]">Select a site to view the bar chart.</p>
		{/if}
	</section>
{:else if section === 'line'}
	<section class="cell cell-line">
		{#if site}
			<p class="m-0 mb-2 font-headline text-xs font-semibold tracking-wide text-[#16a34a] uppercase">
				Line chart
			</p>
			<div class="mb-3 grid gap-2 sm:grid-cols-2">
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Time on X axis</span>
					<select
						class={selectClass}
						value={lineTimeGrain}
						onchange={(e) => onChange({ lineTimeGrain: e.currentTarget.value })}
					>
						<option value="daily">Daily</option>
						<option value="weekly">Weekly</option>
						<option value="monthly">Monthly</option>
					</select>
				</label>
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Line value (Y)</span>
					<select
						class={selectClass}
						value={lineField || ''}
						onchange={(e) => onChange({ lineField: e.currentTarget.value })}
					>
						{#each numericFields as f (f.name)}
							<option value={f.name}>{f.label}</option>
						{/each}
					</select>
				</label>
			</div>
			<p class="m-0 mb-1 font-headline text-xs font-semibold tracking-wide text-brand-navy/60 uppercase">
				{lineLabel}
			</p>
			<div bind:this={lineEl} class="chart-host"></div>
		{:else}
			<p class="m-0 font-body text-sm text-[#56646f]">Select a site to view the line chart.</p>
		{/if}
	</section>
{:else if section === 'calendar'}
	<section class="cell cell-calendar">
		{#if site}
			<div class="mb-2 flex flex-wrap items-center justify-between gap-2">
				<p class="m-0 font-headline text-xs font-semibold tracking-wide text-[#16a34a] uppercase">
					Collection calendar
				</p>
				{#if calWindow}
					<div class="year-toggle">
						<button
							type="button"
							class="year-btn"
							disabled={!calWindow.canPanLeft}
							onclick={() => panCalendar(-1)}
							aria-label="Earlier months"
						>
							‹
						</button>
						<span class="year-label font-mono text-[12px]">{calWindow.label}</span>
						<button
							type="button"
							class="year-btn"
							disabled={!calWindow.canPanRight}
							onclick={() => panCalendar(1)}
							aria-label="Later months"
						>
							›
						</button>
					</div>
				{/if}
			</div>
			<div class="mb-3 grid gap-2 sm:grid-cols-3">
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Column</span>
					<select
						class={selectClass}
						value={calFilterField || barField || ''}
						onchange={(e) => (calFilterField = e.currentTarget.value || null)}
					>
						{#each numericFields as f (f.name)}
							<option value={f.name}>{f.label}</option>
						{/each}
					</select>
				</label>
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Compare</span>
					<select
						class={selectClass}
						value={calFilterOp}
						onchange={(e) => (calFilterOp = /** @type {'gt'|'lt'|'eq'} */ (e.currentTarget.value))}
					>
						<option value="gt">Greater than</option>
						<option value="lt">Less than</option>
						<option value="eq">Equal to</option>
					</select>
				</label>
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Value</span>
					<input
						class={selectClass}
						type="number"
						step="any"
						placeholder="All days"
						value={calFilterValue}
						oninput={(e) => (calFilterValue = e.currentTarget.value)}
					/>
				</label>
			</div>
			{#if String(calFilterValue ?? '').trim()}
				<p class="m-0 mb-2 font-body text-xs text-brand-steel">
					Showing days with {calFilterLabel}
					{calFilterOp === 'gt' ? ' > ' : calFilterOp === 'lt' ? ' < ' : ' = '}
					{calFilterValue}
				</p>
			{/if}
			<div bind:this={heatEl} class="heat-host relative"></div>
		{:else}
			<p class="m-0 font-body text-sm text-[#56646f]">Select a site to view the calendar.</p>
		{/if}
	</section>
{:else if section === 'box'}
	<section class="cell cell-box">
		{#if site}
			<p class="m-0 mb-2 font-headline text-xs font-semibold tracking-wide text-[#16a34a] uppercase">
				Box plot
			</p>
			<div class="mb-3 grid gap-2 sm:grid-cols-2">
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Time on X axis</span>
					<select
						class={selectClass}
						value={boxTimeGrain}
						onchange={(e) => onChange({ boxTimeGrain: e.currentTarget.value })}
					>
						<option value="daily">Daily</option>
						<option value="weekly">Weekly</option>
						<option value="monthly">Monthly</option>
					</select>
				</label>
				<label class="grid gap-1">
					<span class="font-body text-sm font-medium text-brand-navy">Box value (Y)</span>
					<select
						class={selectClass}
						value={boxField || ''}
						onchange={(e) => onChange({ boxField: e.currentTarget.value })}
					>
						{#each numericFields as f (f.name)}
							<option value={f.name}>{f.label}</option>
						{/each}
					</select>
				</label>
			</div>
			<p class="m-0 mb-1 font-headline text-xs font-semibold tracking-wide text-brand-navy/60 uppercase">
				{boxLabel}
			</p>
			<div bind:this={boxEl} class="chart-host"></div>
		{:else}
			<p class="m-0 font-body text-sm text-[#56646f]">Select a site to view the box plot.</p>
		{/if}
	</section>
{/if}

<style>
	.cell {
		min-width: 0;
		min-height: 0;
		overflow: auto;
		background: white;
		padding: 1rem 1.1rem;
		display: flex;
		flex-direction: column;
	}
	.meta-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.5rem;
	}
	.meta-card {
		border-radius: 0.75rem;
		border: 1px solid rgba(20, 40, 60, 0.08);
		background: #f8faf8;
		padding: 0.65rem 0.75rem;
	}
	.year-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.year-btn {
		display: inline-flex;
		height: 1.75rem;
		width: 1.75rem;
		align-items: center;
		justify-content: center;
		border: 1px solid rgba(20, 40, 60, 0.15);
		border-radius: 0.4rem;
		background: white;
		font-size: 1rem;
		line-height: 1;
		color: #1a2530;
		cursor: pointer;
	}
	.year-btn:disabled {
		opacity: 0.4;
		cursor: not-allowed;
	}
	.year-label {
		min-width: 8.5rem;
		text-align: center;
		color: #1a2530;
	}
	.cell-calendar {
		overflow: visible;
	}
	.chart-host,
	.heat-host {
		width: 100%;
		max-width: 100%;
		flex: 1;
		min-height: 150px;
	}
	.cell-line .chart-host,
	.cell-box .chart-host {
		margin-bottom: 0.75rem;
		min-height: 170px;
	}
	.heat-host {
		min-height: 180px;
		width: 100%;
		overflow: visible;
	}
	:global(.chart-host .empty),
	:global(.heat-host .empty) {
		margin: 0;
		padding: 0.75rem 0;
		font-size: 0.8rem;
		font-family: var(--font-body);
		color: #6b7885;
	}
	:global(.heat-host .heat-tip) {
		position: fixed;
		z-index: 40;
		pointer-events: none;
		padding: 0.4rem 0.55rem;
		border-radius: 8px;
		background: #1a2530;
		color: white;
		font-size: 11px;
		line-height: 1.35;
		box-shadow: 0 8px 20px -12px rgba(0, 0, 0, 0.45);
	}
	@media (max-width: 520px) {
		.meta-grid {
			grid-template-columns: 1fr;
		}
	}
</style>
