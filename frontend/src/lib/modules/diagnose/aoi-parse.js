/** Parse uploaded AOI files (GeoJSON / KML / GPX) into a Polygon or MultiPolygon. */

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
		const geometry = extractPolygon(parsed);
		if (!geometry) throw new Error('GeoJSON must contain a Polygon or MultiPolygon');
		return { geometry, name: stem(name) };
	}

	if (lower.endsWith('.kml') || lower.endsWith('.gpx')) {
		const { kml, gpx } = await import('@tmcw/togeojson');
		const doc = new DOMParser().parseFromString(text, 'text/xml');
		const parseErr = doc.querySelector('parsererror');
		if (parseErr) throw new Error('Could not parse XML file');
		const fc = lower.endsWith('.kml') ? kml(doc) : gpx(doc);
		const geometry = extractPolygon(fc);
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
