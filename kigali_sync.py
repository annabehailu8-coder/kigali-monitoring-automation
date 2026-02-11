import ee
import os
import json
import requests
from datetime import datetime, timedelta

def send_telegram_alert(score, task_name, alert_image, background_image, region):
    """Sends a text-based alert with a direct GEE link for reliability."""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ Telegram credentials missing.")
        return

    # 1. Generate the GEE Link (More reliable than photos for high pixel counts)
    # This creates a viewable link for the GEE explorer
    gee_link = f"https://code.earthengine.google.com/?asset=projects/kigali-sync-final/assets/{task_name}"

    try:
        # 2. Prepare the Telegram message
        # Baseline is fixed to your requested period
        caption = (
            f"🚨 *Kigali Construction Alert*\n"
            f"Significant change detected!\n"
            f"📅 *Baseline:* 2024-01-01 to 2025-06-01\n"
            f"🏗️ *Change Score:* `{score}` pixels\n\n"
            f"🔗 [View Map in Google Earth Engine]({gee_link})"
        )
        
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id, 
            'text': caption, 
            'parse_mode': 'Markdown',
            'disable_web_page_preview': False
        }
        
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print(f"📱 Telegram alert sent with GEE link.")
        else:
            print(f"❌ Telegram Error: {response.text}")
            
    except Exception as e:
        print(f"Alert Error: {e}")

def run_monitoring():
    # 1. Authentication
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(
            gee_json_key['client_email'], 
            key_data=os.environ['GEE_JSON_KEY']
        )
        ee.Initialize(credentials, project='kigali-sync-final')
    except Exception as e:
        print(f"Auth Error: {e}"); return

    # 2. Assets
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" 
    kigali_aoi = ee.FeatureCollection(asset_id)
    region = kigali_aoi.geometry().bounds()

    # 3. Delta Tracking
    state_file = 'last_image_id.txt'
    last_id = open(state_file, 'r').read().strip() if os.path.exists(state_file) else ""

    # 4. Satellite Search
    now = datetime.now()
    s2_col = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
               .filterBounds(region) \
               .filterDate((now - timedelta(days=30)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')) \
               .sort('system:time_start', False)
    
    latest_img = s2_col.first()

    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        
        if current_id != last_id:
            print(f"New Image Found: {current_id}. Processing Radar Fusion...")

            # --- UPDATED BASELINE PER REQUEST ---
            # Baseline: Jan 2024 to June 2025
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD') \
                             .filterBounds(region) \
                             .filterDate('2024-01-01', '2025-06-01').median()
            
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD') \
                            .filterBounds(region) \
                            .sort('system:time_start', False).first()
            
            # Identify 6dB+ increases
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)
            cleaned_alerts = sar_alerts.focal_mode(radius=1, kernelType='circle', iterations=1).selfMask()

            # Calculate Change Score
            stats = cleaned_alerts.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=region,
                scale=20,
                maxPixels=1e8
            )
            change_score = stats.get('VV').getInfo() or 0
            print(f"Change Score: {change_score}")

            # 5. Threshold Trigger
            if change_score > 5:
                task_name = f"Alert_Kigali_{now.strftime('%Y%m%d_%H%M')}"
                
                # SENDS TEXT ALERT WITH GEE LINK
                send_telegram_alert(change_score, task_name, cleaned_alerts, latest_img, region)

                # Export Task
                ee.batch.Export.image.toAsset(
                    image=cleaned_alerts.byte().clip(kigali_aoi),
                    description=task_name,
                    assetId=f"projects/kigali-sync-final/assets/{task_name}",
                    scale=20,
                    region=region,
                    maxPixels=1e9
                ).start()
                print(f"SUCCESS: Export {task_name} started.")

            with open(state_file, 'w') as f:
                f.write(current_id)
        else:
            print("No new imagery detected.")
    else:
        print("No clear images found in the last 30 days.")

if __name__ == "__main__":
    run_monitoring()
