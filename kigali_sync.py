import ee
import os
import json
import base64
from datetime import datetime, timedelta

def run_alerting_system():
    try:
        # 1. Professional Auth Flow
        encoded_key = os.environ.get('GEE_JSON_KEY')
        gee_json_key = json.loads(base64.b64decode(encoded_key).decode('utf-8'))
        ee.Initialize(ee.ServiceAccountCredentials(gee_json_key['client_email'], 
                      key_data=json.dumps(gee_json_key)), project='dahanga')
        print("🛰️  System Online: Connected to Dahanga Project.")
    except Exception as e:
        print(f"❌ AUTH FAILURE: {e}"); return

    # 2. Define Area of Interest (AOI)
    aoi = ee.FeatureCollection("projects/dahanga/assets/Gahanga_Sector")
    region = aoi.geometry().bounds()

    # 3. Work #3 Logic: Radar Change Detection (Sentinel-1)
    # Compare "Last Week" to "Previous Month"
    now = datetime.now()
    recent_s1 = ee.ImageCollection("COPERNICUS/S1_GRD") \
        .filterBounds(region) \
        .filterDate((now - timedelta(days=14)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
        .select('VV').mean()

    baseline_s1 = ee.ImageCollection("COPERNICUS/S1_GRD") \
        .filterBounds(region) \
        .filterDate((now - timedelta(days=60)).strftime('%Y-%m-%d'), (now - timedelta(days=30)).strftime('%Y-%m-%d')) \
        .filter(ee.Filter.listContains('transmitterReceiverPolarisation', 'VV')) \
        .select('VV').mean()

    # Calculate Radar Ratio (Change)
    # Brightness increase usually means new structures/construction
    radar_change = recent_s1.divide(baseline_s1)
    
    # 4. Threshold Alerting
    # We only trigger a task if the max change is > 1.5 (50% increase in radar return)
    stats = radar_change.reduceRegion(reducer=ee.Reducer.max(), geometry=region, scale=30)
    change_val = stats.get('VV').getInfo()

    print(f"📊 Current Change Score for Gahanga: {change_val}")

    if change_val and change_val > 1.2:
        print("🚨 ALERT: Significant change detected! Triggering Export...")
        task_name = f"ALERT_Gahanga_{now.strftime('%Y%m%d')}"
        task = ee.batch.Export.image.toAsset(
            image=radar_change.visualize(min=0.8, max=2, palette=['white', 'yellow', 'red']),
            description=task_name,
            assetId=f"projects/dahanga/assets/{task_name}",
            region=region,
            scale=20, # Higher resolution for alerts
            maxPixels=1e8
        )
        task.start()
        print(f"✅ Export Task {task_name} started.")
    else:
        print("✅ Status Green: No significant construction detected today.")

if __name__ == "__main__":
    run_alerting_system()
