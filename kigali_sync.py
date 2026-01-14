import ee
import osimport ee
import os
import json

def initialize_gee():
    """
    Authenticates and initializes Earth Engine using a Service Account.
    Expects GEE_JSON_KEY as a GitHub secret containing the full JSON key.
    """
    try:
        # 1. Load the Service Account key from environment variables
        key_json = os.environ.get('GEE_JSON_KEY')
        
        if not key_json:
            print("❌ ERROR: GEE_JSON_KEY not found in environment.")
            return False

        # 2. Parse the JSON to get the service account email
        key_dict = json.loads(key_json)
        service_account = key_dict.get('client_email')
        
        if not service_account:
            print("❌ ERROR: Could not find 'client_email' in the JSON key.")
            return False

        # 3. Create credentials object
        # Note: We pass the JSON string directly to key_data
        credentials = ee.ServiceAccountCredentials(service_account, key_data=key_json)

        # 4. Initialize with your NEW project ID
        # REPLACE 'kigali-sync-final' with your actual new project ID
        project_id = 'kigali-sync-final' 
        
        ee.Initialize(credentials, project=project_id)
        
        print(f"✅ Successfully initialized GEE with project: {project_id}")
        return True

    except Exception as e:
        print(f"❌ Failed to initialize Earth Engine: {e}")
        return False

def main():
    if initialize_gee():
        # --- YOUR KIGALI SYNC LOGIC STARTS HERE ---
        print("Starting Kigali monitoring sync...")
        
        # Example: Test the connection by getting info about a simple object
        test_point = ee.Geometry.Point([30.06, -1.94]) # Kigali coordinates
        print(f"Connection test successful. Point created: {test_point.getInfo()}")
        
        # --- END OF YOUR LOGIC ---
    else:
        exit(1) # Exit with error code for GitHub Actions

if __name__ == "__main__":
    main()
import json
import datetime

def initialize_gee():
    """Initializes Earth Engine using the Service Account key from GitHub Secrets."""
    try:
        # Get the JSON key from environment variable
        key_json = os.environ.get('GEE_JSON_KEY')
        if not key_json:
            print("❌ Error: GEE_JSON_KEY environment variable is missing.")
            return False

        # Parse key and create credentials
        key_dict = json.loads(key_json)
        credentials = ee.ServiceAccountCredentials(key_dict['client_email'], key_data=key_json)
        
        # Initialize with your Project ID
        # IMPORTANT: Ensure this matches the project you registered!
        ee.Initialize(credentials, project=key_dict['project_id'])
        print(f"✅ GEE Initialized successfully for project: {key_dict['project_id']}")
        return True
    except Exception as e:
        print(f"❌ Failed to initialize GEE: {e}")
        return False

def run_analysis():
    """Main logic for Kigali Land Use Detection."""
    
    # 1. Define Region of Interest (ROI) - Official Kigali Boundary
    kigali_roi = ee.FeatureCollection("FAO/GAUL/2015/level2") \
        .filter(ee.Filter.eq('ADM2_NAME', 'Kigali'))
    roi_geometry = kigali_roi.geometry()

    # 2. Set Date Range (Last 6 months)
    end_date = datetime.datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.datetime.now() - datetime.timedelta(days=180)).strftime('%Y-%m-%d')

    # 3. Load Sentinel-2 Imagery & Filter
    # We use 'Harmonized' for consistent time-series analysis
    s2_collection = ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED") \
        .filterBounds(roi_geometry) \
        .filterDate(start_date, end_date) \
        .filter(ee.Filter.lt('CLOUDY_PIXEL_PERCENTAGE', 20))

    # Create a cloud-free median composite
    composite = s2_collection.median().clip(roi_geometry)

    # 4. Land Use Calculation (Urban Index Example)
    # NDBI (Normalized Difference Built-Up Index) helps detect urban sprawl
    # Formula: (SWIR - NIR) / (SWIR + NIR)
    ndbi = composite.normalizedDifference(['B11', 'B8']).rename('NDBI')

    # Identify "Urban" pixels (NDBI > 0 is often indicative of built-up area)
    urban_threshold = 0.1
    urban_pixels = ndbi.gt(urban_threshold)

    # 5. Calculate Total Urban Area in Square Kilometers
    area_image = urban_pixels.multiply(ee.Image.pixelArea())
    area_stats = area_image.reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=roi_geometry,
        scale=10, # Sentinel-2 resolution is 10m
        maxPixels=1e9
    )

    urban_area_sqkm = area_stats.get('NDBI').getInfo() / 1_000_000

    # 6. Output Results to GitHub Logs
    print("-" * 30)
    print(f"KIGALI MONITORING REPORT")
    print(f"Date Range: {start_date} to {end_date}")
    print(f"Detected Urban Area: {urban_area_sqkm:.2f} sq km")
    print("-" * 30)

if __name__ == "__main__":
    if initialize_gee():
        run_analysis()
    else:
        exit(1)
