# Diagnose Module

The Diagnose module is the core of the DDA product. It provides watershed-based field mapping with observation zones, geotagged field notes, and offline sync via QField Cloud.

## Capabilities

### Watershed-Scoped Projects

- A user creates a diagnosis project by clicking a point on the map
- The backend looks up the watershed boundary at that coordinate using a FlatGeobuf file stored in S3
- The project is tied to the detected watershed polygon, which defines its spatial extent
- The watershed geometry is stored in PostGIS and used to clip raster tiles and scope data queries

### Interactive Map

- Built with MapLibre GL JS
- Resizable left sidebar with layer controls
- Base layer options: OpenStreetMap and ESRI satellite imagery
- Secondary data layers: COG raster layers (e.g., LULC) served through Titiler, draggable for reorder
- Primary layers: Observation Zones, Hypotheses, and Field Notes
- Floating overlay cards on the right side for zone/note/hypothesis editing

### Observation Zones

- Polygon features drawn directly on the map using MapLibre GL Draw
- Each zone has a text label, observations, questions, and configurable color
- Zones can be edited (geometry, text, color) and deleted
- Stored as PostGIS geometries with POLYGON/MULTIPOLYGON constraint

### Hypotheses

- Testable statements created in the web app and linked to one or more observation zones
- New hypotheses start with status `untested`
- Field workers link field notes to a hypothesis as evidence (optional dropdown on the field note form)
- Back in the web app, users record a root cause and set status to `validated` or `invalidated`
- Validation requires at least one linked field note; `discarded` can be set without evidence

### Field Notes

- Geotagged point features placed on the map
- Each note has text content, optional photo and audio attachments, and an optional link to a hypothesis
- Media files are uploaded via multipart form and stored in S3 under `{project_id}/media/`
- Notes can be edited (text, geometry) and deleted; deletion cleans up S3 media

### COG Raster Layers

- Cloud-Optimized GeoTIFF layers stored in S3
- Served as map tiles through a Titiler proxy
- Tiles can be clipped to the project's watershed boundary
- Configurable via the `COG_LAYERS` environment variable

## QField Cloud Integration

### Per-User Accounts

Each user connects their own QField Cloud account via the settings page. The app stores the QField Cloud API token (not credentials) on the `users` row (`qfield_username`, `qfield_token`, `qfield_token_expires_at`). ODK Central tokens are stored the same way (`odk_username`, `odk_token`, `odk_token_expires_at`). If a token expires, the user reconnects from Settings → Connectors.

### Packaging to QField

When a user packages a diagnosis project:

1. A QGIS project file (`.qgs`) is generated using PyQGIS with the project's layers, data, and styling
2. Raster layers are clipped to the watershed boundary and converted to MBTiles (zoom range configurable via `QFIELD_RASTER_MIN_ZOOM`, `QFIELD_RASTER_MAX_ZOOM`)
3. Observation zones, hypotheses, and field notes are exported to GeoPackages (field notes include a Value Relation dropdown to pick a hypothesis)
4. Everything is uploaded to QField Cloud using the packaging user's token
5. The QField Cloud project is created in the user's QField Cloud account
6. Other users with diagnosis access are added as QField Cloud collaborators
7. Progress is streamed to the frontend via Server-Sent Events

### Syncing from QField

When a user syncs from QField Cloud:

1. Changes made in QField (offline edits, new notes, photos) are pulled down
2. Media files are migrated from QField Cloud to S3
3. The PostGIS database is updated with the synced data
4. Progress is streamed via SSE

### Collaborator Sync

When packaging, all users with access to the diagnosis (direct users and org members) are automatically added as collaborators on the QField Cloud project. This allows the whole team to sync from the same project in QField.

## Access Control

### Three-Tier Model

| Role | Capabilities |
|------|-------------|
| **Owner** | Full control. Can delete the project, manage all sharing, create/edit/delete zones and notes. |
| **Admin** | Can manage sharing (add/remove users and orgs, change roles). Can create/edit/delete zones and notes. |
| **Member** | Can view the project, create/edit/delete zones and notes. Cannot manage sharing. |

### Sharing Mechanisms

1. **Direct user grants**: The owner or an admin adds a user by email. Each granted user gets a role (admin or member).
2. **Organization grants**: The owner or an admin shares with an entire organization. All org members get access.

### Members Page

Each diagnosis project has a dedicated `/diagnose/[slug]/members` page showing:
- The project owner at the top with a purple "owner" badge
- All users with direct access, with role badges and management actions
- All organizations with access
- Admins see controls to add/remove users and orgs, change roles
- Non-owner members see a "Leave" button to remove their own access

## Design Decisions

### Per-User Connector Tokens on `users`

Rather than a separate `qfield_tokens` table or a server-wide token, each user stores their own QField Cloud and ODK Central credentials on the `users` row. Projects are created under the user's QField Cloud storage, and billing/quota stays with each user.

### Watershed as Spatial Scope

Projects are scoped to a watershed boundary rather than arbitrary bounding boxes. This provides a natural ecological unit for field work and enables meaningful raster clipping.

### S3 for Media Storage

Field note photos and audio are stored in S3 rather than locally. This decouples media storage from the API server and enables scalable access.

### SSE for Progress Streaming

Packaging and syncing can take significant time. Server-Sent Events provide real-time progress updates without polling or WebSocket complexity.

### Session-Based Auth with HttpOnly Cookies

Cookie-based sessions (not JWTs) are used because:
- Server-side session revocation is straightforward
- No token refresh logic needed on the client
- HttpOnly cookies prevent XSS-based token theft

### Diagnosis Admin Role

Beyond the owner, users can be promoted to "admin" on a diagnosis. This allows delegation of sharing management without transferring ownership. Admins can add/remove users and orgs but cannot delete the project.

### Hypothesis Workflow

Hypotheses connect observation zones (context) to field notes (evidence). The workflow is intentionally split between desk planning and field collection:

1. **Plan** — create a hypothesis and link relevant observation zones
2. **Collect** — field users attach notes to the hypothesis while on site
3. **Review** — back at the desk, record the root cause and mark validated or invalidated
