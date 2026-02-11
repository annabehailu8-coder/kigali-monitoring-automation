import ee
import os
import json
import requests
from datetime import datetime, timedelta

def send_telegram_alert(score, task_name, region):
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    if not token or not chat_id: return

    try:
        center = region.centroid().getInfo()['coordinates']
        google_maps_link = f"https://www.google.com/maps/search/?api=1&query={center[1]},{center[0]}"
        gee_app_link = "YOUR_GEE_APP_URL_HERE" # You will get this in Part 2

        caption = (
            f"🚨 *Kigali Construction Alert*\n"
            f"🏗️ *Change Score:* `{score}` pixels\n"
            f"📅 *Baseline:* Jan 2025 Start\n\n"
            f"🌐 [Open Dashboard App]({gee_app_link})\n"
            f"📍 [View on Google Maps]({google_maps_link})"
        )
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={'chat_id': chat_id, 'text': caption, 'parse_mode': 'Markdown'})
    except Exception as e: print(f"Alert Error: {e}")

def run_monitoring():
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(gee_json_key['client_email'], key_data=os.environ['GEE_JSON_KEY'])
        ee.Initialize(credentials, project='kigali-sync-final')
    except Exception as e: print(f"Auth Error: {e}"); return

    # Assets
    kigali_aoi = ee.FeatureCollection("projects/kigali-sync-final/assets/kigali_boundary_custom")
    region = kigali_aoi.geometry().bounds()

    # Delta Tracking
    state_file = 'last_image_id.txt'
    last_id = open(state_file, 'r').read().strip() if os.path.exists(state_file) else ""

    now = datetime.now()
    latest_img = ee.ImageCollection("COPERNICUS/S2_HARMONIZED").filterBounds(region).sort('system:time_start', False).first()

    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        if current_id != last_id:
            # 2025 Baseline Analysis
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(region).filterDate('2025-01-01', '2025-06-01').median()
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(region).sort('system:time_start', False).first()
            
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)
            cleaned_alerts = sar_alerts.focal_mode(radius=1, kernelType='circle', iterations=1).selfMask()

            change_score = cleaned_alerts.reduceRegion(reducer=ee.Reducer.count(), geometry=region, scale=20).get('VV').getInfo() or 0

            if change_score > 5:
                task_name = f"Alert_Kigali_2025_{now.strftime('%Y%m%d_%H%M')}"
                send_telegram_alert(change_score, task_name, region)

                # AUTOMATION FIX: Overwrite the "Latest" asset for the App
                ee.batch.Export.image.toAsset(
                    image=cleaned_alerts.byte().clip(kigali_aoi),
                    description="Update_App_Asset",
                    assetId="projects/kigali-sync-final/assets/Kigali_Latest_Alert",
                    scale=20, region=region
                ).start()

            with open(state_file, 'w') as f: f.write(current_id)

if __name__ == "__main__":
    run_monitoring()
