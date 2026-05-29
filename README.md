# WELLlabs DDA App

Early stage Geospatial watershed diagnosis and field annotation platform.

The application allows a user to:

- select a coordinate on a map

- query watershed boundaries from PostGIS

- return GeoJSON

- render watershed polygons on the frontend

This repository is the boilerplate/foundation for future development

---

# Tech Stack

## Backend

- Python 3.9+

- Django

- Django REST Framework

- PostGIS

- GDAL / GEOS

## Frontend

- SvelteKit

- TailwindCSS

- Leaflet

## Database

- PostgreSQL

- PostGIS extension

# Project Structure

```bash
welllabs-dda-app/
│
├── backend/
│   ├── config/
│   ├── core/
│   ├── requirements.txt
│   ├── manage.py
│   ├── .env
│   └── venv/
│
├── frontend/
│   ├── src/
│   ├── static/
│   ├── package.json
│   └── node_modules/
│
├── data/
│   └── raw/
│	      └── watersheds.gpkg
│
└── README.md
```

---

# System Requirements

Install:

- Python 3.9+
- PostgreSQL
- PostGIS
- GDAL
- GEOS
- Node.js
- npm
- Git

---

# Create PostgreSQL Database

Start PostgreSQL
```
# MacOS
brew services start postgresql

# Linux
sudo systemctl start postgresql
```

Open PostgreSQL shell:

```bash
psql postgres
```

Create database:

```sql
CREATE DATABASE ddaapp;

\c ddaapp

CREATE EXTENSION postgis;
```

Exit
```
\q
```
---

# Backend Setup

## Create Virtual Environment

```bash
cd backend

python -m venv venv
```

Activate:

### Linux/macOS

```bash
source venv/bin/activate
```

### Windows

```bash
venv\Scripts\activate
```
---

# Install Python Dependencies

```bash
pip install -r requirements.txt
```
---

# Environment File

Create:

```bash
backend/.env
```

Example:

```env
SECRET_KEY=your-secret-key

DB_NAME=ddaapp
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```
---

# Configure GDAL and GEOS

Edit these based on the path in your device. Most likely paths given below

In:
```
backend/config/settings.py
```

MacOS
```
# Apple silicon
GDAL_LIBRARY_PATH = "/opt/homebrew/opt/gdal/lib/libgdal.dylib"
GEOS_LIBRARY_PATH = "/opt/homebrew/opt/geos/lib/libgeos_c.dylib"

#Intel
GDAL_LIBRARY_PATH = "/usr/local/opt/gdal/lib/libgdal.dylib"
GEOS_LIBRARY_PATH = "/usr/local/opt/geos/lib/libgeos_c.dylib"
```

Linux
```
GDAL_LIBRARY_PATH = "/usr/lib/libgdal.so"
GEOS_LIBRARY_PATH = "/usr/lib/libgeos_c.so"
```

Windows
```
GDAL_LIBRARY_PATH = r"C:\OSGeo4W\bin\gdal308.dll"
GEOS_LIBRARY_PATH = r"C:\OSGeo4W\bin\geos_c.dll"
```

# Create Data Folders

From project root:

```bash
mkdir -p data/raw
```

---

# Import Watershed Layer

Place watershed data inside:

```bash
data/raw/watersheds.gpkg
```

Import:

```bash
ogr2ogr \
-f PostgreSQL \
PG:"dbname=ddaapp user=postgres" \
data/raw/watersheds.gpkg \
-nln watersheds
```

---

# Run Django Backend

## Run Migrations

```bash
python manage.py migrate
```

## Start Backend Server

```bash
python manage.py runserver
```

Backend URL:

```text
http://127.0.0.1:8000
```

---

# Backend Health Check

Example endpoint:

```text
http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "ok"
}
```

---

# Backend API Test

Example watershed lookup:

```text
http://127.0.0.1:8000/api/watershed/?lat=12.9&lng=77.7
```

Expected response:

```json
{
  "fid": 1,
  "id": "watershed_id",
  "uid": "watershed_uid",
  "geom": {
    "type": "MultiPolygon"
  }
}
```

---

# Frontend Setup

Go to frontend:

```bash
cd frontend
```

Install dependencies:

```bash
npm install
```

Run frontend:

```bash
npm run dev
```

Frontend URL:

```text
http://localhost:5173
```

---

