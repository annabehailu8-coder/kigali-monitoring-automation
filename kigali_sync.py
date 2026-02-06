import ee
import os
import json
from datetime import datetime, timedelta

def run_monitoring():
    # 1. Auth with Error Handling
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], 
                                                  key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials)
        print("Authenticated successfully.")
    except Exception as e:
        print(f"Auth Error: {e}")
        return

    # 2. Setup Assets
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom"
    kigali_aoi = ee.FeatureCollection(asset_id)
    
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 3. Detection Logic (Work #2)
    now = datetime.now()
    s2_col = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
              .filterBounds(kigali_aoi)
              .filterDate((now - timedelta(days=30)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d'))
              .sort('system:time_start', False))
    
    latest_img = s2_col.first()
    
    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        
        if current_id != last_id:
            print(f"New Image Detected: {current_id}. Running Fusion...")
            
            # SAR Radar Check
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(kigali_aoi).filterDate('2024-01-01', '2024-12-31').median()
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(kigali_aoi).sort('system:time_start', False).first()
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(5)
            
            # NDVI Optical Check
            ndvi = latest_img.normalizedDifference(['B8', 'B4'])
            ndvi_alerts = ndvi.lt(0.3)
            
            # Fused Result
            final_alerts = sar_alerts.And(ndvi_alerts).selfMask()

            # --- EXPORT TO ASSET (Bypasses Drive Quota Error) ---
            # Using 'toAsset' ensures the file is saved within GEE itself
            task_name = f"Alert_{now.strftime('%Y%m%d_%H%M')}"
            asset_path = f"projects/kigali-sync-final/assets/{task_name}"
            
            task = ee.batch.Export.image.toAsset(
                image=final_alerts,
                description=task_name,
                assetId=asset_path,
                scale=10,
                region=kigali_aoi.geometry().bounds()
            )
            task.start()
            print(f"Task Started! View it in GEE Assets: {asset_path}")

            # 4. Update the Delta File
            with open(state_file, 'w') as f:
                f.write(current_id)
            print("Successfully updated last_image_id.txt locally.")
        else:
            print("No new imagery found since last update.")
    else:
        print("Failed to find any imagery for the current period.")

if __name__ == "__main__":
    run_monitoring()
