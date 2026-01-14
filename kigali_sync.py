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
        service_account = key_dict.get('client_email')
        
        if not service_account:
            print("❌ ERROR: Could not find 'client_email' in the JSON key.")
            return False
            
        credentials = ee.ServiceAccountCredentials(key_dict['client_email'], key_data=key_json)
        
        # Initialize with your Project ID
        project_id = 'kigali-sync-final' 
        ee.Initialize(credentials, project=project_id)
        
        print(f"✅ Successfully initialized GEE with project: {project_id}")
        return True

    except Exception as e:
        print(f"❌ Failed to initialize Earth Engine: {e}")
        return False

def main():
    if initialize_gee():"""Main logic using a CUSTOM SHAPEFILE."""
    
    # 1. DEFINE CUSTOM ROI FROM ASSETS
    # REPLACE the string below with your actual Asset ID from the Assets tab
    asset_id = 'projects/kigali-sync-final/assets/KIgali_City' 
    
    try:
        kigali_roi = ee.FeatureCollection(asset_id)
        roi_geometry = kigali_roi.geometry()
        print(f"✅ Loaded custom shapefile: {asset_id}")
    except Exception as e:
        print(f"❌ Could not load shapefile. Did you share it with the Service Account? Error: {e}")
        return

    # 2. Set Date Range (Last 6 months)
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime('%Y-%m-%d')

    # 3. Load and Filter Sentinel-2 Imagery
    s2_collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(roi_geometry) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 15)) # Stricter cloud filter

    # Create a cloud-free median composite
    composite = s2_collection.median().clip(roi_geometry)

    # 4. Urban Detection (NDBI Index)
    # Built-up index: (SWIR - NIR) / (SWIR + NIR)
    ndbi = composite.normalizedDifference(['B11', 'B8']).rename('NDBI')
    urban_threshold = 0.1
    urban_pixels = ndbi.gt(urban_threshold)

    # 5. Calculate Area
    area_image = urban_pixels.multiply(ee.Image.pixelArea())
    area_stats = area_image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi_geometry,
        scale=10,
        maxPixels=1e9
    )

    # Get results
    urban_area_val = area_stats.get('NDBI').getInfo()
    if urban_area_val:
        urban_area_sqkm = urban_area_val / 1_000_000
        print("-" * 30)
        print(f"CUSTOM ROI MONITORING REPORT")
        print(f"Detected Urban Area: {urban_area_sqkm:.2f} sq km")
        print("-" * 30)
    else:
        print("⚠️ No urban pixels detected in this ROI.")

if __name__ == "__main__":
    if initialize_gee():
        run_analysis()
    else:
        exit(1)
