import ee
import os
import json
import requests
from datetime import datetime, timedelta

import requests
import os
import ee

def send_telegram_alert(score, task_name, alert_image, background_image, region):
    """Sends a photo notification with guaranteed red pixels and delivery fixes."""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ Telegram credentials missing.")
        return

    # 1. VISUALIZATION FIX (The "Red" Issue)
    # Background: Sentinel-2 RGB
    bg_vis = background_image.visualize(bands=['B4', 'B3', 'B2'], min=0, max=3000)
    
    # Alerts: Create a solid red mask (FF0000)
    # We use .selfMask() to ensure only the '1' pixels are drawn
    fg_vis = alert_image.selfMask().visualize(palette=['#FF0000'], min=1, max=1)
    
    # Blend them together
    combined_vis = bg_vis.blend(fg_vis)
    
    try:
        # 2. TELEGRAM URL FIX
        # We append a dummy parameter '&extension=.png' to trick Telegram's parser
        thumb_url = combined_vis.getThumbURL({
            'region': region,
            'dimensions': 1024,
            'format': 'png'
        }) + "&extension=.png" 
        
        caption = (
            f"🚨 *Construction Alert: Kigali*\n"
            f"Significant change detected!\n"
            f"Pixel Count: `{score}`\n"
            f"Task: `{task_name}`"
        )
        
        # 3. ROBUST SENDING
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {
            'chat_id': chat_id, 
            'photo': thumb_url, 
            'caption': caption, 
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, data=payload)
        
        if response.status_code != 200:
            print(f"❌ Telegram Failed: {response.status_code} - {response.text}")
        else:
            print("✅ Telegram notification sent successfully!")
            
    except Exception as e:
        print(f"⚠️ Script Error: {e}")

def run_monitoring():
    # 1. Authentication
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(
            gee_json_key['client_email'], 
            key_data=os.environ['GEE_JSON_KEY']
        )
        ee.Initialize(credentials, project='kigali-sync-final')
        print("GEE Authenticated successfully.")
    except Exception as e:
        print(f"Auth Error: {e}")
        return

    # 2. Assets
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" 
    
    try:
        kigali_aoi = ee.FeatureCollection(asset_id)
        region = kigali_aoi.geometry().bounds()
    except Exception as e:
        print(f"Asset Loading Error: {e}")
        return

    # 3. Delta Tracking
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 4. Multi-Sensor Intelligence Logic
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

            # Radar (S1) Analysis
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD') \
                             .filterBounds(region) \
                             .filterDate('2024-01-01', '2024-06-01').median()
            
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
            print(f"Change Score (Pixel Count): {change_score}")

            # 5. Threshold Trigger
            if change_score > 5:
                task_timestamp = now.strftime('%Y%m%d_%H%M')
                task_name = f"Alert_Kigali_{task_timestamp}"
                
                # NO CHANGES TO THIS CALL: Matches your successful script exactly
                send_telegram_alert(change_score, task_name, cleaned_alerts, latest_img, region)

                # Export Task
                task = ee.batch.Export.image.toAsset(
                    image=cleaned_alerts.byte().clip(kigali_aoi),
                    description=task_name,
                    assetId=f"projects/kigali-sync-final/assets/{task_name}",
                    scale=20,
                    region=region,
                    maxPixels=1e9
                )
                task.start()
                print(f"SUCCESS: Task {task_name} started (BLUE).")

            # 6. Update GitHub Delta
            with open(state_file, 'w') as f:
                f.write(current_id)
        else:
            print("No new imagery detected. System idle.")
    else:
        print("Cloud Search: No clear images found in the last 30 days.")

if __name__ == "__main__":
    run_monitoring()
