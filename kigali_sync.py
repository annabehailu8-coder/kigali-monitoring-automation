import ee
import os
import json
import requests
from datetime import datetime, timedelta

def send_telegram_alert(score, task_name, alert_image, background_image, region):
    """Sends a text-based alert with GEE and Google Maps links for reliability."""
    token = os.environ.get('TELEGRAM_TOKEN')
    chat_id = os.environ.get('TELEGRAM_CHAT_ID')
    
    if not token or not chat_id:
        print("⚠️ Telegram credentials missing.")
        return

    # 1. Generate Google Maps link (Center of detection area)
    try:
        # Get coordinates of the center of the region
        center = region.centroid().getInfo()['coordinates']
        lon, lat = center[0], center[1]
        # Direct link to Google Maps Satellite view at the location
        google_maps_link = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
    except Exception as e:
        print(f"Maps Link Error: {e}")
        google_maps_link = "https://www.google.com/maps/@-1.9441,30.0619,12z" # Default Kigali center

    # 2. Generate GEE link (Direct path to your exported asset)
    gee_link = f"https://code.earthengine.google.com/?asset=projects/kigali-sync-final/assets/{task_name}"

    try:
        # 3. Formulate the alert message
        caption = (
            f"🚨 *Kigali Construction Alert*\n"
            f"Significant change detected!\n"
            f"📅 *Baseline:* 2025-01-01 to 2025-06-01\n"
            f"🏗️ *Change Score:* `{score}` pixels\n\n"
            f"🔗 [View Radar in GEE]({gee_link})\n"
            f"📍 [Open in Google Maps]({google_maps_link})"
        )
        
        # 4. Send the Telegram message
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = {
            'chat_id': chat_id, 
            'text': caption, 
            'parse_mode': 'Markdown',
            'disable_web_page_preview': False
        }
        
        response = requests.post(url, data=payload)
        if response.status_code == 200:
            print(f"📱 Telegram alert sent successfully.")
        else:
            print(f"❌ Telegram Error: {response.text}")
            
    except Exception as e:
        print(f"Alert Dispatch Error: {e}")

def run_monitoring():
    # 1. Initialize Earth Engine
    try:
        gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
        credentials = ee.ServiceAccountCredentials(
            gee_json_key['client_email'], 
            key_data=os.environ['GEE_JSON_KEY']
        )
        ee.Initialize(credentials, project='kigali-sync-final')
    except Exception as e:
        print(f"Authentication Failed: {e}"); return

    # 2. Load Region of Interest
    asset_id = "projects/kigali-sync-final/assets/kigali_boundary_custom" 
    kigali_aoi = ee.FeatureCollection(asset_id)
    region = kigali_aoi.geometry().bounds()

    # 3. Check for New Imagery (Sentinel-2)
    state_file = 'last_image_id.txt'
    last_id = open(state_file, 'r').read().strip() if os.path.exists(state_file) else ""

    now = datetime.now()
    s2_col = ee.ImageCollection("COPERNICUS/S2_HARMONIZED") \
               .filterBounds(region) \
               .filterDate((now - timedelta(days=30)).strftime('%Y-%m-%d'), now.strftime('%Y-%m-%d')) \
               .sort('system:time_start', False)
    
    latest_img = s2_col.first()

    if latest_img.getInfo():
        current_id = latest_img.id().getInfo()
        
        if current_id != last_id:
            print(f"New Image Found: {current_id}. Running 2025 Radar Analysis...")

            # --- 2025 BASELINE LOGIC ---
            # Ignores construction from 2024; starts baseline at Jan 2025
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD') \
                             .filterBounds(region) \
                             .filterDate('2025-01-01', '2025-06-01').median()
            
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD') \
                            .filterBounds(region) \
                            .sort('system:time_start', False).first()
            
            # Identify changes (6dB increase)
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)
            cleaned_alerts = sar_alerts.focal_mode(radius=1, kernelType='circle', iterations=1).selfMask()

            # Calculate change score
            stats = cleaned_alerts.reduceRegion(
                reducer=ee.Reducer.count(),
                geometry=region,
                scale=20,
                maxPixels=1e8
            )
            change_score = stats.get('VV').getInfo() or 0
            print(f"Change Score (2025 Baseline): {change_score}")

            # 4. Trigger Alert and Export
            if change_score > 5:
                task_timestamp = now.strftime('%Y%m%d_%H%M')
                task_name = f"Alert_Kigali_2025_{task_timestamp}"
                
                # Sends message with dual links (GEE + Maps)
                send_telegram_alert(change_score, task_name, cleaned_alerts, latest_img, region)

                # Export the detected changes to your Assets folder
                task = ee.batch.Export.image.toAsset(
                    image=cleaned_alerts.byte().clip(kigali_aoi),
                    description=task_name,
                    assetId=f"projects/kigali-sync-final/assets/{task_name}",
                    scale=20,
                    region=region,
                    maxPixels=1e9
                )
                task.start()
                print(f"SUCCESS: Monitoring complete. Export {task_name} active.")

            # Update delta tracking
            with open(state_file, 'w') as f:
                f.write(current_id)
        else:
            print("System Idle: No new satellite imagery detected.")
    else:
        print("Search Result: No clear images found in the last 30 days.")

if __name__ == "__main__":
    run_monitoring()
