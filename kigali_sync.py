import ee
import os
import json
import datetime

# --- CONFIGURATION ---
# Replace with your actual Asset ID from GEE
ASSET_ID = 'projects/kigali-sync-final/assets/KIgali_City'
STATE_FILE = "last_image_id.txt"

def initialize_gee():
    """Initializes Earth Engine using the Service Account key."""
    try:
        key_json = os.environ.get('GEE_JSON_KEY')
        if not key_json:
            print("❌ Error: GEE_JSON_KEY missing in environment.")
            return False

        key_dict = json.loads(key_json)
        credentials = ee.ServiceAccountCredentials(
            key_dict['client_email'], 
            key_data=key_json
        )
        
        ee.Initialize(credentials, project=key_dict['project_id'])
        print(f"✅ GEE Initialized: {key_dict['project_id']}")
        return True
    except Exception as e:
        print(f"❌ Initialization failed: {e}")
        return False

def get_last_processed_id():
    """Reads the last processed Image ID from a local file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return f.read().strip()
    return None

def save_latest_id(image_id):
    """Saves the current Image ID to a local file."""
    with open(STATE_FILE, "w") as f:
        f.write(image_id)

def run_analysis():
    """Main logic: Check for new imagery, filter S1/S2, and export if new."""
    try:
        # 1. Define ROI
        roi = ee.FeatureCollection(ASSET_ID)
        roi_geometry = roi.geometry()

        # 2. Find the LATEST available Sentinel-2 image
        s2_collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
            .filterBounds(roi_geometry) \
            .sort('system:time_start', False) # Newest first

        latest_image = s2_collection.first()
        
        if latest_image is None:
            print("⚠️ No images found in GEE for this ROI.")
            return

        latest_id = latest_image.id().getInfo()
        print(f"🔍 Latest image in GEE: {latest_id}")

        # 3. SYNC LOGIC: Compare IDs
        last_id = get_last_processed_id()
        if latest_id == last_id:
            print("✅ No new imagery since last run. Skipping to save quota.")
            return
        
        print("🚀 New imagery detected! Starting processing...")

        # 4. Filter Logic (Sentinel-2 Optical)
        # We check the last 5 days specifically for the composite
        now = datetime.datetime.now()
        start_date = (now - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = now.strftime('%Y-%m-%d')

        s2_filtered = s2_collection.filterDate(start_date, end_date) \
            .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

        # 5. Filter Logic (Sentinel-1 Radar)
        s1_filtered = ee.ImageCollection("COPERNICUS/S1_GRD") \
            .filterBounds(roi_geometry) \
            .filterDate(start_date, end_date) \
            .filter(ee.Filter.eq('instrumentMode', 'IW')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
            .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VH'))

        # 6. Analysis: Urban Detection (NDBI)
        composite = s2_filtered.median().clip(roi_geometry)
        # Simple NDBI: (SWIR1 - NIR) / (SWIR1 + NIR)
        ndbi = composite.normalizedDifference(['B11', 'B8']).rename('NDBI')
        
        # Calculate Urban Area
        urban_mask = ndbi.gt(0.1)
        area_stats = urban_mask.multiply(ee.Image.pixelArea()).reduceRegion(
            reducer=ee.Reducer.sum(),
            geometry=roi_geometry,
            scale=10,
            maxPixels=1e9
        )
        
        urban_sqkm = area_stats.get('NDBI').getInfo() / 1_000_000
        print(f"📊 Analysis Complete. Detected Urban Area: {urban_sqkm:.2f} sq km")

        # 7. TRIGGER EXPORT (Optional)
        # Only starts if processing was successful
        task = ee.batch.Export.image.toDrive(
            image=composite.select(['B4', 'B3', 'B2']),
            description=f"Kigali_Update_{datetime.datetime.now().strftime('%Y%m%d')}",
            folder='Kigali_Monitoring',
            region=roi_geometry,
            scale=10
        )
        task.start()
        print(f"📤 Export task started: {task.id}")

        # 8. UPDATE STATE: Save the ID so we don't run again for this image
        save_latest_id(latest_id)
        print("💾 State updated in last_image_id.txt")

    except Exception as e:
        print(f"❌ Analysis failed: {e}")

if __name__ == "__main__":
    if initialize_gee():
        run_analysis()
    else:
        exit(1)
