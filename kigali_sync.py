import ee
import os
import json
import requests
from datetime import datetime, timedelta

def send_telegram_alert(score, task_name, region):
    """Sends a text-based alert with GEE App and Google Maps links."""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id:
        print("⚠️ Telegram credentials missing.")
        return

    try:
        # FIX: Added 'maxError=1' to prevent the geometry calculation crash
        center = region.centroid(maxError=1).getInfo()['coordinates']
        google_maps_link = f"https://www.google.com/maps/search/?api=1&query={center[1]},{center[0]}"
        
        # Replace this with your actual published GEE App URL
        gee_app_link = "https://kigali-sync-final.projects.earthengine.app/view/kigali-monitor"

        caption = (
            f"🚨 *Kigali Construction Alert*\n"
            f"🏗️ *Change Score:* `{score}` pixels\n"
            f"📅 *Baseline:* Jan 2025 Start\n\n"
            f"🌐 [Open Dashboard App]({gee_app_link})\n"
            f"📍 [View Location on Google Maps]({google_maps_link})"
        )
        
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={'chat_id': chat_id, 'text': caption, 'parse_mode': 'Markdown'})
        print("📱 Telegram notification sent.")
    except Exception as e: 
        print(f"Alert Dispatch Error: {e}")

def run_monitoring():
    # 1. Authentication
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials, project='kigali-sync-final')
    except Exception as e:
        print(f"Auth Error: {e}"); return

    # 2. Assets
    kigali_aoi = ee.FeatureCollection("projects/kigali-sync-final/assets/kigali_boundary_custom")
    region = kigali_aoi.geometry().bounds()

    # 3. Delta Tracking
    state_file = 'last_image_id.txt'
    last_id = open(state_file, 'r').read().strip() if os.path.exists(state_file) else ""

    now = datetime.now()
    latest_img = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
                   .filterBounds(region) \
                   .sort('system:time_start', False).first()

    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        
        # To force a run if you aren't getting alerts, empty 'last_image_id.txt'
        if current_id != last_id:
            print(f"New Image Found: {current_id}. Analyzing...")

            # --- 2025 BASELINE LOGIC ---
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD') \
                             .filterBounds(region) \
                             .filterDate('2025-01-01', '2025-06-01').median()
            
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD') \
                            .filterBounds(region) \
                            .sort('system:time_start', False).first()
            
            # Identify 6dB+ increases
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)
            cleaned_alerts = sar_alerts.focal_mode(radius=1, kernelType='circle', iterations=1).selfMask()

            # Calculate change score
            stats = cleaned_alerts.reduceRegion(reducer=ee.Reducer.count(), geometry=region, scale=20)
            change_score = stats.get('VV').getInfo() or 0

            if change_score > 5:
                task_name = f"Alert_Kigali_2025_{now.strftime('%Y%m%d_%H%M')}"
                send_telegram_alert(change_score, task_name, region)

                # Export the "Latest" asset for the App automation
                ee.batch.Export.image.toAsset(
                    image=cleaned_alerts.byte().clip(kigali_aoi),
                    description="App_Asset_Update",
                    assetId="projects/kigali-sync-final/assets/Kigali_Latest_Alert",
                    scale=20, region=region
                ).start()
                print(f"SUCCESS: Export for {task_name} started.")

            with open(state_file, 'w') as f:
                f.write(current_id)
        else:
            print("System Idle: No new imagery.")
    else:
        print("Search Result: No imagery found.")

if __name__ == "__main__":
    run_monitoring()
