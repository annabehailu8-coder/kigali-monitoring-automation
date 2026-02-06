import ee
import os
import json
from datetime import datetime, timedelta

def run_monitoring():
    # 1. Initialize Earth Engine with Service Account
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], 
                                                  key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials)
        print("Successfully authenticated with Earth Engine.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # 2. Define Area of Interest (Kigali) 
    # Ensure this Asset ID matches your 'Step 8' upload [cite: 401]
    kigali_aoi = ee.FeatureCollection("projects/kigali-sync-final/assets/kigali_boundary_custom")

    # 3. Delta Check: Read last processed ID [cite: 413]
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 4. Define Date Range (Using Python datetime for stability) [cite: 14, 439]
    # Set to 30 days for the first run to ensure data is found; change to 5 later.
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30) 

    # 5. Fetch Latest Sentinel-2 (Optical) [cite: 405]
    s2_collection = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
                     .filterBounds(kigali_aoi)
                     .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                     .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20)) # Filter out very cloudy images [cite: 23]
                     .sort('system:time_start', False))

    latest_image = s2_collection.first()

    # 6. Logical Trigger & Delta Comparison [cite: 415]
    if latest_image.getInfo():
        current_id = latest_image.id().getInfo()
        
        if current_id != last_id:
            print(f"NEW IMAGE DETECTED: {current_id}")
            
            # --- START PROCESSING AREA ---
            # Future Phase Logic: Cloud Masking & Radar Fusion will be inserted here [cite: 53, 56]
            # For now, we simulate a successful ingestion/export [cite: 447]
            # --- END PROCESSING AREA ---
            
            # Update the Delta file so we don't process this image again [cite: 431]
            with open(state_file, 'w') as f:
                f.write(current_id)
            print("Successfully updated last_image_id.txt.")
        else:
            print("No new imagery found since last successful run.")
    else:
        print("No suitable images found in this date range. Check cloud cover settings.")

if __name__ == "__main__":
    run_monitoring()
