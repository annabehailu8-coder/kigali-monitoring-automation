import ee
import os
import json
from datetime import datetime, timedelta

def run_monitoring():
    # 1. Initialize Earth Engine
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], 
                                                  key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials)
        print("Successfully authenticated.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # 2. Define Area of Interest & Asset
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" # [cite: 851]
    kigali_aoi = ee.FeatureCollection(asset_id) # [cite: 463]

    # 3. Delta Check [cite: 465, 858]
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 4. Fetch Latest Imagery (Optical) [cite: 464, 853]
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30) 
    
    s2_collection = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
                     .filterBounds(kigali_aoi)
                     .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                     .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30)) # [cite: 473]
                     .sort('system:time_start', False))

    latest_image = s2_collection.first()
    img_info = latest_image.getInfo()
    
    if img_info:
        current_id = img_info['id']
        
        if current_id != last_id: # [cite: 865]
            print(f"NEW IMAGE FOUND: {current_id}")
            
            # --- UPDATED EXPORT WITH SHARED DRIVE LOGIC ---
            task = ee.batch.Export.image.toDrive(
                image=latest_image.select(['B4', 'B3', 'B2']), # [cite: 897]
                description='Kigali_Success_Test',
                folder='Kigali_Monitoring_Data', # MUST be shared with the service account email
                scale=10,
                region=kigali_aoi.geometry().bounds(), # Use bounds to avoid geometry complexity errors
                fileFormat='GeoTIFF'
            )
            
            task.start() # [cite: 897]
            print(f"TASK STARTED: Check GEE Tasks tab. Task ID: {task.id}")
            
            # Update Delta File [cite: 863, 881]
            with open(state_file, 'w') as f:
                f.write(current_id)
        else:
            print("No new images since last check.")
    else:
        print("No images found in date range.")

if __name__ == "__main__":
    run_monitoring()
