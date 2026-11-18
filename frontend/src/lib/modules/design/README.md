# Design module (frontend)

Solution site-suitability on top of a saved AOI.

- `api.js` — `/api/design` client. AOI resolution (map click, village, upload) re-exports the
  Diagnose watershed helpers so both modules pick places identically.
- `components/DesignProjectPicker.svelte` — project list + create flow (`routes/design`). AOI
  sources: **From PD project** (copies a Problem Diagnosis watershed you can access), map click,
  village, or uploaded polygon.
- `components/SolutionDesigner.svelte` — project page (`routes/design/[slug]`). Solutions from
  `backend/app/modules/design/data/site_suitability.csv` are ranked most-feasible first and act
  as map layers: selecting one draws the areas (Areal/Point) or stream reaches (Instream) that
  meet its slope, stream-order and LULC criteria. The top-ranked solution is shown by default.
  On first open the panel asks whether to **view all solutions** or **choose a custom list**;
  the choice is remembered per project in the browser and can be changed from the panel header.
- `components/WatershedStats.svelte` — collapsible left sidebar: AOI details (source, area,
  perimeter, centroid) plus slope classes, LULC breakdown and drainage length/density by
  Strahler order, from `GET /api/design/projects/{id}/stats`.

Backend: `backend/app/modules/design/` (`services/suitability.py` does the GIS).
