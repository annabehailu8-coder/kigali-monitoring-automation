import ee
import os
import json
import datetime

def initialize_gee():
    """Initializes Earth Engine using the Service Account key."""
    try:
        key_json = os.environ.get('GEE_JSON_KEY')
        if not key_json:
            print("❌ Error: GEE_JSON_KEY missing.")
            return False

        key_dict = json.loads(key_json)
        # Exactly 8 spaces before 'credentials'
        credentials = ee.ServiceAccountCredentials(key_dict['client_email'], key_data=key_json)
        
        ee.Initialize(credentials, project=key_dict['project_id'])
        print(f"✅ GEE Initialized. Project: {key_dict['project_id']}")
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False

def run_analysis():
    """Main logic using a CUSTOM SHAPEFILE."""
    try:
        # 1. Define ROI - Replace with your actual Asset ID
        asset_id = 'projects/kigali-sync-final/assets/KIgali_City' 
        kigali_roi = ee.FeatureCollection(asset_id)
        roi_geometry = kigali_roi.geometry()
        print(f"✅ Loaded custom shapefile: {asset_id}")

        # 2. Set Dates
        end_date = datetime.datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime('%Y-%m-%d')

        # 3. Process Imagery
        s2 = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(roi_geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15))

        composite = s2.median().clip(roi_geometry)

        # 4. Urban Detection (NDBI)
        ndbi = composite.normalizedDifference(['B11', 'B8']).rename('NDBI')
        urban_pixels = ndbi.gt(0.1)

        # 5. Area Calculation
        area_image = urban_pixels.multiply(ee.Image.pixelArea())
        area_stats = area_image.reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi_geometry,
            scale=10,
            maxPixels=1e9
        )

        urban_val = area_stats.get('NDBI').getInfo()
        if urban_val:
            print(f"Detected Urban Area: {urban_val / 1_000_000:.2f} sq km")
        else:
            print("⚠️ No urban pixels detected.")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")

if __name__ == "__main__":
    if initialize_gee():
        run_analysis()
    else:
        exit(1)
