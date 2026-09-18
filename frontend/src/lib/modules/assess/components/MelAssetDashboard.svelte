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
		ASSESS_BLUE,
		BLUE_SCALE,
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
	/** @type {'collected'|'water_level'|'rainfall'} */
	let heatMetric = $state('collected');
	/** @type {string|null} key of metric whose process popover is open */
	let processKey = $state(null);
	let showAssetInfo = $state(false);

	/** Default side-slope ratio Z (horizontal : 1 vertical) when not surveyed. */
	const DEFAULT_Z = 1.5;

	/** @type {maplibregl.Map | null} */
	let map = null;

	const WL_SCALE = BLUE_SCALE;
	const RAIN_SCALE = ['#e8f8ef', '#86efac', '#22c55e', '#15803d', '#14532d'];
	const COLLECTED_YES = '#1b75e0';
	const COLLECTED_NO = '#eef1f4';

	const slugBase = $derived(itemPath('/assess', project, projects));
	const crumbs = $derived(
		assessCrumbs({
			projects,
			project,
			plan,
			tail: [{ label: data?.asset?.label || 'Asset' }]
		})
	);

	const series = $derived(data?.visual?.series || []);
	const maxH = $derived(data?.visual?.max_pond_height_m);
	const ot = $derived(data?.asset?.ot_answers || {});

	const location = $derived.by(() => {
		const raw = String(ot.fp_ot_location || '').trim();
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
		const place = [ot.fp_ot_village_name, ot.fp_ot_block_name, ot.fp_ot_district_name]
			.map((v) => String(v || '').trim())
			.filter(Boolean);
		return {
			lat,
			lon,
			coordsLabel:
				lat != null && lon != null ? `${lat.toFixed(5)}, ${lon.toFixed(5)}` : raw || null,
			placeLabel: place.length ? place.join(' · ') : null,
			farmer: String(ot.fp_ot_farmer_name || '').trim() || null,
			pondType: String(ot.fp_ot_farm_pond_type || '').trim() || null
		};
	});

	const heatValueField = $derived(
		heatMetric === 'rainfall'
			? 'daily_rainfall_mm'
			: heatMetric === 'water_level'
				? 'water_level_m'
				: null
	);
	const heatScale = $derived(
		heatMetric === 'rainfall' ? RAIN_SCALE : heatMetric === 'water_level' ? WL_SCALE : null
	);
	const heatMetricLabel = $derived(
		heatMetric === 'rainfall'
			? 'Daily rainfall'
			: heatMetric === 'water_level'
				? 'Water level'
				: 'Record collected'
	);
	const heatUnit = $derived(
		heatMetric === 'rainfall' ? 'mm' : heatMetric === 'water_level' ? 'm' : ''
	);

	const activity = $derived(
		dailyActivity(
			series.map((p) => ({
				date: p.date,
				water_level_m: p.water_level_m,
				daily_rainfall_mm: p.daily_rainfall_mm
			})),
			{ dateField: 'date', valueField: heatValueField }
		)
	);

	const calcs = $derived(data?.calculations || {});

	const pondDims = $derived.by(() => {
		const length = Number(ot.fp_ot_length);
		const breadth = Number(ot.fp_ot_breadth);
		const depth = Number(ot.fp_ot_height ?? maxH);
		const zRaw = Number(ot.fp_ot_side_slope ?? ot.fp_ot_z ?? DEFAULT_Z);
		const Z = Number.isFinite(zRaw) && zRaw > 0 ? zRaw : DEFAULT_Z;
		const L = Number.isFinite(length) && length > 0 ? length : 12;
		const B = Number.isFinite(breadth) && breadth > 0 ? breadth : 12;
		const D = Number.isFinite(depth) && depth > 0 ? depth : 3;
		const latestWl = [...series].reverse().find((p) => p.water_level_m != null)?.water_level_m;
		const h = latestWl != null ? Math.max(0, Math.min(D, Number(latestWl))) : 0;
		const fillRatio = D > 0 ? h / D : 0;
		return {
			L,
			B,
			D,
			Z,
			h,
			fillRatio,
			topL: L + 2 * Z * D,
			topB: B + 2 * Z * D,
			waterL: L + 2 * Z * h,
			waterB: B + 2 * Z * h,
			latestWl: latestWl != null ? Number(latestWl) : null
		};
	});

	/** Plan + section A-A geometry matching farm-pond frustum diagram. */
	const pondGeom = $derived.by(() => {
		const { L, B, D, Z, h, topL, topB, waterL, waterB } = pondDims;

		// Smaller viewBox → higher CSS scale → bigger, legible text
		const planW = 300;
		const planH = 170;
		const planPadX = 22;
		const planPadTop = 12;
		const planPadBottom = 36;
		const planPadRight = 72;
		const planScale =
			Math.min(
				(planW - planPadX - planPadRight) / topL,
				(planH - planPadTop - planPadBottom) / topB
			) * 0.88;
		const outerW = topL * planScale;
		const outerH = topB * planScale;
		const innerW = L * planScale;
		const innerH = B * planScale;
		const ox = planPadX + (planW - planPadX - planPadRight - outerW) / 2;
		const oy = planPadTop + (planH - planPadTop - planPadBottom - outerH) / 2;
		const ix = ox + (outerW - innerW) / 2;
		const iy = oy + (outerH - innerH) / 2;
		const waterW = waterL * planScale;
		const waterHt = waterB * planScale;
		const wx = ox + (outerW - waterW) / 2;
		const wy = oy + (outerH - waterHt) / 2;

		const plan = {
			viewW: planW,
			viewH: planH,
			outer: { x: ox, y: oy, w: outerW, h: outerH },
			inner: { x: ix, y: iy, w: innerW, h: innerH },
			water: { x: wx, y: wy, w: waterW, h: waterHt },
			corners: {
				lines: [
					[
						[ox, oy],
						[ix, iy]
					],
					[
						[ox + outerW, oy],
						[ix + innerW, iy]
					],
					[
						[ox + outerW, oy + outerH],
						[ix + innerW, iy + innerH]
					],
					[
						[ox, oy + outerH],
						[ix, iy + innerH]
					]
				]
			},
			// Dimension arrow anchors
			lenArrow: {
				x1: ix,
				x2: ix + innerW,
				y: oy + outerH + 14
			},
			brArrow: {
				x: ox + outerW + 12,
				y1: iy,
				y2: iy + innerH
			}
		};

		const secW = 300;
		const secH = 145;
		const secPadX = 50;
		const groundY = 26;
		const depthPx = Math.max(40, Math.min(65, D * 18));
		const usable = secW - secPadX * 2;
		const secScale = (usable / topL) * 0.82;
		const topPx = topL * secScale;
		const botPx = L * secScale;
		const left0 = (secW - topPx) / 2;
		const botLeft = left0 + (topPx - botPx) / 2;
		const bottomY = groundY + depthPx;

		const waterTopPx = waterL * secScale;
		const waterDepthPx = depthPx * (h / Math.max(D, 1e-6));
		const waterTopY = bottomY - waterDepthPx;
		const waterLeft = (secW - waterTopPx) / 2;

		const bundW = 16;
		const bundH = 9;

		const section = {
			viewW: secW,
			viewH: secH,
			groundY,
			bottomY,
			excavation: [
				[left0, groundY],
				[botLeft, bottomY],
				[botLeft + botPx, bottomY],
				[left0 + topPx, groundY]
			],
			water:
				h > 0.01
					? [
							[waterLeft, waterTopY],
							[botLeft, bottomY],
							[botLeft + botPx, bottomY],
							[waterLeft + waterTopPx, waterTopY]
						]
					: null,
			waterTopY,
			left0,
			topPx,
			botLeft,
			botPx,
			bunds: [
				{ x: left0 - bundW, y: groundY - bundH, w: bundW, h: bundH },
				{ x: left0 + topPx, y: groundY - bundH, w: bundW, h: bundH }
			],
			htArrow: {
				x: Math.max(18, left0 - 22),
				y1: groundY,
				y2: bottomY
			},
			wlArrow:
				h > 0.01
					? {
							x: Math.min(secW - 18, left0 + topPx + 18),
							y1: waterTopY,
							y2: bottomY
						}
					: null,
			lenArrow: {
				x1: botLeft,
				x2: botLeft + botPx,
				y: Math.min(secH - 20, bottomY + 15)
			}
		};

		return { plan, section, L, B, D, Z, h };
	});

	const surfaceArea = $derived(
		calcs.surface_area_m2 != null ? calcs.surface_area_m2 : pondDims.L * pondDims.B
	);

	const calcCardsByVar = $derived.by(() => {
		/** @type {Record<string, any>} */
		const map = {};
		for (const c of data?.calculation_cards || []) {
			if (c?.variable) map[c.variable] = c;
		}
		return map;
	});

	const wlStats = $derived.by(() => {
		const wls = series.map((p) => p.water_level_m).filter((v) => v != null).map(Number);
		let rises = 0;
		let riseSum = 0;
		let declines = 0;
		const E = Number(calcs.evaporation_assumption_m ?? 0.005);
		for (let i = 1; i < wls.length; i++) {
			const d = wls[i] - wls[i - 1];
			if (d > 0) {
				rises += 1;
				riseSum += d;
			} else if (-d > E) {
				declines += 1;
			}
		}
		const rainPts = series.filter((p) => p.daily_rainfall_mm != null).length;
		return { n: wls.length, rises, riseSum, declines, rainPts, E };
	});

	const pondLabels = $derived.by(() => {
		const L = pondDims.L;
		const B = pondDims.B;
		const H = pondDims.D;
		const area = surfaceArea;
		const cumWl = calcs.cum_wl_height_increase_m;
		const fillings = calcs.number_of_fillings;
		const vol = calcs.volumetric_storage_m3;
		const volSimple = calcs.volume_m3;
		const recharge = calcs.recharge_m;
		const kpiTarget = Number(ot.fp_ot_what_is_the_volumetric_water_savings_kpi_decided_);
		const kpiPctVal = calcs.volumetric_savings_kpi_progress_pct;
		const cumRain = calcs.cumulative_rainfall_mm;
		const cards = calcCardsByVar;

		return [
			{
				key: 'volume',
				label: 'Volume',
				value: volSimple,
				unit: 'm³',
				icon: 'cube',
				formula: 'L × B × H',
				description:
					cards.volume_m3?.description ||
					'Pond capacity: length × breadth × height (box volume).',
				how:
					cards.volume_m3?.methodology ||
					'Multiply pond length by breadth and height from the one-time survey. Result is the maximum storage volume in m³.',
				raws: [`L ${fmt(L)} m`, `B ${fmt(B)} m`, `H ${fmt(H)} m`]
			},
			{
				key: 'cum_wl',
				label: 'Cum. WL increase',
				value: cumWl,
				unit: 'm',
				icon: 'wl',
				formula: 'Σ max(WLᵢ₊₁ − WLᵢ, 0)',
				description:
					cards.cum_wl_height_increase_m?.description ||
					'Sums all positive water-level rises across consecutive staff-gauge readings.',
				how:
					cards.cum_wl_height_increase_m?.methodology ||
					'Order CM staff-gauge readings by date. For each consecutive pair (WL1 then WL2) add (WL2 − WL1) when the change is positive; ignore declines. The sum is the cumulative rise in water-column height (m).',
				raws: [
					`${wlStats.n} WL readings`,
					`${wlStats.rises} rises`,
					`sum of rises ${fmt(wlStats.riseSum)} m`
				]
			},
			{
				key: 'fillings',
				label: 'Fillings',
				value: fillings,
				unit: '',
				icon: 'fill',
				formula: 'Cum. WL increase ÷ Height',
				description:
					cards.number_of_fillings?.description ||
					'Estimates how many times the structure filled by dividing cumulative WL rise by max depth.',
				how:
					cards.number_of_fillings?.methodology ||
					'Compute increase in cumulative WL height from the CM staff-gauge series. Divide by max depth of the structure (one-time height). Result is number of fillings over the monitoring period.',
				raws: [
					`Cum. WL ${fmt(cumWl)} m`,
					`Height ${fmt(H)} m`,
					fillings != null ? `${Math.max(0, Math.round(Number(fillings)))} fill events` : null
				].filter(Boolean)
			},
			{
				key: 'storage',
				label: 'Runoff harvested',
				value: vol,
				unit: 'm³',
				icon: 'cube',
				formula: 'Surface area × Height × Fillings',
				description:
					cards.volumetric_storage_m3?.description ||
					'Estimates total water volume stored/harvested over the monitoring period (m³).',
				how:
					cards.volumetric_storage_m3?.methodology ||
					'Compute surface area = length × breadth. Compute number of fillings from cumulative WL rise ÷ max depth. Multiply surface area × height × number of fillings to get volumetric storage in m³.',
				raws: [
					`L×B ${fmt(L)}×${fmt(B)} = ${fmt(area)} m²`,
					`Height ${fmt(H)} m`,
					`Fillings ${fmt(fillings)}`
				]
			},
			{
				key: 'recharge',
				label: 'Recharge',
				value: recharge,
				unit: 'm',
				icon: 'recharge',
				formula: 'Σ (decline − E) where decline > E',
				description:
					cards.recharge_m?.description ||
					'Estimates recharge from successive water-level declines after accounting for evaporation.',
				how:
					cards.recharge_m?.methodology ||
					'From consecutive staff-gauge readings, sum declines that exceed evaporation E, then subtract E from each qualifying decline. Evaporation E is an assumed daily input.',
				raws: [
					`${wlStats.declines} declines > E`,
					`E = ${fmt(wlStats.E, 3)} m/day`,
					`${wlStats.n} WL readings`
				]
			},
			{
				key: 'kpi',
				label: 'Target achieved',
				value: kpiPctVal,
				unit: '%',
				icon: 'kpi',
				formula: 'Runoff harvested ÷ KPI target × 100',
				description:
					cards.volumetric_savings_kpi_progress_pct?.description ||
					'Tracks progress (%) of realized volumetric storage against the savings KPI.',
				how:
					cards.volumetric_savings_kpi_progress_pct?.methodology ||
					'Compute volumetric storage as above. Divide by the one-time target KPI for the farm pond and express as a percentage.',
				raws: [
					`Storage ${fmt(vol)} m³`,
					Number.isFinite(kpiTarget) && kpiTarget > 0
						? `KPI target ${fmt(kpiTarget)} m³`
						: 'KPI target not set'
				]
			},
			{
				key: 'rain',
				label: 'Cumulative rainfall',
				value: cumRain,
				unit: 'mm',
				icon: 'rain',
				formula: 'Σ daily rainfall',
				description:
					cards.cumulative_rainfall_mm?.description ||
					'Sums reported daily rainfall over the CM monitoring period.',
				how:
					cards.cumulative_rainfall_mm?.methodology ||
					'Sum all CM rainfall (mm) readings for the selected asset over the analysis window.',
				raws: [`${wlStats.rainPts} rain readings`, `Total ${fmt(cumRain)} mm`]
			}
		];
	});

	const processItem = $derived(
		processKey ? pondLabels.find((p) => p.key === processKey) || null : null
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
		maxH;
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

	/** @param {string} key */
	function humanizeOtKey(key) {
		return String(key || '')
			.replace(/^fp_ot_/, '')
			.replace(/_+$/g, '')
			.replace(/_/g, ' ')
			.replace(/\b\w/g, (c) => c.toUpperCase());
	}

	/** @param {any} v */
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

	/** @param {number[][]} pts */
	function polyPoints(pts) {
		return pts.map(([x, y]) => `${x},${y}`).join(' ');
	}

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
				'circle-color': ASSESS_BLUE,
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
				.text('No CM staff-gauge readings yet.');
			return;
		}

		const width = Math.max(280, chartEl.clientWidth || 480);
		const height = Math.max(160, Math.min(320, chartEl.clientHeight || 220));
		const margin = { top: 20, right: 48, bottom: 36, left: 44 };

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

		const wls = parsed.map((p) => p.water_level_m).filter((v) => v != null);
		const rains = parsed.map((p) => p.daily_rainfall_mm || 0);
		const cum = parsed.map((p) => p.cumulative_rainfall_mm || 0);
		const minWl = Math.min(0, ...(wls.length ? wls : [0]));
		const maxWl = Math.max(...(wls.length ? wls : [1]), maxH != null ? maxH : 1, 0.1);
		const maxRain = Math.max(...rains, ...cum, 1);

		const x = d3
			.scaleUtc()
			.domain(d3.extent(parsed, (d) => d._date))
			.range([margin.left, width - margin.right]);
		const yWl = d3
			.scaleLinear()
			.domain([minWl, maxWl * 1.05])
			.nice()
			.range([height - margin.bottom, margin.top]);
		const yRain = d3
			.scaleLinear()
			.domain([0, maxRain * 1.08])
			.nice()
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
					.axisLeft(yWl)
					.ticks(6)
					.tickSize(-(width - margin.left - margin.right))
					.tickFormat(() => '')
			)
			.call((g) => g.select('.domain').remove())
			.call((g) => g.selectAll('line').attr('stroke', '#e8edf2').attr('stroke-dasharray', '3 3'));

		const xTicks = Math.min(8, Math.max(3, Math.floor(parsed.length / 30) + 2));
		svg
			.append('g')
			.attr('transform', `translate(0,${height - margin.bottom})`)
			.call(
				d3
					.axisBottom(x)
					.ticks(xTicks)
					.tickFormat(/** @type {any} */ (d3.utcFormat('%d %b')))
			)
			.call((g) => g.select('.domain').attr('stroke', '#c5ced6'))
			.selectAll('text')
			.attr('fill', '#56646f')
			.style('font-size', '10px')
			.attr('transform', 'rotate(-25)')
			.style('text-anchor', 'end');

		svg
			.append('g')
			.attr('transform', `translate(${margin.left},0)`)
			.call(d3.axisLeft(yWl).ticks(6))
			.call((g) => g.select('.domain').attr('stroke', '#c5ced6'))
			.selectAll('text')
			.attr('fill', '#1e3a8a')
			.style('font-size', '10px');

		svg
			.append('text')
			.attr('x', 14)
			.attr('y', margin.top - 8)
			.attr('fill', '#1e3a8a')
			.attr('font-size', 11)
			.attr('font-weight', 600)
			.text('Water level (m)');

		svg
			.append('g')
			.attr('transform', `translate(${width - margin.right},0)`)
			.call(d3.axisRight(yRain).ticks(6))
			.call((g) => g.select('.domain').attr('stroke', '#c5ced6'))
			.selectAll('text')
			.attr('fill', '#2563eb')
			.style('font-size', '10px');

		svg
			.append('text')
			.attr('x', width - 14)
			.attr('y', margin.top - 8)
			.attr('text-anchor', 'end')
			.attr('fill', '#2563eb')
			.attr('font-size', 11)
			.attr('font-weight', 600)
			.text('Rainfall (mm)');

		const innerW = width - margin.left - margin.right;
		const barW = Math.max(2, Math.min(10, (innerW / Math.max(parsed.length, 1)) * 0.55));

		svg
			.append('g')
			.selectAll('rect.rain')
			.data(parsed)
			.join('rect')
			.attr('class', 'rain')
			.attr('x', (d) => x(d._date) - barW / 2)
			.attr('y', (d) => yRain(d.daily_rainfall_mm || 0))
			.attr('width', barW)
			.attr('height', (d) => Math.max(0, yRain(0) - yRain(d.daily_rainfall_mm || 0)))
			.attr('fill', '#93c5fd')
			.attr('opacity', 0.9);

		const cumLine = d3
			.line()
			.defined((d) => d.cumulative_rainfall_mm != null)
			.x((d) => x(d._date))
			.y((d) => yRain(d.cumulative_rainfall_mm || 0))
			.curve(d3.curveStepAfter);

		svg
			.append('path')
			.datum(parsed)
			.attr('fill', 'none')
			.attr('stroke', '#4ade80')
			.attr('stroke-width', 2)
			.attr('d', cumLine);

		const wlLine = d3
			.line()
			.defined((d) => d.water_level_m != null)
			.x((d) => x(d._date))
			.y((d) => yWl(d.water_level_m))
			.curve(d3.curveMonotoneX);

		svg
			.append('path')
			.datum(parsed.filter((d) => d.water_level_m != null))
			.attr('fill', 'none')
			.attr('stroke', '#1e3a8a')
			.attr('stroke-width', 2.5)
			.attr('d', wlLine);

		svg
			.append('g')
			.selectAll('circle.wl')
			.data(parsed.filter((d) => d.water_level_m != null))
			.join('circle')
			.attr('class', 'wl')
			.attr('cx', (d) => x(d._date))
			.attr('cy', (d) => yWl(d.water_level_m))
			.attr('r', 3.25)
			.attr('fill', '#1e3a8a')
			.attr('stroke', '#fff')
			.attr('stroke-width', 1);

		if (maxH != null) {
			const y = yWl(maxH);
			svg
				.append('line')
				.attr('x1', margin.left)
				.attr('x2', width - margin.right)
				.attr('y1', y)
				.attr('y2', y)
				.attr('stroke', '#9ca3af')
				.attr('stroke-dasharray', '6 4')
				.attr('stroke-width', 1.5);
			svg
				.append('text')
				.attr('x', width - margin.right - 4)
				.attr('y', y - 4)
				.attr('text-anchor', 'end')
				.attr('fill', '#6b7280')
				.attr('font-size', 10)
				.text(`Max height ${fmt(maxH)} m`);
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
		const focusDot = focus
			.append('circle')
			.attr('r', 5)
			.attr('fill', ASSESS_BLUE)
			.attr('stroke', '#fff')
			.attr('stroke-width', 1.5);

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
				if (d.water_level_m != null) {
					focusDot.style('display', null).attr('cx', cx).attr('cy', yWl(d.water_level_m));
				} else {
					focusDot.style('display', 'none');
				}
				const dateLabel = d3.utcFormat('%d %b %Y')(d._date);
				tip.html(
					`<strong>${dateLabel}</strong><br/>` +
						`Water level: <strong>${d.water_level_m != null ? fmt(d.water_level_m) + ' m' : '—'}</strong><br/>` +
						`Daily rainfall: <strong>${d.daily_rainfall_mm != null ? fmt(d.daily_rainfall_mm) + ' mm' : '—'}</strong><br/>` +
						`Cumulative rainfall: <strong>${fmt(d.cumulative_rainfall_mm)} mm</strong>`
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

			const avail = Math.max(280, heatEl.clientWidth || 400);
			const leftPad = 22;
			const topPad = 18;
			const gap = 2;
			const cell = Math.max(7, Math.min(12, Math.floor((avail - leftPad - 8) / weekCount) - gap));
			const width = leftPad + weekCount * (cell + gap);
			const height = topPad + 7 * (cell + gap) + 4;

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
						? `WL ${point.water_level_m != null ? fmt(point.water_level_m) + ' m' : '—'} · Rain ${
								point.daily_rainfall_mm != null ? fmt(point.daily_rainfall_mm) + ' mm' : '—'
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
			>Edit asset</button
		>
		<button type="button" onclick={() => goto(`${slugBase}/plans/${plan.id}`)}>Back to intervention</button>
	</ModuleHeader>

	<main class="dash-main">
		{#if loading}
			<p class="m-0 self-center text-brand-steel">Loading asset dashboard…</p>
		{:else if error}
			<p class="m-0 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
		{:else}
			<div class="dash-body">
				<div class="dash-grid">
					<!-- Col 1: info + map -->
					<section class="dash-col dash-info">
						<div class="dash-card dash-card-fill info-card">

							<!-- Location identity -->
							<div class="map-identity">
								<div class="loc-badge" aria-hidden="true">
									<svg viewBox="0 0 16 16" width="13" height="13" fill="currentColor"
										><path d="M8 1.5C5.5 1.5 3.5 3.6 3.5 6.2c0 3.4 3.6 7.5 4.2 8.1.2.2.5.2.6 0 .6-.6 4.2-4.7 4.2-8.1C12.5 3.6 10.5 1.5 8 1.5zm0 7a2 2 0 1 1 0-4 2 2 0 0 1 0 4z"
									/></svg>
								</div>
								<div class="loc-text">
									<p class="info-kicker">Location</p>
									<h1 class="info-title">{data.asset?.label || 'Asset'}</h1>
									{#if location.coordsLabel || location.placeLabel}
										<p class="info-sub">
											{#if location.coordsLabel}<span class="info-coords">{location.coordsLabel}</span>{/if}
											{#if location.coordsLabel && location.placeLabel}<span class="info-sep"> · </span>{/if}
											{#if location.placeLabel}<span class="info-place">{location.placeLabel}</span>{/if}
										</p>
									{/if}
								</div>
							</div>

							<!-- Vertical meta list -->
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
								{#if location.pondType}
									<div class="info-row">
										<dt class="info-dt">
											<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
												><path fill="currentColor" d="M8 1.2C5.8 3.8 4 5.9 4 8a4 4 0 1 0 8 0c0-2.1-1.8-4.2-4-6.8z"
											/></svg>
											Pond type
										</dt>
										<dd class="info-dd">{location.pondType}</dd>
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
								{#if ot.fp_ot_length != null}
									<div class="info-row">
										<dt class="info-dt">
											<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
												><path d="M1 8h14M3 5l-2 3 2 3M13 5l2 3-2 3" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round"
											/></svg>
											L × B × H
										</dt>
										<dd class="info-dd">{fmt(pondDims.L)} × {fmt(pondDims.B)} × {fmt(pondDims.D)} m</dd>
									</div>
									<div class="info-row">
										<dt class="info-dt">
											<svg class="info-ico" viewBox="0 0 16 16" aria-hidden="true"
												><rect x="2.5" y="2.5" width="11" height="11" rx="1" stroke="currentColor" stroke-width="1.4" fill="none"
											/></svg>
											Surface area
										</dt>
										<dd class="info-dd">{fmt(surfaceArea)} m²</dd>
									</div>
								{/if}
							</dl>

							<button
								type="button"
								class="asset-info-btn"
								onclick={() => (showAssetInfo = true)}
							>
								View full asset information
							</button>

							<!-- Map in first column -->
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
								<span class="legend-item"><span class="legend-dot"></span> Farm pond</span>
							</div>
						</div>
					</section>

					<!-- Col 2: one metric per row with formula + raw inputs -->
					<section class="dash-col dash-vis">
						<div class="dash-card dash-card-fill stats-card">
							<div class="panel-head">
								<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
									><path fill="currentColor" d="M2 3h12v2H2V3zm0 4h12v2H2V7zm0 4h8v2H2v-2z"
								/></svg>
								<h2 class="panel-title">Summary statistics</h2>
							</div>
							<ul class="pond-metrics">
								{#each pondLabels as item (item.key)}
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
					<!-- Diagrams row: plan + section side by side -->
					<div class="dash-card dims-row-card">
						<div class="panel-head panel-head-spread">
							<div class="panel-head">
								<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
									><rect x="2" y="2" width="12" height="12" rx="1.5" stroke="currentColor" stroke-width="1.4" fill="none"
								/></svg>
								<h2 class="panel-title">Pond dimensions</h2>
							</div>
							<div class="dims-legend">
								<span class="dims-leg"><span class="dims-swatch dims-swatch-top"></span> Top opening</span>
								<span class="dims-leg"><span class="dims-swatch dims-swatch-bottom"></span> Bottom / surface area</span>
								<span class="dims-leg"><span class="dims-swatch dims-swatch-water"></span> Current water</span>
							</div>
						</div>
						<div class="pond-diagrams-row">
							<!-- Plan view -->
							<div class="pond-diagram-box">
								<svg class="pond-svg" viewBox="0 0 {pondGeom.plan.viewW} {pondGeom.plan.viewH}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Plan view">
									<defs><marker id="dimArrow" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#334155"/></marker></defs>
									<!-- Light blue: top opening at ground level -->
									<rect x={pondGeom.plan.outer.x} y={pondGeom.plan.outer.y} width={pondGeom.plan.outer.w} height={pondGeom.plan.outer.h} fill="#bfdbfe" stroke="#1e3a8a" stroke-width="1.8"/>
									<!-- Current water surface -->
									{#if pondDims.h > 0.01}
										<rect x={pondGeom.plan.water.x} y={pondGeom.plan.water.y} width={pondGeom.plan.water.w} height={pondGeom.plan.water.h} fill="#1d4ed8" fill-opacity="0.35" stroke="#1e40af" stroke-width="1.2"/>
									{/if}
									<!-- Medium blue: pond bottom (L × B) -->
									<rect x={pondGeom.plan.inner.x} y={pondGeom.plan.inner.y} width={pondGeom.plan.inner.w} height={pondGeom.plan.inner.h} fill="#93c5fd" stroke="#1e3a8a" stroke-width="1.5"/>
									{#each pondGeom.plan.corners.lines as line}
										<line x1={line[0][0]} y1={line[0][1]} x2={line[1][0]} y2={line[1][1]} stroke="#1e3a8a" stroke-width="1.2"/>
									{/each}
									<text x={pondGeom.plan.outer.x + 4} y={pondGeom.plan.outer.y + 11} fill="#1e3a8a" font-size="8" font-weight="600">Top</text>
									<text x={pondGeom.plan.inner.x + pondGeom.plan.inner.w/2} y={pondGeom.plan.inner.y + pondGeom.plan.inner.h/2 - 2} text-anchor="middle" fill="#0f2744" font-size="11" font-weight="700">{fmt(surfaceArea)} m²</text>
									<text x={pondGeom.plan.inner.x + pondGeom.plan.inner.w/2} y={pondGeom.plan.inner.y + pondGeom.plan.inner.h/2 + 10} text-anchor="middle" fill="#1e3a8a" font-size="8" font-weight="600">bottom</text>
									{#if pondDims.h > 0.01}
										<text x={pondGeom.plan.water.x + pondGeom.plan.water.w/2} y={pondGeom.plan.water.y + 10} text-anchor="middle" fill="#1e40af" font-size="8" font-weight="600">WL {fmt(pondDims.h)} m</text>
									{/if}
									<line x1={pondGeom.plan.lenArrow.x1} y1={pondGeom.plan.lenArrow.y} x2={pondGeom.plan.lenArrow.x2} y2={pondGeom.plan.lenArrow.y} stroke="#334155" stroke-width="1" marker-start="url(#dimArrow)" marker-end="url(#dimArrow)"/>
									<text x={(pondGeom.plan.lenArrow.x1+pondGeom.plan.lenArrow.x2)/2} y={pondGeom.plan.lenArrow.y+11} text-anchor="middle" fill="#1a2530" font-size="10" font-weight="600">Length {fmt(pondDims.L)} m</text>
									<line x1={pondGeom.plan.brArrow.x} y1={pondGeom.plan.brArrow.y1} x2={pondGeom.plan.brArrow.x} y2={pondGeom.plan.brArrow.y2} stroke="#334155" stroke-width="1" marker-start="url(#dimArrow)" marker-end="url(#dimArrow)"/>
									<text x={pondGeom.plan.brArrow.x+10} y={(pondGeom.plan.brArrow.y1+pondGeom.plan.brArrow.y2)/2+4} text-anchor="start" fill="#1a2530" font-size="10" font-weight="600">Breadth {fmt(pondDims.B)} m</text>
								</svg>
							</div>
							<!-- Section view -->
							<div class="pond-diagram-box">
								<svg class="pond-svg" viewBox="0 0 {pondGeom.section.viewW} {pondGeom.section.viewH}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Section view">
									<defs>
										<linearGradient id="pondEmpty" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#dbeafe"/><stop offset="100%" stop-color="#93c5fd"/></linearGradient>
										<marker id="dimArrowSec" viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#334155"/></marker>
									</defs>
									<line x1="10" y1={pondGeom.section.groundY} x2={pondGeom.section.viewW-10} y2={pondGeom.section.groundY} stroke="#94a3b8" stroke-width="1.2"/>
									{#each Array.from({length:9},(_,i)=>20+i*30) as gx}
										<line x1={gx} y1={pondGeom.section.groundY} x2={gx-7} y2={pondGeom.section.groundY+9} stroke="#cbd5e1" stroke-width="1"/>
									{/each}
									{#each pondGeom.section.bunds as bund}
										<polygon points={`${bund.x},${pondGeom.section.groundY} ${bund.x+bund.w*0.25},${bund.y} ${bund.x+bund.w*0.75},${bund.y} ${bund.x+bund.w},${pondGeom.section.groundY}`} fill="#d6d3d1" stroke="#78716c" stroke-width="1"/>
									{/each}
									<!-- Light blue: empty excavation to full height -->
									<polygon points={polyPoints(pondGeom.section.excavation)} fill="url(#pondEmpty)" stroke="#1e3a8a" stroke-width="1.6"/>
									<!-- Dark blue: current water -->
									{#if pondGeom.section.water}
										<polygon points={polyPoints(pondGeom.section.water)} fill="#1d4ed8" opacity="0.7" stroke="#1e3a8a" stroke-width="1"/>
										<line x1={pondGeom.section.water[0][0]} y1={pondGeom.section.waterTopY} x2={pondGeom.section.water[3][0]} y2={pondGeom.section.waterTopY} stroke="#1e40af" stroke-width="1.4" stroke-dasharray="3 2"/>
									{/if}
									<!-- Full pond height -->
									<line x1={pondGeom.section.htArrow.x} y1={pondGeom.section.htArrow.y1} x2={pondGeom.section.htArrow.x} y2={pondGeom.section.htArrow.y2} stroke="#334155" stroke-width="1" marker-start="url(#dimArrowSec)" marker-end="url(#dimArrowSec)"/>
									<text x={pondGeom.section.htArrow.x-10} y={(pondGeom.section.htArrow.y1+pondGeom.section.htArrow.y2)/2} text-anchor="middle" fill="#1a2530" font-size="9" font-weight="600" transform="rotate(-90 {pondGeom.section.htArrow.x-10} {(pondGeom.section.htArrow.y1+pondGeom.section.htArrow.y2)/2})">Height {fmt(pondDims.D)} m</text>
									<!-- Current water level height -->
									{#if pondGeom.section.wlArrow}
										<line x1={pondGeom.section.wlArrow.x} y1={pondGeom.section.wlArrow.y1} x2={pondGeom.section.wlArrow.x} y2={pondGeom.section.wlArrow.y2} stroke="#1d4ed8" stroke-width="1.2" marker-start="url(#dimArrowSec)" marker-end="url(#dimArrowSec)"/>
										<text x={pondGeom.section.wlArrow.x+11} y={(pondGeom.section.wlArrow.y1+pondGeom.section.wlArrow.y2)/2} text-anchor="middle" fill="#1d4ed8" font-size="9" font-weight="700" transform="rotate(90 {pondGeom.section.wlArrow.x+11} {(pondGeom.section.wlArrow.y1+pondGeom.section.wlArrow.y2)/2})">WL {fmt(pondDims.h)} m</text>
									{/if}
									<line x1={pondGeom.section.lenArrow.x1} y1={pondGeom.section.lenArrow.y} x2={pondGeom.section.lenArrow.x2} y2={pondGeom.section.lenArrow.y} stroke="#334155" stroke-width="1" marker-start="url(#dimArrowSec)" marker-end="url(#dimArrowSec)"/>
									<text x={(pondGeom.section.lenArrow.x1+pondGeom.section.lenArrow.x2)/2} y={pondGeom.section.lenArrow.y+11} text-anchor="middle" fill="#1a2530" font-size="10" font-weight="600">Length {fmt(pondDims.L)} m</text>
								</svg>
							</div>
						</div>
					</div>

					<section class="dash-card chart-card">
						<div class="panel-head panel-head-spread">
							<div class="panel-head">
								<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
									><path
										fill="currentColor"
										d="M1.5 12.5 5 8l3 3 5.5-7.5V12.5H1.5z"
									/></svg
								>
								<h2 class="panel-title">Water level vs rainfall</h2>
							</div>
							<div class="chart-legend">
								<span class="chart-leg"
									><span class="leg-swatch" style="background:#1e3a8a"></span> WL</span
								>
								<span class="chart-leg"
									><span class="leg-swatch" style="background:#93c5fd"></span> Daily rain</span
								>
								<span class="chart-leg"
									><span class="leg-swatch" style="background:#4ade80"></span> Cum. rain</span
								>
							</div>
						</div>
						<div bind:this={chartEl} class="chart-host relative"></div>
					</section>

					<section class="dash-card heat-card">
						<div class="panel-head panel-head-spread">
							<div class="panel-head">
								<svg class="panel-ico" viewBox="0 0 16 16" aria-hidden="true"
									><path
										fill="currentColor"
										d="M2 2h4v4H2V2zm6 0h4v4H8V2zm6 0h2v4h-2V2zM2 8h4v4H2V8zm6 0h4v4H8V8zm6 0h2v4h-2V8zM2 14h4v2H2v-2zm6 0h4v2H8v-2zm6 0h2v2h-2v-2z"
									/></svg
								>
								<h2 class="panel-title">Collection calendar</h2>
							</div>
							<div class="heat-controls">
								<label class="heat-metric-label">
									<span>Colour by</span>
									<select bind:value={heatMetric}>
										<option value="collected">Collected (yes/no)</option>
										<option value="water_level">Water level</option>
										<option value="rainfall">Daily rainfall</option>
									</select>
								</label>
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
										<span class="year-label font-mono text-[11px]">{calWindow.label}</span>
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
						</div>
						<div bind:this={heatEl} class="heat-host relative"></div>
						<div class="heat-footer">
							{#if heatMetric === 'collected'}
								<span class="chart-leg"
									><span class="leg-swatch" style="background:{COLLECTED_YES}"></span> Yes</span
								>
								<span class="chart-leg"
									><span class="leg-swatch" style="background:{COLLECTED_NO}"></span> No</span
								>
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
					<div
						class="process-backdrop"
						role="presentation"
						onclick={() => (processKey = null)}
						onkeydown={(e) => e.key === 'Escape' && (processKey = null)}
					></div>
					<div
						class="process-panel"
						role="dialog"
						aria-modal="true"
						aria-labelledby="process-title"
					>
						<div class="process-panel-head">
							<h3 id="process-title" class="process-title">{processItem.label}</h3>
							<button
								type="button"
								class="process-close"
								aria-label="Close"
								onclick={() => (processKey = null)}
							>
								×
							</button>
						</div>
						<p class="process-value">
							{fmt(processItem.value)}{processItem.unit ? ` ${processItem.unit}` : ''}
						</p>
						<p class="process-formula"><span class="metric-k">Formula</span> {processItem.formula}</p>
						{#if processItem.raws?.length}
							<p class="process-raws">
								<span class="metric-k">Inputs</span>
								{processItem.raws.join(' · ')}
							</p>
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
					<div
						class="process-backdrop"
						role="presentation"
						onclick={() => (showAssetInfo = false)}
					></div>
					<div
						class="process-panel asset-info-panel"
						role="dialog"
						aria-modal="true"
						aria-labelledby="asset-info-title"
					>
						<div class="process-panel-head">
							<h3 id="asset-info-title" class="process-title">
								{data.asset?.label || 'Asset'} — full information
							</h3>
							<button
								type="button"
								class="process-close"
								aria-label="Close"
								onclick={() => (showAssetInfo = false)}
							>
								×
							</button>
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
							<p class="process-desc">No one-time survey answers recorded for this asset.</p>
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
		height: 160px;
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
		flex: 1.4;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.heat-card {
		flex: 1;
		min-height: 0;
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
		width: 100%;
		flex: 1;
		min-height: 0;
		overflow: hidden;
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
</style>
