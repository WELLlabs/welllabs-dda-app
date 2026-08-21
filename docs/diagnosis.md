# Diagnose Module

The Diagnose module is the core of the Water Security Tool. It provides watershed-based field
mapping with secondary data layers, watershed analysis, 3D DEM draping, observation zones,
hypotheses, geotagged field notes, and offline sync via QField Cloud.

## Capabilities

### Watershed-Scoped Projects

- A user creates a diagnosis project by clicking a point on the map
- The backend looks up the watershed boundary at that coordinate using a FlatGeobuf/GPKG file on S3 (`WATERSHEDS_FGB_KEY`)
- The project is tied to the detected watershed polygon, which defines its spatial extent
- The watershed geometry is stored in PostGIS and used to clip raster tiles, scope vector queries, and drive analysis

### Interactive Map (2D)

- Built with MapLibre GL JS
- Resizable left sidebar with layer controls
- Base layer options: OpenStreetMap and ESRI satellite imagery
- Secondary layers: COG rasters (Titiler) and FlatGeobuf vectors, reorderable
- Primary layers: Observation Zones, Hypotheses, and Field Notes
- Floating overlay cards for zone / note / hypothesis editing and layer analysis panels

### 3D Terrain Viewer

- Toggle **3D** on the map to open a Plotly surface of the watershed DEM
- DEM mesh comes from `GET /api/diagnose/layers/dem/mesh`
- Selecting a secondary layer drapes it on the DEM via `GET /api/diagnose/layers/{layer_id}/drape-grid`
- Categorical layers use stepped colorscales from `layers.yaml`; continuous / choropleth layers use their catalog styling
- Turntable rotation; relief can be kept minimal so drape colors stay readable

### Secondary Layers & Catalog

Layer enablement is env-driven; styling and analysis copy live in
`backend/app/modules/diagnose/config/layers.yaml`:

| Env | Role |
|-----|------|
| `COG_LAYERS` | Comma-separated COG keys (e.g. LULC, DEM, JRC occurrence/transition) |
| `VECTOR_LAYERS` | Comma-separated FlatGeobuf keys (aquifers, gw_stress, village_resilience, villages) |

Typical catalog entries today:

- **Raster:** LULC 250k, DEM, JRC surface water occurrence / transitions
- **Vector:** Aquifers, WISER groundwater stress, irrigation access / kharif / rabi resilience, baseline population, marginalized % SC/ST

Each layer can declare `analysis_type`, legend classes or choropleth stops, meaning, uncertainty, and field-check text. The map preloads batch analysis for the watershed and shows evidence stats in the sidebar.

### Observation Zones

- Polygon features drawn with MapLibre GL Draw
- Each zone has a text label, observations, questions, and configurable color
- Stored as PostGIS geometries with POLYGON/MULTIPOLYGON constraint

### Hypotheses

- Testable statements linked to one or more observation zones
- New hypotheses start with status `untested`
- Field notes can link to a hypothesis as evidence
- Desk review records a root cause and sets `validated` or `invalidated` (requires ≥1 linked note); `discarded` needs no evidence

### Field Notes

- Geotagged points with title, text, optional photo/audio, optional hypothesis link
- Media uploaded multipart and stored in S3 under `{project_id}/media/`
- Delete cleans up S3 media

### COG Raster Tiles

- Cloud-Optimized GeoTIFFs in S3, tiled via Titiler (proxied through the API)
- Optional watershed clip for project views
- Per-layer colormaps from the catalog (categorical gdaldem / Titiler colormap, continuous colormaps)

## QField Cloud Integration

### Per-User Accounts

Each user connects their own QField Cloud account via settings. The app stores the API token on
`users` (`qfield_username`, `qfield_token`, `qfield_token_expires_at`). ODK tokens are stored
the same way for Assess. Expired tokens are renewed from Settings → Connectors.

### Packaging to QField

1. A QGIS project (`.qgs`) is generated with project layers, data, and styling
2. Rasters are clipped to the watershed and converted to MBTiles (`QFIELD_RASTER_MIN_ZOOM` / `MAX_ZOOM`)
3. Observation zones, hypotheses, and field notes export to GeoPackages
4. Package uploads to QField Cloud under the packaging user's token
5. Collaborators with diagnosis access are added on QField Cloud
6. Progress streams to the frontend via Server-Sent Events

### Syncing from QField

1. Offline edits and new notes/photos are pulled from QField Cloud
2. Media migrate to S3
3. PostGIS updates with synced data
4. Progress streams via SSE

## Access Control

### Three-Tier Model

| Role | Capabilities |
|------|-------------|
| **Owner** | Full control including delete and sharing |
| **Admin** | Manage sharing; create/edit/delete zones and notes |
| **Member** | View project; create/edit/delete zones and notes; no sharing admin |

### Sharing

1. **Direct user grants** by email (`admin` or `member`)
2. **Organization grants** — all org members get access

### Members Page

`/diagnose/[slug]/members` lists the owner, direct users, and orgs, with admin controls to
add/remove grants and change roles. Non-owner members can leave.

## Design Decisions

### Per-User Connector Tokens

QField Cloud tokens live in `user_qfield_credentials` (1:1 with `users`). ODK Central for Assess
uses server env (`ODK_*`); see [settings.md](settings.md) and [assess.md](assess.md).

### Watershed as Spatial Scope

Projects use watershed boundaries (not arbitrary boxes) for clipping, analysis, and 3D mesh extents.

### Layer Catalog vs Env Enablement

`COG_LAYERS` / `VECTOR_LAYERS` decide what is active; `layers.yaml` owns colors, legends, and
analysis semantics so styling is not hard-coded in the frontend.

### Dual-Surface 3D Drape

The DEM provides elevation; a second Plotly surface carries layer colors sampled onto the same
EPSG:4326 mesh so categorical and choropleth layers stay aligned with terrain.

### S3 for Media

Field note media stays in S3 so the API remains stateless for blobs.

### SSE for Progress

Packaging and sync can take minutes; SSE avoids polling and WebSocket complexity.

### Session Auth

HttpOnly cookie JWT (`dda_session`) via FastAPI Users. See [auth.md](auth.md).

### Hypothesis Workflow

1. **Plan** — create hypothesis and link zones  
2. **Collect** — attach field notes as evidence  
3. **Review** — root cause + validated / invalidated  
