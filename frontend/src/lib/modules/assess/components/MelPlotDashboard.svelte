<script>
	import { goto } from '$app/navigation';
	import { onDestroy, onMount } from 'svelte';
	import * as d3 from 'd3';
	import maplibregl from 'maplibre-gl';
	import 'maplibre-gl/dist/maplibre-gl.css';
	import ModuleHeader from '$lib/shared/components/ModuleHeader.svelte';
	import { itemPath } from '$lib/shared/slug.js';
	import { assessCrumbs } from '$lib/modules/assess/breadcrumbs.js';
	import { fetchAssetDashboard } from '$lib/modules/assess/mel-api';
	import {
		autoCalendarRange,
		calendarPanLimits,
		clampCalendarWindow,
		dailyActivity,
		toDate
	} from '$lib/modules/assess/form-explore.js';

	/** @type {{ project: any, plan: any, assetId: string, projects?: any[] }} */
	let { project, plan, assetId, projects = [] } = $props();

	let loading = $state(true);
	let error = $state('');
	let data = $state(null);

	/** @type {HTMLElement | undefined} */
	let chartEl = $state();
	/** @type {HTMLElement | undefined} */
	let heatEl = $state();
	/** @type {HTMLElement | undefined} */
	let mapEl = $state();

	/** @type {number|null} */
	let calStartIdx = $state(null);
	let calSpanMonths = $state(12);
	let calWindowKey = $state('');
	/** @type {'collected'|'soil_moisture'} */
	let heatMetric = $state('collected');
	/** @type {string|null} */
	let processKey = $state(null);
	let showAssetInfo = $state(false);

	/** @type {maplibregl.Map | null} */
	let map = null;

	const SM_SCALE = ['#fef9c3', '#bbf7d0', '#4ade80', '#16a34a', '#14532d'];
	const COLLECTED_YES = '#166534';
	const COLLECTED_NO = '#eef1f4';

	const RIDGE_POINTS = [
		{ id: 'A', key: 'bm_cm_soil_moisture_raised_r_corner_a', x: 0.18, y: 0.22 },
		{ id: 'B', key: 'bm_cm_soil_moisture_raised_r_corner_b', x: 0.82, y: 0.22 },
		{ id: 'C', key: 'bm_cm_soil_moisture_raised_r_corner_c', x: 0.82, y: 0.78 },
		{ id: 'D', key: 'bm_cm_soil_moisture_raised_r_corner_d', x: 0.18, y: 0.78 },
		{ id: 'Centre', key: 'bm_cm_soil_moisture_raised_r_centre', x: 0.5, y: 0.5 }
	];
	const FURROW_POINTS = [
		{ id: 'A', key: 'bm_cm_soil_moisture_raised_f_corner_a', x: 0.18, y: 0.22 },
		{ id: 'B', key: 'bm_cm_soil_moisture_raised_f_corner_b', x: 0.82, y: 0.22 },
		{ id: 'C', key: 'bm_cm_soil_moisture_raised_f_corner_c', x: 0.82, y: 0.78 },
		{ id: 'D', key: 'bm_cm_soil_moisture_raised_f_corner_d', x: 0.18, y: 0.78 },
		{ id: 'Centre', key: 'bm_cm_soil_moisture_raised_f_centre', x: 0.5, y: 0.5 }
	];
	const FLAT_POINTS = [
		{ id: 'A', key: 'bm_cm_soil_moisture_flat_corner_a', x: 0.18, y: 0.22 },
		{ id: 'B', key: 'bm_cm_soil_moisture_flat_corner_b', x: 0.82, y: 0.22 },
		{ id: 'C', key: 'bm_cm_soil_moisture_flat_corner_c', x: 0.82, y: 0.78 },
		{ id: 'D', key: 'bm_cm_soil_moisture_flat_corner_d', x: 0.18, y: 0.78 },
		{ id: 'Centre', key: 'bm_cm_soil_moisture_flat_centre', x: 0.5, y: 0.5 }
	];

	const slugBase = $derived(itemPath('/assess', project, projects));
	const crumbs = $derived(
		assessCrumbs({
			projects,
			project,
			plan,
			tail: [{ label: data?.asset?.label || 'Farm plot' }]
		})
	);

	const series = $derived(data?.visual?.series || []);
	const ot = $derived(data?.asset?.ot_answers || {});
	const calcs = $derived(data?.calculations || {});
	const layout = $derived(calcs.plot_layout || data?.visual?.plot_layout || 'flat');
	const latestSm = $derived(series.length ? series[series.length - 1] : null);
	const latestPoints = $derived(calcs.latest_sm_points || data?.visual?.latest_sm_points || {});

	const location = $derived.by(() => {
		const raw = String(ot.bm_ot_location || '').trim();
		let lat = null;
		let lon = null;
		if (raw) {
			const parts = raw
				.split(/[,\s]+/)
				.map((p) => Number(p))
				.filter((n) => !Number.isNaN(n));
			if (parts.length >= 2) {
				lat = parts[0];
				lon = parts[1];
			}
		}
		const place = [ot.bm_ot_village_name, ot.bm_ot_block_name, ot.bm_ot_district_name]
			.map((v) => String(v || '').trim())
			.filter(Boolean);
		return {
			lat,
			lon,
			coordsLabel:
				lat != null && lon != null ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : raw || null,
			placeLabel: place.length ? place.join(' · ') : null,
			farmer: String(ot.bm_ot_farmer_name || '').trim() || null,
			crop: String(ot.bm_ot_crop_grown || '').trim() || null,
			season: String(ot.bm_ot_agriculture_season || '').trim() || null
		};
	});

	const heatValueField = $derived(heatMetric === 'soil_moisture' ? 'sm_plot_pct' : null);
	const heatScale = $derived(heatMetric === 'soil_moisture' ? SM_SCALE : null);
	const heatMetricLabel = $derived(heatMetric === 'soil_moisture' ? 'Soil moisture' : 'Record collected');
	const heatUnit = $derived(heatMetric === 'soil_moisture' ? '%' : '');

	const activity = $derived(
		dailyActivity(
			series.map((p) => ({
				date: p.date,
				sm_plot_pct: p.sm_plot_pct ?? p.sm_t_pct ?? p.sm_c_pct
			})),
			{ dateField: 'date', valueField: heatValueField }
		)
	);

	const calcCardsByVar = $derived.by(() => {
		/** @type {Record<string, any>} */
		const map = {};
		for (const c of data?.calculation_cards || []) {
			if (c?.variable) map[c.variable] = c;
		}
		return map;
	});

	const smStats = $derived.by(() => {
		const diffs = series.map((p) => p.sm_diff_pct).filter((v) => v != null).map(Number);
		const pairedDates = series.filter((p) => p.sm_t_pct != null && p.sm_c_pct != null).length;
		const smPts = series.filter((p) => p.sm_plot_pct != null || p.sm_t_pct != null || p.sm_c_pct != null).length;
		return { n: series.length, smPts, diffs: diffs.length, pairedDates };
	});

	const hasTcPair = $derived(series.some((p) => p.sm_t_pct != null && p.sm_c_pct != null));
	const latestT = $derived(latestSm?.sm_t_pct ?? null);
	const latestC = $derived(latestSm?.sm_c_pct ?? null);

	const plotLabels = $derived.by(() => {
		const cards = calcCardsByVar;
		const area = calcs.area_under_crop;
		const unit = calcs.area_unit || 'acre';
		const areaM2 = calcs.area_m2;
		const smDiff = calcs.sm_diff_pct;
		const smPer = calcs.sm_diff_per_unit_area_pct;
		const savings = calcs.sm_water_savings_m3;
		const rz = calcs.root_zone_depth_m ?? 0.4;
		const pairLabel = hasTcPair
			? `${smStats.pairedDates} paired dates`
			: layout === 'raised'
				? 'Ridge vs furrow on this plot'
				: 'No paired control';

		return [
			{
				key: 'sm_diff',
				label: 'SM difference',
				value: smDiff,
				unit: '%',
				icon: 'wl',
				formula: 'average(SM_Tn − SM_Cn)',
				description:
					cards.sm_diff_pct?.description ||
					'Average soil-moisture difference (%) between treatment and control observation points.',
				how:
					cards.sm_diff_pct?.methodology ||
					'For flat plots use SM_diff (%) = average(SM_Tn − SM_Cn) across paired observation points. For raised beds compute ridge and furrow median diffs then average them. Control readings are paired by asset/date against treatment readings.',
				raws: [pairLabel, `${smStats.smPts} SM readings`]
			},
			{
				key: 'sm_per',
				label: 'SM diff / area',
				value: smPer,
				unit: `% / ${unit}`,
				icon: 'fill',
				formula: 'SM difference ÷ plot area',
				description:
					cards.sm_diff_per_unit_area_pct?.description ||
					'Normalizes treatment-vs-control soil-moisture difference by treated plot area.',
				how:
					cards.sm_diff_per_unit_area_pct?.methodology ||
					'Compute SM_diff (%) as above. Divide by treated plot area from the one-time survey (acre or bigha; 1 bigha ≈ 2529 m²).',
				raws: [`SM diff ${fmt(smDiff)} %`, `Area ${fmt(area)} ${unit}`]
			},
			{
				key: 'savings',
				label: 'SM water savings',
				value: savings,
				unit: 'm³',
				icon: 'cube',
				formula: '0.40 m × area (m²) × SM_diff / 100',
				description:
					cards.sm_water_savings_m3?.description ||
					'Converts soil-moisture difference into volumetric water retained in the root zone.',
				how:
					cards.sm_water_savings_m3?.methodology ||
					'Convert plot area to m² (1 bigha ≈ 2529 m²). Apply a 40 cm root-zone depth. SM water savings (m³) = root-zone depth × area × SM difference as a fraction.',
				raws: [`Root zone ${fmt(rz, 2)} m`, `Area ${fmt(areaM2)} m²`, `SM diff ${fmt(smDiff)} %`]
			}
		];
	});

	const processItem = $derived(
		processKey ? plotLabels.find((p) => p.key === processKey) || null : null
	);

	const kpiPct = $derived(
		calcs.volumetric_savings_kpi_progress_pct != null
			? Math.max(0, Number(calcs.volumetric_savings_kpi_progress_pct))
			: null
	);

	const panLimits = $derived(calendarPanLimits(series, 'date'));

	const calWindow = $derived.by(() => {
		if (calStartIdx == null || !panLimits) return null;
		return clampCalendarWindow(calStartIdx, calSpanMonths, panLimits);
	});

	const plotGeom = $derived.by(() => {
		const raised = layout === 'raised';
		const planW = 300;
		const planH = 170;
		const pad = 18;
		const split = raised ? (planW - pad * 2 - 10) / 2 : planW - pad * 2;
		const boxH = planH - 42;
		const ridgeBox = { x: pad, y: 16, w: raised ? split : planW - pad * 2, h: boxH };
		const furrowBox = raised
			? { x: pad + split + 10, y: 16, w: split, h: boxH }
			: null;
		const mapPts = (box, defs) =>
			defs.map((p) => ({
				...p,
				cx: box.x + p.x * box.w,
				cy: box.y + p.y * box.h,
				value: numOrNull(latestPoints[p.key])
			}));
		return {
			planW,
			planH,
			raised,
			ridgeBox,
			furrowBox,
			ridgePts: mapPts(ridgeBox, raised ? RIDGE_POINTS : FLAT_POINTS),
			furrowPts: furrowBox ? mapPts(furrowBox, FURROW_POINTS) : []
		};
	});

	$effect(() => {
		const key = `${series[0]?.date || ''}|${series[series.length - 1]?.date || ''}|${series.length}`;
		const limits = calendarPanLimits(series, 'date');
		if (!limits) {
			if (calWindowKey !== key) {
				calStartIdx = null;
				calWindowKey = key;
			}
			return;
		}
		if (key === calWindowKey && calStartIdx != null) return;

		const auto = autoCalendarRange(activity);
		if (!auto) {
			calStartIdx = null;
			calWindowKey = key;
			return;
		}
		const next = clampCalendarWindow(auto.startIdx, auto.months, limits);
		calStartIdx = next.startIdx;
		calSpanMonths = next.months;
		calWindowKey = key;
	});

	onMount(load);

	onDestroy(() => {
		if (chartEl) d3.select(chartEl).selectAll('*').remove();
		if (heatEl) d3.select(heatEl).selectAll('*').remove();
		if (map) {
			map.remove();
			map = null;
		}
	});

	$effect(() => {
		if (!chartEl || loading || error) return;
		series;
		const ro = new ResizeObserver(() => drawChart());
		ro.observe(chartEl);
		drawChart();
		return () => ro.disconnect();
	});

	$effect(() => {
		if (!heatEl || loading || error) return;
		activity;
		calWindow;
		heatMetric;
		const ro = new ResizeObserver(() => drawHeat());
		ro.observe(heatEl);
		drawHeat();
		return () => ro.disconnect();
	});

	$effect(() => {
		if (!mapEl || loading || error) return;
		const { lat, lon } = location;
		if (lat == null || lon == null) {
			if (map) {
				map.remove();
				map = null;
			}
			return;
		}

		if (!map) {
			map = new maplibregl.Map({
				container: mapEl,
				style: {
					version: 8,
					sources: {
						osm: {
							type: 'raster',
							tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
							tileSize: 256,
							attribution: '© OpenStreetMap'
						}
					},
					layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
				},
				center: [lon, lat],
				zoom: 13,
				interactive: true
			});
			map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
			map.on('load', () => ensureMarker(lat, lon));
		} else {
			map.setCenter([lon, lat]);
			ensureMarker(lat, lon);
		}

		const ro = new ResizeObserver(() => {
			map?.resize();
		});
		ro.observe(mapEl);
		queueMicrotask(() => map?.resize());

		return () => ro.disconnect();
	});

	async function load() {
		loading = true;
		error = '';
		try {
			data = await fetchAssetDashboard(project.id, plan.id, assetId);
		} catch (err) {
			error = String(err);
		} finally {
			loading = false;
		}
	}

	function fmt(v, digits = 2) {
		if (v == null || Number.isNaN(Number(v))) return '—';
		return Number(v).toLocaleString(undefined, { maximumFractionDigits: digits });
	}

	function numOrNull(v) {
		if (v == null || v === '') return null;
		const n = Number(v);
		return Number.isFinite(n) ? n : null;
	}

	function smColor(v) {
		if (v == null || Number.isNaN(Number(v))) return '#d6d3d1';
		const t = Math.max(0, Math.min(1, Number(v) / 30));
		return d3.interpolateRgb('#fde68a', '#166534')(t);
	}

	function humanizeOtKey(key) {
		return String(key || '')
			.replace(/^bm_ot_/, '')
			.replace(/_+$/g, '')
			.replace(/_/g, ' ')
			.replace(/\b\w/g, (c) => c.toUpperCase());
	}

	function fmtOtValue(v) {
		if (v == null || v === '') return '—';
		if (Array.isArray(v)) return v.length ? v.join(', ') : '—';
		if (typeof v === 'boolean') return v ? 'Yes' : 'No';
		if (typeof v === 'object') {
			try {
				return JSON.stringify(v);
			} catch {
				return String(v);
			}
		}
		return String(v);
	}

	const assetInfoRows = $derived.by(() => {
		const entries = Object.entries(ot || {}).filter(([, v]) => v != null && v !== '');
		entries.sort(([a], [b]) => a.localeCompare(b));
		return entries.map(([key, value]) => ({
			key,
			label: humanizeOtKey(key),
			value: fmtOtValue(value)
		}));
	});

	function ensureMarker(lat, lon) {
		if (!map) return;
		const id = 'asset-point';
		const src = {
			type: 'FeatureCollection',
			features: [
				{
					type: 'Feature',
					geometry: { type: 'Point', coordinates: [lon, lat] },
					properties: {}
				}
			]
		};
		if (map.getSource(id)) {
			/** @type {any} */ (map.getSource(id)).setData(src);
			return;
		}
		map.addSource(id, { type: 'geojson', data: src });
		map.addLayer({
			id: `${id}-circle`,
			type: 'circle',
			source: id,
			paint: {
				'circle-radius': 8,
				'circle-color': '#166534',
				'circle-stroke-width': 2,
				'circle-stroke-color': '#ffffff'
			}
		});
	}

	function panCalendar(deltaMonths) {
		if (calStartIdx == null || !panLimits) return;
		const next = clampCalendarWindow(calStartIdx + deltaMonths, calSpanMonths, panLimits);
		calStartIdx = next.startIdx;
		calSpanMonths = next.months;
	}

	function drawChart() {
		if (!chartEl) return;
		d3.select(chartEl).selectAll('*').remove();

		if (!series.length) {
			d3.select(chartEl)
				.append('p')
				.attr('class', 'empty')
				.text('No CM soil-moisture readings yet.');
			return;
		}

		const width = Math.max(280, chartEl.clientWidth || 480);
		const height = Math.max(180, Math.min(340, chartEl.clientHeight || 240));
		const margin = { top: 28, right: 18, bottom: 44, left: 48 };

		const parsed = series
			.map((p) => ({
				...p,
				_date: toDate(p.date)
			}))
			.filter((p) => p._date);

		if (!parsed.length) {
			d3.select(chartEl).append('p').attr('class', 'empty').text('No dated readings to chart.');
			return;
		}

		const sms = parsed.flatMap((p) => [p.sm_t_pct, p.sm_c_pct]).filter((v) => v != null);
		const maxSm = Math.max(30, ...(sms.length ? sms : [30]));
		const hasT = parsed.some((d) => d.sm_t_pct != null);
		const hasC = parsed.some((d) => d.sm_c_pct != null);

		const x = d3
			.scaleUtc()
			.domain(d3.extent(parsed, (d) => d._date))
			.range([margin.left, width - margin.right]);
		const ySm = d3
			.scaleLinear()
			.domain([0, maxSm])
			.range([height - margin.bottom, margin.top]);

		const svg = d3
			.select(chartEl)
			.append('svg')
			.attr('width', '100%')
			.attr('viewBox', `0 0 ${width} ${height}`)
			.attr('preserveAspectRatio', 'xMidYMid meet')
			.style('display', 'block')
			.style('max-width', '100%');

		const tip = d3
			.select(chartEl)
			.append('div')
			.attr('class', 'chart-tip')
			.style('display', 'none');

		svg
			.append('g')
			.attr('class', 'grid')
			.attr('transform', `translate(${margin.left},0)`)
			.call(
				d3
					.axisLeft(ySm)
					.ticks(6)
					.tickSize(-(width - margin.left - margin.right))
					.tickFormat(() => '')
			)
			.call((g) => g.select('.domain').remove())
			.call((g) => g.selectAll('line').attr('stroke', '#e5e7eb'));

		const xTicks = Math.min(10, Math.max(4, Math.floor(parsed.length / 2) + 1));
		svg
			.append('g')
			.attr('transform', `translate(0,${height - margin.bottom})`)
			.call(
				d3
					.axisBottom(x)
					.ticks(xTicks)
					.tickFormat(/** @type {any} */ (d3.utcFormat('%d-%m-%Y')))
			)
			.call((g) => g.select('.domain').attr('stroke', '#c5ced6'))
			.selectAll('text')
			.attr('fill', '#4b6b8a')
			.style('font-size', '10px')
			.attr('transform', 'rotate(-35)')
			.style('text-anchor', 'end');

		svg
			.append('g')
			.attr('transform', `translate(${margin.left},0)`)
			.call(d3.axisLeft(ySm).ticks(6).tickFormat((d) => String(d)))
			.call((g) => g.select('.domain').attr('stroke', '#c5ced6'))
			.selectAll('text')
			.attr('fill', '#3b4a58')
			.style('font-size', '10px');

		svg
			.append('text')
			.attr('transform', `rotate(-90)`)
			.attr('x', -(margin.top + (height - margin.top - margin.bottom) / 2))
			.attr('y', 14)
			.attr('fill', '#3b4a58')
			.attr('font-size', 11)
			.attr('font-weight', 600)
			.attr('text-anchor', 'middle')
			.text('Soil moisture (%)');

		svg
			.append('text')
			.attr('x', (margin.left + width - margin.right) / 2)
			.attr('y', height - 4)
			.attr('text-anchor', 'middle')
			.attr('fill', '#3b4a58')
			.attr('font-size', 11)
			.text('Date');

		const tColor = '#3f7d3f';
		const cColor = '#2563eb';
		const tPts = parsed.filter((d) => d.sm_t_pct != null);
		const cPts = parsed.filter((d) => d.sm_c_pct != null);

		if (hasT) {
			const tLine = d3
				.line()
				.x((d) => x(d._date))
				.y((d) => ySm(d.sm_t_pct))
				.curve(d3.curveLinear);
			svg
				.append('path')
				.datum(tPts)
				.attr('fill', 'none')
				.attr('stroke', tColor)
				.attr('stroke-width', 2.2)
				.attr('d', tLine);
			svg
				.append('g')
				.selectAll('circle.sm-t')
				.data(tPts)
				.join('circle')
				.attr('cx', (d) => x(d._date))
				.attr('cy', (d) => ySm(d.sm_t_pct))
				.attr('r', 2.6)
				.attr('fill', tColor);
		}

		if (hasC) {
			const cLine = d3
				.line()
				.x((d) => x(d._date))
				.y((d) => ySm(d.sm_c_pct))
				.curve(d3.curveLinear);
			svg
				.append('path')
				.datum(cPts)
				.attr('fill', 'none')
				.attr('stroke', cColor)
				.attr('stroke-width', 2.2)
				.attr('d', cLine);
			svg
				.append('g')
				.selectAll('circle.sm-c')
				.data(cPts)
				.join('circle')
				.attr('cx', (d) => x(d._date))
				.attr('cy', (d) => ySm(d.sm_c_pct))
				.attr('r', 2.6)
				.attr('fill', cColor);
		}

		const focus = svg.append('g').style('display', 'none');
		focus
			.append('line')
			.attr('class', 'guide')
			.attr('y1', margin.top)
			.attr('y2', height - margin.bottom)
			.attr('stroke', '#1a2530')
			.attr('stroke-opacity', 0.35)
			.attr('stroke-dasharray', '3 3');
		const focusT = focus
			.append('circle')
			.attr('r', 4.5)
			.attr('fill', tColor)
			.attr('stroke', '#fff')
			.attr('stroke-width', 1.4);
		const focusC = focus
			.append('circle')
			.attr('r', 4.5)
			.attr('fill', cColor)
			.attr('stroke', '#fff')
			.attr('stroke-width', 1.4);

		const bisect = d3.bisector((d) => d._date).center;
		svg
			.append('rect')
			.attr('fill', 'transparent')
			.attr('x', margin.left)
			.attr('y', margin.top)
			.attr('width', width - margin.left - margin.right)
			.attr('height', height - margin.top - margin.bottom)
			.style('cursor', 'crosshair')
			.on('mouseenter', () => {
				focus.style('display', null);
				tip.style('display', 'block');
			})
			.on('mouseleave', () => {
				focus.style('display', 'none');
				tip.style('display', 'none');
			})
			.on('mousemove', (event) => {
				const [mx] = d3.pointer(event);
				const date = x.invert(mx);
				const i = bisect(parsed, date);
				const d = parsed[Math.max(0, Math.min(parsed.length - 1, i))];
				if (!d) return;
				const cx = x(d._date);
				focus.select('.guide').attr('x1', cx).attr('x2', cx);
				if (d.sm_t_pct != null) {
					focusT.style('display', null).attr('cx', cx).attr('cy', ySm(d.sm_t_pct));
				} else {
					focusT.style('display', 'none');
				}
				if (d.sm_c_pct != null) {
					focusC.style('display', null).attr('cx', cx).attr('cy', ySm(d.sm_c_pct));
				} else {
					focusC.style('display', 'none');
				}
				const dateLabel = d3.utcFormat('%d %b %Y')(d._date);
				tip.html(
					`<strong>${dateLabel}</strong><br/>` +
						`T: <strong>${d.sm_t_pct != null ? fmt(d.sm_t_pct) + ' %' : '—'}</strong><br/>` +
						`C: <strong>${d.sm_c_pct != null ? fmt(d.sm_c_pct) + ' %' : '—'}</strong>` +
						(d.sm_diff_pct != null ? `<br/>SM diff: <strong>${fmt(d.sm_diff_pct)} %</strong>` : '')
				);
				tip.style('left', `${event.clientX + 14}px`).style('top', `${event.clientY + 14}px`);
			});
	}

	function drawHeat() {
		if (!heatEl) return;
		try {
			d3.select(heatEl).selectAll('*').remove();
			if (!calWindow) {
				d3.select(heatEl).append('p').attr('class', 'empty').text('No collection dates.');
				return;
			}

			const { start, end } = calWindow;
			const byKey = new Map(activity.map((d) => [d.key, d]));
			const days = d3.utcDays(start, end);
			const weekCount = Math.max(1, d3.utcWeek.count(start, d3.utcDay.offset(end, -1)) + 1);

			const availW = Math.max(200, heatEl.clientWidth || 400);
			const availH = Math.max(140, heatEl.clientHeight || 160);
			const leftPad = 28;
			const topPad = 22;
			const gap = 3;
			const cellW = Math.max(10, (availW - leftPad - 6) / weekCount - gap);
			const cellH = Math.max(10, (availH - topPad - 4) / 7 - gap);
			const width = leftPad + weekCount * (cellW + gap);
			const height = topPad + 7 * (cellH + gap);

			const valueVals = activity
				.map((d) => d.value)
				.filter((v) => v != null && !Number.isNaN(v));
			const minVal = valueVals.length ? /** @type {number} */ (d3.min(valueVals)) : 0;
			const maxVal = valueVals.length ? /** @type {number} */ (d3.max(valueVals)) : 1;
			const color =
				heatMetric === 'collected'
					? null
					: d3
							.scaleQuantize()
							.domain([
								minVal === maxVal ? minVal - 0.01 : minVal,
								maxVal === minVal ? maxVal + 0.01 : maxVal
							])
							.range(/** @type {string[]} */ (heatScale));

			const svg = d3
				.select(heatEl)
				.append('svg')
				.attr('width', '100%')
				.attr('height', '100%')
				.attr('viewBox', `0 0 ${width} ${height}`)
				.attr('preserveAspectRatio', 'xMinYMin meet')
				.style('display', 'block');

			const tip = d3
				.select(heatEl)
				.append('div')
				.attr('class', 'heat-tip')
				.style('display', 'none');

			const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
			const monthMarks = [];
			for (let t = start.getTime(); t < end.getTime(); ) {
				const first = new Date(t);
				const label =
					first.getUTCMonth() === 0
						? `${monthNames[0]} ${String(first.getUTCFullYear()).slice(2)}`
						: monthNames[first.getUTCMonth()];
				monthMarks.push({
					label,
					x: d3.utcWeek.count(start, first) * (cellW + gap)
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
				.attr('font-size', Math.max(10, Math.min(13, cellH * 0.45)))
				.text((d) => d.label);

			const g = svg.append('g').attr('transform', `translate(${leftPad},${topPad})`);
			const weekdays = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
			g.selectAll('text.wd')
				.data(weekdays)
				.join('text')
				.attr('x', -8)
				.attr('y', (_, i) => i * (cellH + gap) + cellH * 0.72)
				.attr('text-anchor', 'end')
				.attr('fill', '#6b7885')
				.attr('font-size', Math.max(9, Math.min(12, cellH * 0.4)))
				.text((d) => d);

			g.selectAll('rect.day')
				.data(days)
				.join('rect')
				.attr('width', cellW)
				.attr('height', cellH)
				.attr('rx', Math.min(4, cellW, cellH) * 0.22)
				.attr('x', (d) => d3.utcWeek.count(start, d) * (cellW + gap))
				.attr('y', (d) => ((d.getUTCDay() + 6) % 7) * (cellH + gap))
				.attr('fill', (d) => {
					const key = d.toISOString().slice(0, 10);
					const hit = byKey.get(key);
					if (heatMetric === 'collected') return hit ? COLLECTED_YES : COLLECTED_NO;
					if (!hit || hit.value == null) return COLLECTED_NO;
					return /** @type {(v: number) => string} */ (color)(hit.value);
				})
				.on('mouseenter', (event, d) => {
					const key = d.toISOString().slice(0, 10);
					const hit = byKey.get(key);
					const point = series.find((p) => p.date === key);
					let metricLine = '';
					if (heatMetric === 'collected') {
						metricLine = hit
							? '<strong>Record collected: Yes</strong>'
							: '<strong>Record collected: No</strong>';
					} else {
						metricLine =
							hit?.value != null
								? `${heatMetricLabel}: <strong>${fmt(hit.value)} ${heatUnit}</strong>`
								: `${heatMetricLabel}: —`;
					}
					const detail = point
						? `T ${point.sm_t_pct != null ? fmt(point.sm_t_pct) + ' %' : '—'} · C ${
								point.sm_c_pct != null ? fmt(point.sm_c_pct) + ' %' : '—'
							}`
						: 'No reading';
					tip
						.style('display', 'block')
						.html(
							`<strong>${key}</strong><br/>${metricLine}<br/>${
								hit ? `${hit.count} reading${hit.count === 1 ? '' : 's'}` : 'No data'
							}<br/>${detail}`
						);
					tip.style('left', `${event.clientX + 12}px`).style('top', `${event.clientY + 12}px`);
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
</script>

<div class="dash-page bg-transparent font-body">
	<ModuleHeader title="Assess" titleHref="/assess" wide {crumbs}>
		<button
			type="button"
			onclick={() =>
				goto(`${slugBase}/plans/${plan.id}/new?assets=1&asset=${encodeURIComponent(assetId)}`)}
			>Edit farm plot</button
		>
		<button type="button" onclick={() => goto(`${slugBase}/plans/${plan.id}`)}>Back to intervention</button>
	</ModuleHeader>

	<main class="dash-main">
		{#if loading}
			<p class="m-0 self-center text-brand-steel">Loading plot dashboard…</p>
		{:else if error}
			<p class="m-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
		{:else}
			<div class="dash-body">
				<div class="dash-grid">
					<section class="dash-col dash-info">
						<div class="dash-card dash-card-fill info-card">
							<div class="map-identity">
								<div class="loc-badge loc-badge-plot" aria-hidden="true">
									<svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"
										><path d="M8 1.5C5.5 1.5 3.5 3.6 3.5 6.2c0 3.4 3.6 7.5 4.2 8.1.2.2.5.2.6 0 .6-.6 4.2-4.7 4.2-8.1C12.5 3.6 10.5 1.5 8 1.5zm0 7a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"
									/></svg>
								</div>
								<div class="loc-text">
									<p class="info-kicker">Farm plot</p>
									<h1 class="info-title">{data.asset?.label || 'Farm plot'}</h1>
									{#if location.coordsLabel || location.placeLabel}
										<p class="info-sub">
											{#if location.coordsLabel}<span class="info-coords">{location.coordsLabel}</span>{/if}
											{#if location.coordsLabel && location.placeLabel}<span class="info-sep"> · </span>{/if}
											{#if location.placeLabel}<span class="info-place">{location.placeLabel}</span>{/if}
										</p>
									{/if}
								</div>
							</div>

							<dl class="info-list">
								{#if location.farmer}
									<div class="info-row">
										<dt class="info-dt">
											<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
												><path fill="currentColor" d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm0 1.5c-2.5 0-4.5 1.3-4.5 3V14h9v-1.5c0-1.7-2-3-4.5-3z"
											/></svg>
											Farmer
										</dt>
										<dd class="info-dd">{location.farmer}</dd>
									</div>
								{/if}
								{#if location.crop || location.season}
									<div class="info-row">
										<dt class="info-dt">
											<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
												><path fill="currentColor" d="M8 1.2C5.8 3.8 4 5.9 4 8a4 4 0 1 0 8 0c0-2.1-1.8-4.2-4-6.8z"
											/></svg>
											Crop
										</dt>
										<dd class="info-dd">{[location.crop, location.season].filter(Boolean).join(' · ')}</dd>
									</div>
								{/if}
								<div class="info-row">
									<dt class="info-dt">
										<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
											><path fill="currentColor" d="M2 3h12v2H2V3zm0 4h12v2H2V7zm0 4h8v2H2v-2z"
										/></svg>
										Readings
									</dt>
									<dd class="info-dd">{data.reading_count ?? series.length}</dd>
								</div>
								{#if calcs.area_under_crop != null}
									<div class="info-row">
										<dt class="info-dt">
											<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
												><rect x="2.5" y="2.5" width="11" height="11" rx="1" stroke="currentColor" stroke-width="1.4" fill="none"
											/></svg>
											Plot area
										</dt>
										<dd class="info-dd">
											{fmt(calcs.area_under_crop)} {calcs.area_unit || ''}
											{#if calcs.area_m2 != null}<span class="info-place"> · {fmt(calcs.area_m2)} m²</span>{/if}
										</dd>
									</div>
								{/if}
								<div class="info-row">
									<dt class="info-dt">
										<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
											><path fill="currentColor" d="M2 12h12v2H2v-2zM3 8h2v3H3V8zm4-4h2v7H7V4zm4 2h2v5h-2V6z"
										/></svg>
										Layout
									</dt>
									<dd class="info-dd">{layout === 'raised' ? 'Raised bed' : 'Flat plot'}</dd>
								</div>
							</dl>

							<button type="button" class="asset-info-btn" onclick={() => (showAssetInfo = true)}>
								View full plot information
							</button>

							<div class="panel-head map-inline-head">
								<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
									><path fill="currentColor" d="M8 1.5C5.5 1.5 3.5 3.6 3.5 6.2c0 3.4 3.6 7.5 4.2 8.1.2.2.5.2.6 0 .6-.6 4.2-4.7 4.2-8.1C12.5 3.6 10.5 1.5 8 1.5zm0 7a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"
								/></svg>
								<h2 class="panel-title">Location map</h2>
							</div>
							<div class="map-frame">
								{#if location.lat != null && location.lon != null}
									<div bind:this={mapEl} class="map-host"></div>
								{:else}
									<div class="map-fallback">No coordinates available.</div>
								{/if}
							</div>
							<div class="map-legend">
								<span class="legend-item"><span class="legend-dot legend-dot-plot"></span> Farm plot</span>
							</div>
						</div>
					</section>

					<section class="dash-col dash-vis">
						<div class="dash-card dash-card-fill stats-card">
							<div class="panel-head">
								<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
									><path fill="currentColor" d="M2 3h12v2H2V3zm0 4h12v2H2V7zm0 4h8v2H2v-2z"
								/></svg>
								<h2 class="panel-title">Summary statistics</h2>
							</div>
							<ul class="pond-metrics">
								{#each plotLabels as item (item.key)}
									<li class="pond-metric" class:pond-metric-kpi={item.key === 'kpi'} data-key={item.key}>
										<div class="metric-head">
											<div class="metric-top">
												{#if item.key === 'kpi' && kpiPct != null}
													<svg class="kpi-ring metric-ring" viewBox="0 0 36 36" aria-hidden="true">
														<circle class="kpi-ring-bg" cx="18" cy="18" r="14" />
														<circle
															class="kpi-ring-fg"
															cx="18"
															cy="18"
															r="14"
															pathLength="100"
															stroke-dasharray="{Math.min(100, kpiPct)} 100"
														/>
													</svg>
												{:else}
													<span class="metric-ico" data-icon={item.icon} aria-hidden="true"></span>
												{/if}
												<span class="pond-metric-label">{item.label}</span>
											</div>
											<span class="pond-metric-value">
												{fmt(item.value)}{item.unit ? ` ${item.unit}` : ''}
											</span>
										</div>
										{#if item.key === 'kpi' && kpiPct != null}
											<div class="kpi-bar" aria-hidden="true">
												<span style="width: {Math.min(100, kpiPct)}%"></span>
											</div>
										{/if}
										<p class="metric-formula"><span class="metric-k">Formula</span> {item.formula}</p>
										{#if item.raws?.length}
											<p class="metric-raws">
												<span class="metric-k">Inputs</span>
												{item.raws.join(' · ')}
											</p>
										{/if}
										<button
											type="button"
											class="metric-know-more"
											aria-expanded={processKey === item.key}
											onclick={() => (processKey = processKey === item.key ? null : item.key)}
										>
											Know more
										</button>
									</li>
								{/each}
							</ul>
						</div>
					</section>

					<div class="dash-col dash-charts">
						<div class="dash-card dims-row-card">
							<div class="panel-head panel-head-spread">
								<div class="panel-head">
									<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
										><rect x="2" y="2" width="12" height="12" rx="1.5" stroke="currentColor" stroke-width="1.4" fill="none"
									/></svg>
									<h2 class="panel-title">Soil moisture layout</h2>
								</div>
								<div class="dims-legend">
									{#if plotGeom.raised}
										<span class="dims-leg"><span class="dims-swatch dims-swatch-ridge"></span> Ridge (T)</span>
										<span class="dims-leg"><span class="dims-swatch dims-swatch-furrow"></span> Furrow (C)</span>
									{:else}
										<span class="dims-leg"><span class="dims-swatch dims-swatch-flat"></span> Flat plot</span>
									{/if}
									<span class="dims-leg">Points coloured by latest SM %</span>
								</div>
							</div>
							<div class="pond-diagrams-row">
								<div class="pond-diagram-box">
									<svg class="pond-svg" viewBox="0 0 {plotGeom.planW} {plotGeom.planH}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Plot plan">
										<rect x={plotGeom.ridgeBox.x} y={plotGeom.ridgeBox.y} width={plotGeom.ridgeBox.w} height={plotGeom.ridgeBox.h} rx="6" fill={plotGeom.raised ? '#dcfce7' : '#ecfccb'} stroke="#14532d" stroke-width="1.6"/>
										<text x={plotGeom.ridgeBox.x + 8} y={plotGeom.ridgeBox.y + 14} fill="#14532d" font-size="9" font-weight="700">{plotGeom.raised ? 'Ridge' : 'Plot'}</text>
										{#each plotGeom.ridgePts as pt}
											<circle cx={pt.cx} cy={pt.cy} r="8" fill={smColor(pt.value)} stroke="#14532d" stroke-width="1.2"/>
											<text x={pt.cx} y={pt.cy + 3} text-anchor="middle" fill="#14532d" font-size="7" font-weight="700">{pt.value != null ? fmt(pt.value, 0) : pt.id}</text>
										{/each}
										{#if plotGeom.furrowBox}
											<rect x={plotGeom.furrowBox.x} y={plotGeom.furrowBox.y} width={plotGeom.furrowBox.w} height={plotGeom.furrowBox.h} rx="6" fill="#fef3c7" stroke="#92400e" stroke-width="1.6"/>
											<text x={plotGeom.furrowBox.x + 8} y={plotGeom.furrowBox.y + 14} fill="#92400e" font-size="9" font-weight="700">Furrow</text>
											{#each plotGeom.furrowPts as pt}
												<circle cx={pt.cx} cy={pt.cy} r="8" fill={smColor(pt.value)} stroke="#92400e" stroke-width="1.2"/>
												<text x={pt.cx} y={pt.cy + 3} text-anchor="middle" fill="#78350f" font-size="7" font-weight="700">{pt.value != null ? fmt(pt.value, 0) : pt.id}</text>
											{/each}
										{/if}
									</svg>
								</div>
								<div class="pond-diagram-box">
									<svg class="pond-svg" viewBox="0 0 300 145" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Plot section">
										<line x1="12" y1="88" x2="288" y2="88" stroke="#94a3b8" stroke-width="1.2"/>
										{#if plotGeom.raised}
											<polygon points="28,88 52,48 88,48 112,88" fill="#bbf7d0" stroke="#166534" stroke-width="1.4"/>
											<polygon points="112,88 136,108 188,108 212,88" fill="#fde68a" stroke="#b45309" stroke-width="1.4"/>
											<polygon points="212,88 236,48 272,48 288,88" fill="#bbf7d0" stroke="#166534" stroke-width="1.4"/>
											<text x="70" y="40" text-anchor="middle" fill="#166534" font-size="9" font-weight="700">Ridge {fmt(calcs.sm_diff_pct != null ? plotGeom.ridgePts.reduce((s,p)=>s+(p.value??0),0)/Math.max(1,plotGeom.ridgePts.filter(p=>p.value!=null).length) : null)} %</text>
											<text x="162" y="128" text-anchor="middle" fill="#92400e" font-size="9" font-weight="700">Furrow</text>
											<text x="150" y="22" text-anchor="middle" fill="#14532d" font-size="10" font-weight="700">SM diff {fmt(calcs.sm_diff_pct)} %</text>
										{:else}
											<rect x="30" y="70" width="240" height="18" fill="#d9f99d" stroke="#4d7c0f" stroke-width="1.3"/>
											{#if hasTcPair}
												<text x="150" y="44" text-anchor="middle" fill="#3f7d3f" font-size="10" font-weight="700">T {fmt(latestT)} %</text>
												<text x="150" y="60" text-anchor="middle" fill="#2563eb" font-size="10" font-weight="700">C {fmt(latestC)} %</text>
												<text x="150" y="116" text-anchor="middle" fill="#56646f" font-size="9">Plot-level SM · paired T vs C</text>
											{:else}
												<text x="150" y="52" text-anchor="middle" fill="#3f6212" font-size="10" font-weight="700">Flat plot mean SM {fmt(latestSm?.sm_plot_pct)} %</text>
												<text x="150" y="116" text-anchor="middle" fill="#56646f" font-size="9">Five-point average</text>
											{/if}
										{/if}
									</svg>
								</div>
							</div>
						</div>

						<section class="dash-card chart-card">
							<div class="panel-head panel-head-spread">
								<div class="panel-head">
									<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
										><path fill="currentColor" d="M1.5 12.5 5 8l3 3 5.5-7.5V12.5H1.5z"/></svg>
									<h2 class="panel-title">{data.visual?.title || 'Soil moisture treatment vs control'}</h2>
								</div>
								<div class="chart-legend">
									<span class="chart-leg"><span class="leg-swatch" style="background:#3f7d3f"></span> T</span>
									<span class="chart-leg"><span class="leg-swatch" style="background:#2563eb"></span> C</span>
								</div>
							</div>
							<div bind:this={chartEl} class="chart-host relative"></div>
						</section>

						<section class="dash-card heat-card">
							<div class="panel-head panel-head-spread">
								<div class="panel-head">
									<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
										><path fill="currentColor" d="M2 2h4v4H2V2zm6 0h4v4H8V2zm6 0h2v4h-2V2zM2 8h4v4H2V8zm6 0h4v4H8V8zm6 0h2v4h-2V8zM2 14h4v2H2v-2zm6 0h4v2H8v-2zm6 0h2v2h-2v-2z"/></svg>
									<h2 class="panel-title">Collection calendar</h2>
								</div>
								<div class="heat-controls">
									<label class="heat-metric-label">
										<span>Colour by</span>
										<select bind:value={heatMetric}>
											<option value="collected">Collected (yes/no)</option>
											<option value="soil_moisture">Soil moisture</option>
										</select>
									</label>
									{#if calWindow}
										<div class="year-toggle">
											<button type="button" class="year-btn" disabled={!calWindow.canPanLeft} onclick={() => panCalendar(-1)} aria-label="Earlier months">‹</button>
											<span class="year-label font-mono text-[11px]">{calWindow.label}</span>
											<button type="button" class="year-btn" disabled={!calWindow.canPanRight} onclick={() => panCalendar(1)} aria-label="Later months">›</button>
										</div>
									{/if}
								</div>
							</div>
							<div bind:this={heatEl} class="heat-host relative"></div>
							<div class="heat-footer">
								{#if heatMetric === 'collected'}
									<span class="chart-leg"><span class="leg-swatch" style="background:{COLLECTED_YES}"></span> Yes</span>
									<span class="chart-leg"><span class="leg-swatch" style="background:{COLLECTED_NO}"></span> No</span>
								{:else}
									<span>Low</span>
									{#each heatScale || [] as c}
										<span class="leg-swatch" style="background:{c}"></span>
									{/each}
									<span>High</span>
								{/if}
							</div>
						</section>
					</div>
				</div>

				{#if processItem}
					<div class="process-backdrop" role="presentation" onclick={() => (processKey = null)} onkeydown={(e) => e.key === 'Escape' && (processKey = null)}></div>
					<div class="process-panel" role="dialog" aria-modal="true" aria-labelledby="process-title">
						<div class="process-panel-head">
							<h3 id="process-title" class="process-title">{processItem.label}</h3>
							<button type="button" class="process-close" aria-label="Close" onclick={() => (processKey = null)}>×</button>
						</div>
						<p class="process-value">{fmt(processItem.value)}{processItem.unit ? ` ${processItem.unit}` : ''}</p>
						<p class="process-formula"><span class="metric-k">Formula</span> {processItem.formula}</p>
						{#if processItem.raws?.length}
							<p class="process-raws"><span class="metric-k">Inputs</span> {processItem.raws.join(' · ')}</p>
						{/if}
						{#if processItem.description}
							<p class="process-desc">{processItem.description}</p>
						{/if}
						<div class="process-body">
							<p class="process-body-label">Full process</p>
							<p class="process-body-text">{processItem.how}</p>
						</div>
					</div>
				{/if}

				{#if showAssetInfo}
					<div class="process-backdrop" role="presentation" onclick={() => (showAssetInfo = false)}></div>
					<div class="process-panel asset-info-panel" role="dialog" aria-modal="true" aria-labelledby="asset-info-title">
						<div class="process-panel-head">
							<h3 id="asset-info-title" class="process-title">{data.asset?.label || 'Farm plot'} — full information</h3>
							<button type="button" class="process-close" aria-label="Close" onclick={() => (showAssetInfo = false)}>×</button>
						</div>
						{#if assetInfoRows.length}
							<dl class="asset-info-list">
								{#each assetInfoRows as row (row.key)}
									<div class="asset-info-row">
										<dt class="asset-info-dt">{row.label}</dt>
										<dd class="asset-info-dd">{row.value}</dd>
									</div>
								{/each}
							</dl>
						{:else}
							<p class="process-desc">No one-time survey answers recorded for this farm plot.</p>
						{/if}
					</div>
				{/if}
			</div>
		{/if}
	</main>
</div>

<style>
	.dash-page {
		height: 100vh;
		max-height: 100vh;
		overflow: hidden;
		display: flex;
		flex-direction: column;
	}
	.dash-main {
		flex: 1;
		min-height: 0;
		width: 100%;
		padding: 0.4rem 0.7rem 0.5rem;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		gap: 0.35rem;
	}
	.dash-body {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		overflow: hidden;
		position: relative;
	}
	/* ── Col 1: info panel (identity + meta list + map) ── */
	.info-card {
		flex: 1;
		gap: 0;
		min-height: 0;
		overflow: hidden;
		display: flex;
		flex-direction: column;
	}
	.map-inline-head {
		margin-top: 0.25rem;
		padding-top: 0.4rem;
		border-top: 1px solid rgba(27, 117, 224, 0.1);
	}
	.asset-info-btn {
		flex: none;
		align-self: stretch;
		margin: 0.35rem 0 0.15rem;
		border: 1px solid rgba(27, 117, 224, 0.35);
		background: #fff;
		color: #1b75e0;
		font-size: 0.72rem;
		font-weight: 600;
		padding: 0.4rem 0.55rem;
		border-radius: 0.45rem;
		cursor: pointer;
		text-align: center;
		line-height: 1.2;
	}
	.asset-info-btn:hover {
		background: #eef5fc;
		border-color: #1b75e0;
	}
	.asset-info-panel {
		width: min(34rem, calc(100% - 2rem));
	}
	.asset-info-list {
		margin: 0.25rem 0 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0;
		max-height: min(60vh, 28rem);
		overflow-y: auto;
	}
	.asset-info-row {
		display: grid;
		grid-template-columns: minmax(7rem, 0.9fr) 1.2fr;
		gap: 0.5rem 0.75rem;
		padding: 0.45rem 0;
		border-bottom: 1px solid rgba(27, 117, 224, 0.08);
	}
	.asset-info-row:last-child {
		border-bottom: none;
	}
	.asset-info-dt {
		margin: 0;
		font-size: 0.68rem;
		font-weight: 700;
		letter-spacing: 0.02em;
		color: #1b75e0;
		line-height: 1.3;
	}
	.asset-info-dd {
		margin: 0;
		font-size: 0.8rem;
		font-weight: 550;
		color: #1a2530;
		line-height: 1.35;
		word-break: break-word;
	}
	.info-card .map-frame {
		flex: 1;
		min-height: 120px;
		margin-top: 0.15rem;
	}
	.map-identity {
		flex: none;
		display: flex;
		align-items: flex-start;
		gap: 0.5rem;
		padding-bottom: 0.55rem;
		border-bottom: 1px solid rgba(27, 117, 224, 0.1);
		margin-bottom: 0.1rem;
	}
	.loc-badge {
		width: 26px;
		height: 26px;
		border-radius: 999px;
		background: #1b75e0;
		color: #fff;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: none;
		margin-top: 0.15rem;
	}
	.loc-text { min-width: 0; }
	.info-kicker {
		margin: 0;
		font-size: 9px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: #1b75e0;
	}
	.info-title {
		margin: 0.06rem 0 0;
		font-size: 0.92rem;
		font-weight: 700;
		line-height: 1.22;
		color: #0f2744;
	}
	.info-sub {
		margin: 0.12rem 0 0;
		font-size: 0.66rem;
		color: #6b7885;
		line-height: 1.3;
	}
	.info-coords { font-family: ui-monospace, monospace; }
	.info-place, .info-sep { color: #6b7885; }

	/* Vertical meta list */
	.info-list {
		margin: 0;
		padding: 0;
		flex: none;
		display: flex;
		flex-direction: column;
		gap: 0;
	}
	.info-row {
		display: flex;
		flex-direction: column;
		gap: 0.12rem;
		padding: 0.42rem 0;
		border-bottom: 1px solid rgba(27, 117, 224, 0.08);
	}
	.info-row:last-child {
		border-bottom: none;
		padding-bottom: 0.15rem;
	}
	.info-dt {
		display: flex;
		align-items: center;
		gap: 0.28rem;
		font-size: 9px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: #1b75e0;
		line-height: 1;
	}
	.info-ico {
		width: 12px;
		height: 12px;
		flex: none;
		color: #1b75e0;
	}
	.info-dd {
		margin: 0;
		font-size: 0.9rem;
		font-weight: 600;
		color: #1a2530;
		line-height: 1.3;
		padding-left: 1.4rem; /* align under the label text (past icon) */
	}
	.dash-grid {
		flex: 1;
		min-height: 0;
		display: grid;
		/* info+map | stats (1 per row) | diagrams+charts */
		grid-template-columns: minmax(12rem, 0.85fr) minmax(13rem, 0.95fr) minmax(0, 1.85fr);
		gap: 0.35rem;
		align-items: stretch;
		width: 100%;
		overflow: hidden;
	}
	.dash-col {
		min-width: 0;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		gap: 0.35rem;
	}
	.dash-vis {
		/* middle column: diagrams card on top, stats card below */
	}
	.dash-card {
		border-radius: 0.6rem;
		border: 1px solid rgba(26, 58, 95, 0.1);
		background: #fff;
		padding: 0.4rem 0.5rem;
		box-shadow: 0 1px 2px rgba(15, 39, 68, 0.03);
	}
	.dash-card-fill {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.panel-head {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		margin-bottom: 0.3rem;
		flex: none;
	}
	.panel-head-spread {
		justify-content: space-between;
		flex-wrap: wrap;
		gap: 0.25rem 0.5rem;
		width: 100%;
	}
	.panel-head-spread > .panel-head {
		margin-bottom: 0;
	}
	.panel-ico {
		width: 14px;
		height: 14px;
		color: #1b75e0;
		flex: none;
	}
	.panel-title {
		margin: 0;
		font-size: 0.82rem;
		font-weight: 700;
		color: #0f2744;
	}
	.chart-legend,
	.heat-footer {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.45rem 0.65rem;
		font-size: 0.65rem;
		color: #56646f;
	}
	.heat-footer {
		flex: none;
		margin-top: 0.25rem;
	}
	.chart-leg {
		display: inline-flex;
		align-items: center;
		gap: 0.28rem;
	}
	.leg-swatch {
		display: inline-block;
		width: 10px;
		height: 6px;
		border-radius: 2px;
		flex: none;
	}
	.heat-controls {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 0.55rem;
	}
	.heat-metric-label {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-size: 0.68rem;
		color: #56646f;
	}
	.heat-metric-label select {
		border: 1px solid rgba(26, 58, 95, 0.18);
		border-radius: 0.35rem;
		background: #fff;
		padding: 0.2rem 0.4rem;
		font-size: 0.72rem;
		color: #1a2530;
		outline: none;
	}
	.heat-metric-label select:focus {
		border-color: rgba(27, 117, 224, 0.45);
	}
	.map-panel {
		padding: 0.4rem 0.5rem 0.4rem;
	}
	.map-frame {
		position: relative;
		flex: 1;
		min-height: 0;
		border-radius: 0.45rem;
		overflow: hidden;
		border: 1px solid rgba(26, 58, 95, 0.1);
		background: #eef2f6;
	}
	.map-host {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.map-fallback {
		display: flex;
		align-items: center;
		justify-content: center;
		height: 100%;
		padding: 0.75rem;
		font-size: 0.8rem;
		color: #6b7885;
	}
	.map-legend {
		flex: none;
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 0.65rem;
		padding: 0.25rem 0.1rem 0;
		font-size: 0.67rem;
		color: #56646f;
	}
	.legend-item {
		display: inline-flex;
		align-items: center;
		gap: 0.3rem;
	}
	.legend-dot {
		width: 8px;
		height: 8px;
		border-radius: 999px;
		background: #1b75e0;
		border: 1.5px solid #fff;
		box-shadow: 0 0 0 1px rgba(27, 117, 224, 0.35);
	}
	/* Diagrams card at top of col 3 */
	.dims-row-card {
		flex: none;
		display: flex;
		flex-direction: column;
	}
	.dims-legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.35rem 0.7rem;
		font-size: 0.65rem;
		color: #56646f;
	}
	.dims-leg {
		display: inline-flex;
		align-items: center;
		gap: 0.28rem;
	}
	.dims-swatch {
		display: inline-block;
		width: 12px;
		height: 10px;
		border-radius: 2px;
		border: 1px solid #1e3a8a;
		flex: none;
	}
	.dims-swatch-top {
		background: #bfdbfe;
	}
	.dims-swatch-bottom {
		background: #93c5fd;
	}
	.dims-swatch-water {
		background: #1d4ed8;
		border-color: #1e40af;
	}
	.pond-diagrams-row {
		display: flex;
		flex-direction: row;
		gap: 0.3rem;
		height: 118px;
	}
	.pond-diagrams-row .pond-diagram-box {
		flex: 1 1 0;
		min-width: 0;
	}

	/* (kept for possible reuse) */
	.pond-diagrams {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		flex: 1;
		min-height: 0;
		overflow: hidden;
	}
	.pond-diagram-box {
		flex: 1 1 0;
		min-height: 0;
		border-radius: 8px;
		background: #eef5fc;
		border: 1px solid rgba(27, 117, 224, 0.1);
		overflow: hidden;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.pond-svg {
		width: 100%;
		height: 100%;
		display: block;
	}

	/* Stats card = col 2: one metric per row */
	.stats-card {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		padding: 0.4rem 0.5rem;
	}
	.pond-metrics {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: 0.35rem;
		flex: 1;
		min-height: 0;
		overflow-y: auto;
	}
	.pond-metric {
		display: flex;
		flex-direction: column;
		justify-content: flex-start;
		gap: 0.28rem;
		padding: 0.55rem 0.6rem 0.45rem;
		border-radius: 8px;
		border: 1px solid rgba(27, 117, 224, 0.12);
		background: #f8fbff;
		min-height: 0;
		flex: 1 1 0;
	}
	.metric-head {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.metric-top {
		display: flex;
		align-items: center;
		gap: 0.3rem;
		min-width: 0;
	}
	.metric-formula,
	.metric-raws {
		margin: 0;
		font-size: 0.65rem;
		line-height: 1.4;
		color: #8a96a3;
	}
	.metric-formula {
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		color: #8a96a3;
		background: rgba(15, 39, 68, 0.04);
		border-radius: 4px;
		padding: 0.22rem 0.4rem;
	}
	.metric-k {
		font-weight: 700;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: #9aa6b2;
		font-size: 0.58rem;
		margin-right: 0.25rem;
		font-family: inherit;
	}
	.metric-raws {
		color: #8a96a3;
	}
	.metric-know-more {
		align-self: flex-end;
		margin-top: auto;
		border: none;
		background: transparent;
		color: #1b75e0;
		font-size: 0.68rem;
		font-weight: 600;
		padding: 0.15rem 0;
		cursor: pointer;
		line-height: 1.2;
	}
	.metric-know-more:hover,
	.metric-know-more[aria-expanded='true'] {
		text-decoration: underline;
		color: #155fba;
	}

	/* Process description dialog */
	.process-backdrop {
		position: absolute;
		inset: 0;
		background: rgba(15, 39, 68, 0.28);
		z-index: 20;
	}
	.process-panel {
		position: absolute;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		z-index: 21;
		width: min(28rem, calc(100% - 2rem));
		max-height: calc(100% - 2rem);
		overflow: auto;
		background: #fff;
		border-radius: 0.75rem;
		border: 1px solid rgba(27, 117, 224, 0.18);
		box-shadow: 0 16px 40px -12px rgba(15, 39, 68, 0.35);
		padding: 1rem 1.1rem 1.15rem;
		display: flex;
		flex-direction: column;
		gap: 0.45rem;
	}
	.process-panel-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
	}
	.process-title {
		margin: 0;
		font-size: 1rem;
		font-weight: 700;
		color: #0f2744;
	}
	.process-close {
		border: none;
		background: #eef2f6;
		color: #3b4a58;
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 999px;
		font-size: 1.15rem;
		line-height: 1;
		cursor: pointer;
	}
	.process-close:hover {
		background: #dde3ea;
	}
	.process-value {
		margin: 0;
		font-size: 1.35rem;
		font-weight: 700;
		color: #1a2530;
		font-variant-numeric: tabular-nums;
	}
	.process-formula {
		margin: 0;
		font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
		font-size: 0.75rem;
		color: #3b4a58;
		background: rgba(27, 117, 224, 0.06);
		border-radius: 5px;
		padding: 0.3rem 0.45rem;
	}
	.process-raws {
		margin: 0;
		font-size: 0.72rem;
		color: #56646f;
		line-height: 1.4;
	}
	.process-desc {
		margin: 0;
		font-size: 0.78rem;
		color: #3b4a58;
		line-height: 1.4;
	}
	.process-body {
		margin-top: 0.15rem;
		padding-top: 0.55rem;
		border-top: 1px solid rgba(27, 117, 224, 0.12);
	}
	.process-body-label {
		margin: 0 0 0.25rem;
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.08em;
		text-transform: uppercase;
		color: #1b75e0;
	}
	.process-body-text {
		margin: 0;
		font-size: 0.8rem;
		line-height: 1.5;
		color: #1a2530;
	}
	.metric-ico {
		width: 18px;
		height: 18px;
		flex: none;
		border-radius: 4px;
		background-color: #e8f1fc;
		position: relative;
	}
	.metric-ico::after {
		content: '';
		position: absolute;
		inset: 0;
		margin: auto;
		width: 11px;
		height: 11px;
		background: #1b75e0;
		mask-size: contain;
		mask-repeat: no-repeat;
		mask-position: center;
		-webkit-mask-size: contain;
		-webkit-mask-repeat: no-repeat;
		-webkit-mask-position: center;
	}
	.metric-ico[data-icon='wl'] {
		background-color: #e8f8ef;
	}
	.metric-ico[data-icon='wl']::after {
		background: #16a34a;
		mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 2 3.5 8h2.7v6h3.6V8H12.5z'/%3E%3C/svg%3E");
		-webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 2 3.5 8h2.7v6h3.6V8H12.5z'/%3E%3C/svg%3E");
	}
	.metric-ico[data-icon='fill']::after {
		mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 1C5.8 3.6 4 5.7 4 8a4 4 0 1 0 8 0c0-2.3-1.8-4.4-4-7z'/%3E%3C/svg%3E");
		-webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 1C5.8 3.6 4 5.7 4 8a4 4 0 1 0 8 0c0-2.3-1.8-4.4-4-7z'/%3E%3C/svg%3E");
	}
	.metric-ico[data-icon='cube']::after {
		mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 1.2 1.5 4.5v7L8 14.8l6.5-3.3v-7L8 1.2zm0 1.7 4.5 2.3L8 8.5 3.5 5.2 8 2.9zM2.8 6.3 7.2 9v4.3L2.8 11V6.3zm10.4 0V11L8.8 13.3V9l4.4-2.7z'/%3E%3C/svg%3E");
		-webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 1.2 1.5 4.5v7L8 14.8l6.5-3.3v-7L8 1.2zm0 1.7 4.5 2.3L8 8.5 3.5 5.2 8 2.9zM2.8 6.3 7.2 9v4.3L2.8 11V6.3zm10.4 0V11L8.8 13.3V9l4.4-2.7z'/%3E%3C/svg%3E");
	}
	.metric-ico[data-icon='recharge']::after {
		mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 2a6 6 0 0 1 5.3 3.2l1.2-.7L13 1.5l-.9 1.6A6 6 0 1 0 14 8h-1.5A4.5 4.5 0 1 1 8 3.5c1.1 0 2.1.4 2.9 1.1L9.5 6H14V2l-1.6 1.4A6 6 0 0 0 8 2z'/%3E%3C/svg%3E");
		-webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M8 2a6 6 0 0 1 5.3 3.2l1.2-.7L13 1.5l-.9 1.6A6 6 0 1 0 14 8h-1.5A4.5 4.5 0 1 1 8 3.5c1.1 0 2.1.4 2.9 1.1L9.5 6H14V2l-1.6 1.4A6 6 0 0 0 8 2z'/%3E%3C/svg%3E");
	}
	.metric-ico[data-icon='rain']::after {
		mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M5.5 2a3.5 3.5 0 0 1 3.4 2.7A2.8 2.8 0 0 1 12.5 8H4.2A2.2 2.2 0 0 1 2 5.8 2.2 2.2 0 0 1 4.5 3.7 3.5 3.5 0 0 1 5.5 2zM4 10.2 5 13h1.2L5.2 10.2H4zm3 0L8 13h1.2L8.2 10.2H7zm3 0L11 13h1.2l-1-2.8H10z'/%3E%3C/svg%3E");
		-webkit-mask-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3E%3Cpath fill='black' d='M5.5 2a3.5 3.5 0 0 1 3.4 2.7A2.8 2.8 0 0 1 12.5 8H4.2A2.2 2.2 0 0 1 2 5.8 2.2 2.2 0 0 1 4.5 3.7 3.5 3.5 0 0 1 5.5 2zM4 10.2 5 13h1.2L5.2 10.2H4zm3 0L8 13h1.2L8.2 10.2H7zm3 0L11 13h1.2l-1-2.8H10z'/%3E%3C/svg%3E");
	}
	.pond-metric-label {
		font-size: 0.7rem;
		line-height: 1.15;
		font-weight: 600;
		color: #56646f;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.pond-metric-value {
		font-size: 1.05rem;
		line-height: 1.1;
		font-weight: 700;
		color: #1a2530;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
		flex: none;
	}
	.pond-metric-hint {
		display: none;
	}
	.pond-metric[data-key='cum_wl'] .pond-metric-hint {
		color: #16a34a;
		font-weight: 600;
	}
	.metric-ring {
		width: 18px;
		height: 18px;
		flex: none;
		transform: rotate(-90deg);
	}
	.kpi-bar {
		height: 4px;
		border-radius: 999px;
		background: #e2e8f0;
		overflow: hidden;
		margin-top: 0.1rem;
	}
	.kpi-bar > span {
		display: block;
		height: 100%;
		border-radius: inherit;
		background: #22c55e;
		min-width: 4px;
	}
	.kpi-ring-bg {
		fill: none;
		stroke: #e2e8f0;
		stroke-width: 3.5;
	}
	.kpi-ring-fg {
		fill: none;
		stroke: #22c55e;
		stroke-width: 3.5;
		stroke-linecap: round;
	}
	.dash-charts {
		/* gap from .dash-col */
		min-height: 0;
		height: 100%;
	}
	.chart-card {
		flex: 1.1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.heat-card {
		flex: 1.25;
		min-height: 156px;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.chart-host {
		width: 100%;
		flex: 1;
		min-height: 0;
	}
	.heat-host {
		position: relative;
		width: 100%;
		flex: 1 1 auto;
		min-height: 160px;
		overflow: hidden;
	}
	.heat-host :global(svg) {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
	}
	.year-toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.25rem;
		border: 1px solid rgba(27, 117, 224, 0.18);
		border-radius: 999px;
		padding: 0.1rem 0.3rem;
		background: #f7fafc;
	}
	.year-btn {
		border: none;
		background: transparent;
		color: #1b75e0;
		font-size: 1rem;
		line-height: 1;
		width: 1.35rem;
		height: 1.35rem;
		border-radius: 999px;
		cursor: pointer;
	}
	.year-btn:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}
	.year-label {
		min-width: 7.5rem;
		text-align: center;
		color: #1a2530;
	}
	:global(.chart-host .empty),
	:global(.heat-host .empty) {
		margin: 0;
		padding: 0.5rem 0;
		font-size: 0.8rem;
		color: #6b7885;
	}
	:global(.chart-host .chart-tip),
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
		max-width: 16rem;
	}
	@media (max-width: 1100px) {
		.dash-page {
			height: auto;
			max-height: none;
			overflow: auto;
		}
		.dash-main {
			overflow: visible;
			min-height: auto;
		}
		.dash-grid {
			grid-template-columns: 1fr;
			overflow: visible;
			height: auto;
		}
		.info-card {
			overflow: visible;
			min-height: auto;
		}
		.info-card .map-frame {
			min-height: 180px;
			flex: none;
			height: 200px;
		}
		.pond-diagrams-row {
			flex-direction: column;
			height: auto;
		}
		.pond-diagrams-row .pond-diagram-box {
			height: 140px;
		}
		.map-frame {
			min-height: 180px;
		}
		.stats-card {
			flex: none;
			height: auto;
			overflow: visible;
		}
		.pond-metrics {
			overflow: visible;
		}
		.chart-host,
		.heat-host {
			min-height: 180px;
		}
	}

	.loc-badge-plot {
		background: #166534;
	}
	.legend-dot-plot {
		background: #166534;
		box-shadow: 0 0 0 1px rgba(22, 101, 52, 0.35);
	}
	.dims-swatch-ridge {
		background: #bbf7d0;
		border-color: #166534;
	}
	.dims-swatch-furrow {
		background: #fde68a;
		border-color: #92400e;
	}
	.dims-swatch-flat {
		background: #d9f99d;
		border-color: #4d7c0f;
	}
	.info-kicker,
	.info-dt {
		color: #166534;
	}
	.loc-badge-plot + .loc-text .info-kicker {
		color: #166534;
	}
	.panel-ico {
		color: #166534;
	}
	.asset-info-btn {
		color: #166534;
		border-color: rgba(22, 101, 52, 0.35);
	}
	.asset-info-btn:hover {
		background: #f0fdf4;
		border-color: #166534;
	}
	.asset-info-dt {
		color: #166534;
	}
</style>
