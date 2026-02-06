import ee
import os
import json
from datetime import datetime, timedelta

def run_monitoring():
    # --- BLOCK 1: AUTHENTICATION (Keep this!) ---
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], 
                                                  key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials)
        print("Authenticated successfully.")
    except Exception as e:
        print(f"Auth Error: {e}")
        return

    # --- BLOCK 2: ASSET & DELTA CHECK ---
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom"
    kigali_aoi = ee.FeatureCollection(asset_id)
    
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # --- BLOCK 3: MULTI-SENSOR FUSION LOGIC ---
    end_date = datetime.now()
    start_date = end_date - timedelta(days=30) 
    
    # A. Get Latest Sentinel-2 (Optical)
    s2_col = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
              .filterBounds(kigali_aoi)
              .filterDate(start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
              .sort('system:time_start', False))
    
    latest_s2 = s2_col.first()
    
    if latest_s2.getInfo():
        current_id = latest_s2.id().getInfo()
        
        if current_id != last_id:
            print(f"Processing New Change Detection for: {current_id}")
            
            # 1. SAR Radar Baseline (Sentinel-1)
            sar_baseline = (ee.ImageCollection('COPERNICUS/S1_GRD')
                            .filterBounds(kigali_aoi)
                            .filterDate('2023-01-01', '2023-12-31')
                            .median())
            
            # 2. Current SAR Radar
            current_sar = (ee.ImageCollection('COPERNICUS/S1_GRD')
                           .filterBounds(kigali_aoi)
                           .sort('system:time_start', False)
                           .first())
            
            # 3. Detection: SAR Brightness Increase (New Buildings)
            sar_diff = current_sar.select('VV').subtract(sar_baseline.select('VV'))
            sar_alerts = sar_diff.gt(5) # Threshold for construction
            
            # 4. Detection: NDVI Loss (Land Clearing)
            ndvi_latest = latest_s2.normalizedDifference(['B8', 'B4'])
            # We simplify here: comparing current NDVI to a fixed 'Green' threshold
            ndvi_alerts = ndvi_latest.lt(0.3) 
            
            # 5. FUSION: Confirmed Construction in Wetlands/Agri
            # Only flag if both sensors agree (SAR Brightness UP + NDVI DOWN)
            confirmed_alerts = sar_alerts.And(ndvi_alerts).selfMask()

            # --- BLOCK 4: EXPORT THE RESULTS ---
            task = ee.batch.Export.image.toDrive(
                image=confirmed_alerts, # We export the 'Alert Map', not the raw photo
                description=f'Alert_Map_{datetime.now().strftime("%Y%m%d")}',
                folder='Kigali_Monitoring_Data',
                scale=10,
                region=kigali_aoi.geometry().bounds(),
                fileFormat='GeoTIFF'
            )
            task.start()
            
            with open(state_file, 'w') as f:
                f.write(current_id)
            print("Fusion Task Started. Check your Drive for the Alert Map.")
        else:
            print("No new imagery to analyze.")
    else:
        print("No images found.")

if __name__ == "__main__":
    run_monitoring()
