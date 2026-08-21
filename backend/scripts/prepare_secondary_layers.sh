#!/usr/bin/env bash
# Convert source GPKG/GeoJSON layers to FlatGeobuf and upload to the DDA S3 bucket.
#
# Usage:
#   ./scripts/prepare_secondary_layers.sh /path/to/datasets
#
# Expected input filenames (any that exist will be converted):
#   Aquifers.gpkg
#   Karnataka_GW_stress*.gpkg | GW_Stress.gpkg | Groundwater_Stress.gpkg
#   Irrigation_Access*.gpkg | WISER_Irrigation*.gpkg
#   Kharif_Resilience*.gpkg | WISER_Kharif*.gpkg
#   Rabi_Resilience*.gpkg | WISER_Rabi*.gpkg
#   Village Boundaries CF.gpkg | villages.gpkg
#   India.tif | dem*.tif  (copied as dem_india.tif COG if already COG, else gdal_translate)
#
# Requires: ogr2ogr (GDAL), aws CLI, optional gdal_translate for DEM.

set -euo pipefail

SRC_DIR="${1:-.}"
OUT_DIR="${OUT_DIR:-/tmp/dda-secondary-layers}"
BUCKET="${AWS_S3_BUCKET:-well-labs-dda-product-dev-bucket}"
REGION="${AWS_DEFAULT_REGION:-ap-south-1}"

mkdir -p "$OUT_DIR/vector"

pick_first() {
  local pattern
  for pattern in "$@"; do
    # shellcheck disable=SC2086
    local match
    match="$(ls -1 $SRC_DIR/$pattern 2>/dev/null | head -n 1 || true)"
    if [[ -n "$match" ]]; then
      echo "$match"
      return 0
    fi
  done
  return 1
}

to_fgb() {
  local src="$1"
  local dest="$2"
  echo "→ FlatGeobuf: $(basename "$src") → $dest"
  ogr2ogr -f FlatGeobuf -nlt PROMOTE_TO_MULTI -lco SPATIAL_INDEX=YES "$dest" "$src"
}

upload() {
  local file="$1"
  local key="$2"
  echo "↑ s3://$BUCKET/$key"
  aws s3 cp "$file" "s3://$BUCKET/$key" --region "$REGION"
}

echo "Source dir: $SRC_DIR"
echo "Output dir: $OUT_DIR"
echo "Bucket:     s3://$BUCKET"

if aq="$(pick_first 'Aquifers.gpkg' 'aquifers.gpkg')"; then
  to_fgb "$aq" "$OUT_DIR/vector/aquifers.fgb"
  upload "$OUT_DIR/vector/aquifers.fgb" "vector/aquifers.fgb"
  echo "  Tip: inspect unique aquifer values with:"
  echo "    ogrinfo -al -so $OUT_DIR/vector/aquifers.fgb | head"
  echo "    python -c \"import geopandas as gpd; print(gpd.read_file('$OUT_DIR/vector/aquifers.fgb')['aquifer'].value_counts())\""
else
  echo "⚠ Aquifers source not found"
fi

if gw="$(pick_first 'Karnataka_GW_stress*.gpkg' 'GW_Stress.gpkg' 'Groundwater_Stress.gpkg' 'WISER_GW_Stress.gpkg' 'gw_stress.gpkg')"; then
  to_fgb "$gw" "$OUT_DIR/vector/gw_stress.fgb"
  upload "$OUT_DIR/vector/gw_stress.fgb" "vector/gw_stress.fgb"
else
  echo "⚠ GW Stress source not found"
fi

if irr="$(pick_first 'Irrigation_Access*.gpkg' 'WISER_Irrigation*.gpkg' 'irrigation_access.gpkg')"; then
  to_fgb "$irr" "$OUT_DIR/vector/irrigation_access.fgb"
  upload "$OUT_DIR/vector/irrigation_access.fgb" "vector/irrigation_access.fgb"
else
  echo "⚠ Irrigation Access source not found"
fi

if kh="$(pick_first 'Kharif_Resilience*.gpkg' 'WISER_Kharif*.gpkg' 'kharif_resilience.gpkg')"; then
  to_fgb "$kh" "$OUT_DIR/vector/kharif_resilience.fgb"
  upload "$OUT_DIR/vector/kharif_resilience.fgb" "vector/kharif_resilience.fgb"
else
  echo "⚠ Kharif Resilience source not found"
fi

if rb="$(pick_first 'Rabi_Resilience*.gpkg' 'WISER_Rabi*.gpkg' 'rabi_resilience.gpkg')"; then
  to_fgb "$rb" "$OUT_DIR/vector/rabi_resilience.fgb"
  upload "$OUT_DIR/vector/rabi_resilience.fgb" "vector/rabi_resilience.fgb"
else
  echo "⚠ Rabi Resilience source not found"
fi

if vil="$(pick_first 'Village Boundaries CF.gpkg' 'villages.gpkg' 'Village*.gpkg')"; then
  to_fgb "$vil" "$OUT_DIR/vector/villages.fgb"
  upload "$OUT_DIR/vector/villages.fgb" "vector/villages.fgb"
  echo "  Tip: compute population / SC-ST quantile stops:"
  echo "    python - <<'PY'"
  echo "import geopandas as gpd, numpy as np"
  echo "g=gpd.read_file('$OUT_DIR/vector/villages.fgb')"
  echo "print(np.nanpercentile(g['Total_Popu'], [20,40,60,80]))"
  echo "pct=((g['Total_SC_P']+g['Total_ST_P'])/g['Total_Popu'].replace(0,np.nan))*100"
  echo "print(np.nanpercentile(pct, [20,40,60,80]))"
  echo "PY"
else
  echo "⚠ Villages source not found"
fi

if dem="$(pick_first 'India.tif' 'dem_india.tif' 'dem*.tif')"; then
  dest="$OUT_DIR/dem_india.tif"
  echo "→ DEM COG: $(basename "$dem") → $dest"
  if gdalinfo "$dem" 2>/dev/null | grep -qi "LAYOUT=COG\|Cloud Optimized"; then
    cp "$dem" "$dest"
  else
    gdal_translate "$dem" "$dest" -of COG -co COMPRESS=DEFLATE -co RESAMPLING=NEAREST
  fi
  upload "$dest" "rasters/dem_india.tif"
else
  echo "⚠ DEM source not found"
fi

echo
echo "Done. Ensure backend/.env has:"
echo "  COG_LAYERS=rasters/lulc250k_2023_24_classed_cog.tif,rasters/dem_india.tif,rasters/jrc_occurrence_india_2024.tif,rasters/jrc_transition_india_2024.tif"
echo "  VECTOR_LAYERS=vector/aquifers.fgb,vector/gw_stress.fgb,vector/village_resilience.fgb,vector/villages.fgb"
echo "  WATERSHEDS_FGB_KEY=vector/india_basins_level_12.gpkg"
echo "Then recreate API: cd backend && docker compose up -d --build api"
