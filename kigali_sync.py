import ee
import os
import json
from datetime import datetime, timedelta

def run_monitoring():
    # 1. Authentication
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(
            gee_json_key['client_email'], 
            key_data=os.environ['GEE_JSON_KEY']
        )
        ee.Initialize(credentials)
        print("GEE Authenticated successfully.")
    except Exception as e:
        print(f"Auth Error: {e}")
        return

    # 2. Assets - REPLACE THE ID BELOW WITH YOUR NEW SMALL SHAPEFILE ID
    # Example: "projects/kigali-sync-final/assets/Kigali_Small_Zone"
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" 
    
    try:
        kigali_aoi = ee.FeatureCollection(asset_id)
        region = kigali_aoi.geometry().bounds()
    except Exception as e:
        print(f"Asset Loading Error: {e}")
        return

    # 3. Delta Tracking (The 'Brain')
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 4. Multi-Sensor Intelligence Logic
    now = datetime.now()
    # Get latest Sentinel-2 (Optical)
    s2_col = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
               .filterBounds(region) \
               .filterDate((now - timedelta(days=30)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')) \
               .sort('system:time_start', False)
    
    latest_img = s2_col.first()

    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        
        if current_id != last_id:
            print(f"New Image Found: {current_id}. Processing Alert...")

            # --- Work #2: Radar (S1) + Optical (S2) Fusion ---
            # SAR Baseline (Radar) - Brighter means more concrete/buildings
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD') \
                             .filterBounds(region) \
                             .filterDate('2024-01-01', '2024-06-01').median()
            
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD') \
                            .filterBounds(region) \
                            .sort('system:time_start', False).first()
            
            # Identify 6dB+ increases in radar (Strong indication of new construction)
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)

            # --- Work #3: Intelligence Filter ---
            # Remove isolated pixels (Salt and Pepper noise)
            cleaned_alerts = sar_alerts.focal_mode(radius=1, kernelType='circle', iterations=1).selfMask()

            # 5. Internal Asset Export (The 'Fast' Way)
            task_timestamp = now.strftime('%Y%m%d_%H%M')
            task_name = f"Alert_Kigali_{task_timestamp}"
            
            task = ee.batch.Export.image.toAsset(
                image=cleaned_alerts.byte().clip(kigali_aoi),
                description=task_name,
                assetId=f"projects/kigali-sync-final/assets/{task_name}",
                scale=20, # 20m is the 'sweet spot' for speed and accuracy
                region=region,
                maxPixels=1e9
            )
            task.start()
            print(f"SUCCESS: Task {task_name} is now BLUE in GEE. Wait ~5 mins.")

            # 6. Update GitHub Delta
            with open(state_file, 'w') as f:
                f.write(current_id)
        else:
            print("No new imagery detected. System idle.")
    else:
        print("Cloud Search: No clear images found in the last 30 days.")

if __name__ == "__main__":
    run_monitoring()
