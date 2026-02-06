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
        print("Successfully authenticated with Earth Engine.")
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # 2. Define Area of Interest (Kigali)
    # Ensure this matches your GEE Asset ID exactly
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" 
    
    try:
        kigali_aoi = ee.FeatureCollection(asset_id)
        # Test connection
        _ = kigali_aoi.size().getInfo()
        print(f"Asset verified: {asset_id}")
    except Exception as e:
        print(f"ERROR: Access denied to asset '{asset_id}'. Check Sharing settings.")
        return

    # 3. Delta Check: Read last processed ID
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 4. Define Date Range 
    # Using 30 days to ensure we find an image for this test
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30) 

    # 5. Fetch Latest Sentinel-2 (Optical)
    try:
        s2_collection = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
                         .filterBounds(kigali_aoi)
                         .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                         # Set to 100% for the test to ensure we find an image even if cloudy
                         .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 30))
                         .sort('system:time_start', False))

        latest_image = s2_collection.first()
        
        # Check if an image actually exists in the result
        img_info = latest_image.getInfo()
        
        if img_info:
            current_id = img_info['id']
            
            # 6. Logical Trigger: Is this a new image?
            if current_id != last_id:
                print(f"NEW IMAGE FOUND: {current_id}")
                
                # --- ADDING THE EXPORT TASK ---
                # This is what makes the entry appear in the GEE Tasks Tab
                task = ee.batch.Export.image.toDrive(
                    image=latest_image.select(['B4', 'B3', 'B2']), # Exporting Red, Green, Blue
                    description=f'Kigali_Monitor_Run',
                    folder='Kigali_Monitoring_Data',
                    scale=10, # 10-meter resolution
                    region=kigali_aoi.geometry(),
                    fileFormat='GeoTIFF'
                )
                
                task.start() # This sends the command to Google's servers
                print(f"TASK STARTED: Check GEE Tasks tab for Task ID: {task.id}")
                
                # 7. Update Delta File
                with open(state_file, 'w') as f:
                    f.write(current_id)
                print("Updated last_image_id.txt to prevent duplicate exports.")
            
            else:
                print("Status: No new imagery since the last run. (Delta Check active)")
        else:
            print("Status: No images found in the specified date/cloud range.")
            
    except Exception as e:
        print(f"Processing Error: {e}")

if __name__ == "__main__":
    run_monitoring()
