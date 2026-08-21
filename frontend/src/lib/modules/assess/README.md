# Assess module (frontend)

MEL plan (Monitoring, Evaluation, Learning) designer.

The Assess route is intentionally limited to MEL plan design and publishing to **ODK Central** (creates + publishes an ODK form from selected indicators).

Key pieces:

- `components/MelPlanDesigner.svelte` — the MEL plan wizard (intervention → outcomes → indicators → publish form)
- `mel-api.js` — client for MEL plan endpoints under `/api/assess/mel/*`
