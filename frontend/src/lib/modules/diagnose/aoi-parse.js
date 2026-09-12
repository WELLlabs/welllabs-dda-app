/** Parse uploaded AOI files (GeoJSON / KML / GPX) into a Polygon or MultiPolygon. */

/** Soft cap before POST — dense GP/cadastral KMLs otherwise 502 Cloudflare. */
const TARGET_VERTICES = 8000;
const MAX_VERTICES = 50000;

/**
 * @param {File} file
 * @returns {Promise<{ geometry: object, name: string }>}
 */
export async function parseAoiFile(file) {
	const name = file.name || 'Custom AOI';
	const lower = name.toLowerCase();
	const text = await file.text();

	if (lower.endsWith('.geojson') || lower.endsWith('.json')) {
		const parsed = JSON.parse(text);
		const geometry = thinPolygon(extractPolygon(parsed));
		if (!geometry) throw new Error('GeoJSON must contain a Polygon or MultiPolygon');
		return { geometry, name: stem(name) };
	}

	if (lower.endsWith('.kml') || lower.endsWith('.gpx')) {
		const { kml, gpx } = await import('@tmcw/togeojson');
		const doc = new DOMParser().parseFromString(text, 'text/xml');
		const parseErr = doc.querySelector('parsererror');
		if (parseErr) throw new Error('Could not parse XML file');
		const fc = lower.endsWith('.kml') ? kml(doc) : gpx(doc);
		const geometry = thinPolygon(extractPolygon(fc));
		if (!geometry) {
			throw new Error(
				lower.endsWith('.gpx')
					? 'GPX must include a closed polygon (tracks/routes alone are not supported)'
					: 'KML must contain a Polygon or MultiPolygon'
			);
		}
		return { geometry, name: stem(name) };
	}

	throw new Error('Unsupported file type — use .geojson, .json, .kml, or .gpx');
}

function stem(filename) {
	return filename.replace(/\.[^.]+$/, '') || 'Custom AOI';
}

/**
 * @param {object} input
 * @returns {object|null}
 */
export function extractPolygon(input) {
	if (!input || typeof input !== 'object') return null;

	if (input.type === 'Polygon' || input.type === 'MultiPolygon') {
		return input;
	}

	if (input.type === 'Feature' && input.geometry) {
		return extractPolygon(input.geometry);
	}

	if (input.type === 'FeatureCollection' && Array.isArray(input.features)) {
		const polys = [];
		for (const f of input.features) {
			const g = extractPolygon(f);
			if (!g) continue;
			if (g.type === 'Polygon') polys.push(g.coordinates);
			else if (g.type === 'MultiPolygon') polys.push(...g.coordinates);
		}
		if (polys.length === 1) return { type: 'Polygon', coordinates: polys[0] };
		if (polys.length > 1) return { type: 'MultiPolygon', coordinates: polys };
		return null;
	}

	if (input.type === 'GeometryCollection' && Array.isArray(input.geometries)) {
		return extractPolygon({
			type: 'FeatureCollection',
			features: input.geometries.map((geometry) => ({ type: 'Feature', geometry, properties: {} }))
		});
	}

	return null;
}

/**
 * Drop excess ring vertices so create/preview POSTs stay under Cloudflare limits.
 * @param {object|null} geometry
 * @returns {object|null}
 */
export function thinPolygon(geometry) {
	if (!geometry) return null;
	const count = countVertices(geometry);
	if (count > MAX_VERTICES) {
		throw new Error(
			`AOI has too many vertices (${count.toLocaleString()}; max ${MAX_VERTICES.toLocaleString()}). ` +
				'Simplify the polygon in QGIS/Earth or upload a coarser boundary.'
		);
	}
	if (count <= TARGET_VERTICES) return roundCoords(geometry, 6);

	let step = Math.max(2, Math.ceil(count / TARGET_VERTICES));
	let thinned = decimateGeometry(geometry, step);
	// One more pass if still dense (very uneven rings).
	if (countVertices(thinned) > TARGET_VERTICES * 1.25) {
		step = Math.max(step + 1, Math.ceil(countVertices(thinned) / TARGET_VERTICES));
		thinned = decimateGeometry(thinned, step);
	}
	return roundCoords(thinned, 6);
}

function countVertices(geometry) {
	if (!geometry?.coordinates) return 0;
	if (geometry.type === 'Polygon') return geometry.coordinates.reduce((n, ring) => n + ring.length, 0);
	if (geometry.type === 'MultiPolygon') {
		return geometry.coordinates.reduce(
			(n, poly) => n + poly.reduce((m, ring) => m + ring.length, 0),
			0
		);
	}
	return 0;
}

function decimateGeometry(geometry, step) {
	if (geometry.type === 'Polygon') {
		return { type: 'Polygon', coordinates: geometry.coordinates.map((ring) => decimateRing(ring, step)) };
	}
	return {
		type: 'MultiPolygon',
		coordinates: geometry.coordinates.map((poly) => poly.map((ring) => decimateRing(ring, step)))
	};
}

/** Keep first/last point; stride the rest. Always close the ring. */
function decimateRing(ring, step) {
	if (!Array.isArray(ring) || ring.length <= 4) return ring;
	const out = [];
	for (let i = 0; i < ring.length - 1; i += step) {
		out.push(ring[i]);
	}
	const first = out[0];
	if (!first) return ring;
	// Ensure closed ring (GeoJSON LinearRing).
	const last = out[out.length - 1];
	if (!last || last[0] !== first[0] || last[1] !== first[1]) {
		out.push([first[0], first[1]]);
	}
	// Need a valid linear ring (≥4 positions including close).
	while (out.length < 4) {
		out.splice(out.length - 1, 0, out[out.length - 2] || first);
	}
	return out;
}

function roundCoords(geometry, precision) {
	const roundPt = (pt) => pt.map((c, i) => (i < 2 ? Number(Number(c).toFixed(precision)) : c));
	if (geometry.type === 'Polygon') {
		return { type: 'Polygon', coordinates: geometry.coordinates.map((ring) => ring.map(roundPt)) };
	}
	return {
		type: 'MultiPolygon',
		coordinates: geometry.coordinates.map((poly) => poly.map((ring) => ring.map(roundPt)))
	};
}
