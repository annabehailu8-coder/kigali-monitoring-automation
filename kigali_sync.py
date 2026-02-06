import ee
import os
import json

# 1. Initialize Earth Engine with Service Account
# The secret is stored in GitHub and passed here
gee_json_key = json.loads(os.environ['GEE_JSON_KEY'])
ee.Initialize(ee.ServiceAccountCredentials(gee_json_key['client_email'], key_data=os.environ['GEE_JSON_KEY']))

# 2. Define Area of Interest (Kigali) [cite: 463, 843]
# Replace with your actual Asset ID from Step 8/9
kigali_aoi = ee.FeatureCollection("projects/kigali-sync-final/assets/KIgali_City")

# 3. Delta Check: Read last processed ID [cite: 863]
state_file = 'last_image_id.txt'
last_id = ""
if os.path.exists(state_file):
    with open(state_file, 'r') as f:
        last_id = f.read().strip()

# 4. Fetch Latest Sentinel-2 (Optical) [cite: 854, 855]
s2_collection = (ee.ImageCollection("COPERNICUS/S2_HARMONIZED")
                 .filterBounds(kigali_aoi)
                 .filterDate(ee.Date(ee.Date.now().advance(-30, 'day')), ee.Date.now())
                 .sort('system:time_start', False))

latest_image = s2_collection.first()

# 5. Logical Trigger [cite: 865]
if latest_image:
    current_id = latest_image.id().getInfo()
    
    if current_id != last_id:
        print(f"New Image Found: {current_id}. Starting Processing...")
        
        # [PHASE 2 LOGIC WILL GO HERE: Cloud Masking & Radar Fusion]
        
        # Update the Delta file for next time [cite: 881]
        with open(state_file, 'w') as f:
            f.write(current_id)
    else:
        print("No new imagery since last check.")
else:
    print("No images found in the last 5 days. Checking Radar fallback...")
