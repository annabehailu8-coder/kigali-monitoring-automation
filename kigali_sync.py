import ee
import os
import json
import requests
from datetime import datetime, timedelta

def send_telegram_alert(score, task_name, alert_image, background_image, region):
    """Sends a photo notification with vibrant RED pixels and a dynamic Time Span."""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ Telegram credentials missing in GitHub Secrets.")
        return

    # 1. DYNAMIC TIME SPAN CALCULATION
    try:
        # Get the date of the satellite background image
        img_date = ee.Date(background_image.get('system:time_start')).format('YYYY-MM-DD').getInfo()
        # Since we use a sliding window, the span is roughly the last 6-12 days
        time_span = f"Detection Period: Last 6-12 days (ending {img_date})"
    except:
        time_span = "Recent Activity"

    # 2. CREATE THE VISUAL (RED ON SATELLITE)
    # Background: Brightened Sentinel-2
    bg_vis = background_image.visualize(bands=['B4', 'B3', 'B2'], min=0, max=4000)
    
    # Foreground: Bright RED (#FF0000). selfMask() removes the black background.
    fg_vis = alert_image.selfMask().visualize(palette=['#FF0000'], min=1, max=1)
    
    # Overlay the red pixels on top of the satellite map
    combined_vis = bg_vis.blend(fg_vis)
    
    try:
        thumb_url = combined_vis.getThumbURL({
            'region': region,
            'dimensions': 1000,
            'format': 'png'
        })
        
        caption = (
            f"🚨 *Kigali Construction Alert*\n"
            f"📅 `{time_span}`\n"
            f"🏗️ New Changes: `{score}` pixels\n"
            f"📂 Asset: `{task_name}`"
        )
        
        url = f"https://api.telegram.org/bot{token}/sendPhoto"
        requests.post(url, data={
            'chat_id': chat_id, 
            'photo': thumb_url, 
            'caption': caption, 
            'parse_mode': 'Markdown'
        })
        print(f"📱 Red Pixel alert sent for {img_date}.")
        
    except Exception as e:
        print(f"Photo Error: {e}")
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      data={'chat_id': chat_id, 'text': f"🚨 Alert: {score} new pixels detected.", 'parse_mode': 'Markdown'})

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

    # 2. Area of Interest
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" 
    try:
        kigali_aoi = ee.FeatureCollection(asset_id)
        region = kigali_aoi.geometry().bounds()
    except Exception as e:
        print(f"Asset Loading Error: {e}")
        return

    # 3. Delta Tracking (To avoid processing the same image twice)
    state_file = 'last_image_id.txt'
    last_id = open(state_file, 'r').read().strip() if os.path.exists(state_file) else ""

    # 4. Satellite Imagery Search
    now = datetime.now()
    s2_col = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
               .filterBounds(region) \
               .filterDate((now - timedelta(days=30)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')) \
               .sort('system:time_start', False)
    
    latest_img = s2_col.first()

    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        
        if current_id != last_id:
            print(f"New Image Found: {current_id}. Analyzing changes...")

            # --- SLIDING WINDOW RADAR ANALYSIS ---
            # Instead of 2024, we get the two most recent radar passes
            sar_col = ee.ImageCollection('COPERNICUS/S1_GRD') \
                        .filterBounds(region) \
                        .sort('system:time_start', False)
            
            # current_sar is the most recent (T)
            current_sar = ee.Image(sar_col.toList(2).get(0))
            # sar_baseline is the one before it (T-1)
            sar_baseline = ee.Image(sar_col.toList(2).get(1))
            
            # Detect pixels that got 6dB brighter since the LAST pass
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)
            cleaned_alerts = sar_alerts.focal_mode(radius=1, kernelType='circle', iterations=1).selfMask()

            # 5. Score Calculation
            stats = cleaned_alerts.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=region,
                scale=20,
                maxPixels=1e8
            )
            change_score = stats.get('VV').getInfo() or 0
            print(f"New Change Score: {change_score}")

            # 6. Notification & Export
            if change_score > 5:
                task_name = f"Alert_Kigali_{now.strftime('%Y%m%d_%H%M')}"
                send_telegram_alert(change_score, task_name, cleaned_alerts, latest_img, region)
