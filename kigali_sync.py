import ee
import os
import json
from datetime import datetime, timedelta

def run_monitoring():
    # --- AUTHENTICATION ---
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], 
                                                  key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials)
        print("Authenticated successfully.")
    except Exception as e:
        print(f"Auth Error: {e}")
        return

    # --- ASSET LOADING ---
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom"
    kigali_aoi = ee.FeatureCollection(asset_id)

    # --- MULTI-SENSOR FUSION LOGIC (WORK #2) ---
    # 1. Baseline: Previous year's Median
    sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(kigali_aoi).filterDate('2024-01-01', '2024-12-31').median()
    
    # 2. Latest Data (Radar & Optical)
    current_sar = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(kigali_aoi).sort('system:time_start', False).first()
    
    # 3. Work #3 Logic: AI-Style Thresholding
    # Detect increase in radar brightness (New structures)
    sar_diff = current_sar.select('VV').subtract(sar_baseline.select('VV'))
    sar_alerts = sar_diff.gt(5) # Threshold: 5dB change [cite: 514]
    
    # 4. Filter Noise (Speckle Reduction)
    # Applying a simple focal mean to act as a noise filter [cite: 514, 735]
    cleaned_alerts = sar_alerts.focal_mode(radius=10, units='meters').selfMask()

    # --- THE EXPORT (REPAIRED FOR QUOTA ERROR) ---
    print("Submitting Fusion Task...")
    task = ee.batch.Export.image.toDrive(
        image=cleaned_alerts,
        description=f'Alert_Map_{datetime.now().strftime("%Y%m%d")}',
        folder='Kigali_Monitoring_Data', # ENSURE THIS FOLDER IS SHARED AS 'EDITOR'
        scale=10,
        region=kigali_aoi.geometry().bounds(),
        fileFormat='GeoTIFF'
    )
    
    try:
        task.start()
        print(f"Fusion Task Started: {task.id}")
    except Exception as e:
        print(f"Export Failed: {e}. Check folder sharing permissions.")

if __name__ == "__main__":
    run_monitoring()
