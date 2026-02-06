import ee
import os
import json
from datetime import datetime, timedelta

def run_monitoring():
    # 1. Auth
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], 
                                                  key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials)
    except Exception as e:
        print(f"Auth Error: {e}")
        return

    # 2. Asset & Delta Check
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom"
    kigali_aoi = ee.FeatureCollection(asset_id)
    
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 3. Filtering
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    latest_image = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
                    .filterBounds(kigali_aoi)
                    .filterDate(start_date, end_date)
                    .sort('system:time_start', False)
                    .first())

    # 4. Logical Export
    if latest_image.getInfo():
        current_id = latest_image.id().getInfo()
        
        if current_id != last_id:
            print(f"Exporting New Image: {current_id}")
            
            # Use 'description' without slashes to avoid file-system errors
            clean_name = f"Kigali_{datetime.now().strftime('%Y%m%d')}"
            
            task = ee.batch.Export.image.toDrive(
                image=latest_image.select(['B4', 'B3', 'B2']),
                description=clean_name,
                folder='Kigali_Monitoring_Data', # MUST EXIST IN YOUR DRIVE
                scale=10,
                region=kigali_aoi.geometry().bounds(),
                fileFormat='GeoTIFF'
            )
            task.start()
            
            with open(state_file, 'w') as f:
                f.write(current_id)
            print("Task submitted. Please check your Shared Folder in Drive.")
        else:
            print("Already processed this image.")
    else:
        print("No image found.")

if __name__ == "__main__":
    run_monitoring()
