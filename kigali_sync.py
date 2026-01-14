import ee
import os
import json
import datetime

def initialize_gee():
    """Initializes Earth Engine using the Service Account key from GitHub Secrets."""
    try:
        key_json = os.environ.get('GEE_JSON_KEY')
        if not key_json:
            print("❌ Error: GEE_JSON_KEY environment variable is missing.")
            return False

        key_dict = json.loads(key_json)
        credentials = ee.ServiceAccountCredentials(key_dict['client_email'], key_data=key_json)
        
        ee.Initialize(credentials, project=key_dict['project_id'])
        print(f"✅ GEE Initialized successfully for project: {key_dict['project_id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize GEE: {e}")
        return False

def run_analysis():
    """Main logic for Kigali Monitoring using fused Sentinel-1 and Sentinel-2 data."""
    try:
        # 1. Define Region of Interest (ROI) from your Assets
        # REPLACE this with your actual Asset ID
        asset_id = 'projects/kigali-sync-final/assets/KIgali_City' 
        roi = ee.FeatureCollection(asset_id)
        roi_geometry = roi.geometry()

        # 2. Set Dynamic Date Range (Last 5 Days)
        now = datetime.datetime.now()
        start_date = (now - datetime.timedelta(days=5)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')
        print(f"📅 Monitoring Period: {start_date} to {end_date}")

        # 3. Sentinel-2 (Optical) Filtering
        s2_col = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(roi_geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

        s2_count = s2_col.size().getInfo()
        print(f"🛰️ Sentinel-2 images found: {s2_count}")

        # 4. Sentinel-1 (Radar) Filtering
        s1_col = ee.ImageCollection("COPERNICUS/S1_GRD") \
            .filterBounds(roi_geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.eq('instrumentMode', 'IW')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))

        s1_count = s1_col.size().getInfo()
        print(f"📡 Sentinel-1 images found: {s1_count}")

        # 5. Analysis Logic
        if s2_count > 0:
            # Create a cloud-free composite and calculate Urban Index (NDBI)
            composite = s2_col.median().clip(roi_geometry)
            ndbi = composite.normalizedDifference(['B11', 'B8']).rename('NDBI')
            
            # Calculate Area of pixels with NDBI > 0.1
            urban_mask = ndbi.gt(0.1)
            area_stats = urban_mask.multiply(ee.Image.pixelArea()).reduceRegion(
                reducer=ee.Reducer.sum(),
                geometry=roi_geometry,
                scale=10,
                maxPixels=1e9
            )
            
            urban_sqkm = area_stats.get('NDBI').getInfo() / 1_000_000
            print("-" * 30)
            print(f"KIGALI URBAN REPORT")
            print(f"Detected Urban Area: {urban_sqkm:.2f} sq km")
            print("-" * 30)
        else:
            print("⚠️ No clear Sentinel-2 images in the last 5 days. Try increasing the date range.")

        if s1_count > 0:
            print("✅ Sentinel-1 Radar data is available for cloud-penetrating analysis.")
            # Note: S1 processing (like Ratio VV/VH) can be added here for flood/structure detection

    except Exception as e:
        print(f"❌ Analysis failed: {e}")

if __name__ == "__main__":
    if initialize_gee():
        run_analysis()
    else:
        exit(1)
