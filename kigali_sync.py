import ee
import os
import json
import requests
from datetime import datetime, timedelta

def send_telegram_alert(score, task_name, alert_image, background_image, region):
    """
    Senior Fix: Ensures change detection pixels are RED and handles Telegram 
    migration to Supergroups.
    """
    token = os.environ.get('TELEGRAM_TOKEN')
    # Update your GitHub Secret with ID: -1003689205228
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ Telegram credentials missing in GitHub Secrets.")
        return

    try:
        img_date = ee.Date(background_image.get('system:time_start')).format('YYYY-MM-DD').getInfo()
        time_span = f"2024-01-01 to {img_date}"
    except:
        time_span = "Recent Detection"

    # 1. VISUALIZATION FIX: Background (Sentinel-2 RGB)
    bg_vis = background_image.visualize(bands=['B4', 'B3', 'B2'], min=0, max=3000)
    
    # 2. COLOR FIX: Create a 3-band RGB image for the mask.
    # We use a 0-1 range with a black-to-red palette, then mask the zeros.
    # This prevents GEE from defaulting '1' to grayscale/black during thumbnailing.
    fg_vis = alert_image.visualize(
        palette=['#000000', '#FF0000'], 
        min=0, 
        max=1
    ).updateMask(alert_image)
    
    # 3. BLEND: This overlays the guaranteed RED pixels onto the background
    combined_vis = bg_vis.blend(fg_vis)
    
    try:
        # TELEGRAM FIX: Append a dummy extension to help the bot recognize the file type
        thumb_url = combined_vis.getThumbURL({
            'region': region,
            'dimensions': 1024,
            'format': 'png'
        }) + "&extension=.png"
        
        caption = (
            f"🚨 *Kigali Construction Alert*\n"
            f"Activity Period: `{time_span}`\n"
            f"Detected Area (Pixels): `{score}`\n"
            f"GEE Task: `{task_name}`"
        )
        
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        payload = {
            'chat_id': chat_id, 
            'photo': thumb_url, 
            'caption': caption, 
            'parse_mode': 'Markdown'
        }
        
        response = requests.post(url, data=payload)
        
        if response.status_code == 200:
            print(f"📱 Telegram alert sent successfully for {time_span}.")
        else:
            # Catching the migration error found in logs
            print(f"❌ Telegram Error: {response.text}")
            if "migrate_to_chat_id" in response.text:
                print("💡 ACTION REQUIRED: Update your TELEGRAM_CHAT_ID secret with the new ID in the error above.")
        
    except Exception as e:
        print(f"Photo Alert Error: {e}")

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

    # 2. Load Boundary Asset
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" 
    try:
        kigali_aoi = ee.FeatureCollection(asset_id)
        region = kigali_aoi.geometry().bounds()
    except Exception as e:
        print(f"Asset Loading Error: {e}")
        return

    # 3. Delta Tracking (Last Processed Image)
    state_file = 'last_image_id.txt'
    last_id = ""
    if os.path.exists(state_file):
        with open(state_file, 'r') as f:
            last_id = f.read().strip()

    # 4. Sensor Logic: Sentinel-2 Cloud-Free Search
    now = datetime.now()
    s2_col = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
               .filterBounds(region) \
               .filterDate((now - timedelta(days=30)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')) \
               .sort('system:time_start', False)
    
    latest_img = s2_col.first()

    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        
        # Only process if we have a brand new image
        if current_id != last_id:
            print(f"New Image Found: {current_id}. Running Radar Change Detection...")

            # 5. Radar (S1) Analysis
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD') \
                             .filterBounds(region) \
                             .filterDate('2024-01-01', '2024-06-01').median()
            
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD') \
                            .filterBounds(region) \
                            .sort('system:time_start', False).first()
            
            # Detect 6dB+ backscatter increase
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)
            cleaned_alerts = sar_alerts.focal_mode(radius=1, kernelType='circle', iterations=1).selfMask()

            # Calculate Pixel Count
            stats = cleaned_alerts.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=region,
                scale=20,
                maxPixels=1e8
            )
            change_score = stats.get('VV').getInfo() or 0
            print(f"Change Score: {change_score}")

            # 6. Threshold & Execution
            if change_score > 5:
                task_timestamp = now.strftime('%Y%m%d_%H%M')
                task_name = f"Alert_Kigali_{task_timestamp}"
                
                # Send the Alert
                send_telegram_alert(change_score, task_name, cleaned_alerts, latest_img, region)

                # Start Export Task to Asset
                task = ee.batch.Export.image.toAsset(
                    image=cleaned_alerts.byte().clip(kigali_aoi),
                    description=task_name,
                    assetId=f"projects/kigali-sync-final/assets/{task_name}",
                    scale=20,
                    region=region,
                    maxPixels=1e9
                )
                task.start()
                print(f"SUCCESS: Export {task_name} started.")

            # Update State File
            with open(state_file, 'w') as f:
                f.write(current_id)
        else:
            print("No new satellite imagery. System idle.")
    else:
        print("No suitable Sentinel-2 imagery found in last 30 days.")

if __name__ == "__main__":
    run_monitoring()
