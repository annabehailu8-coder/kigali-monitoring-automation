import ee
import geemap
import datetime

# 1. Initialize Earth Engine
# Replace with your actual project ID from the screenshots
PROJECT_ID = 'kigali-nrt-lulc-detection-tool'
ee.Initialize(project=PROJECT_ID)

# 2. Define Kigali Area of Interest (AOI)
# Using the asset we verified is working in your GEE account
kigali_aoi = ee.FeatureCollection(f"projects/kigali-nrt-lulc-detection-tool/assets/KIgali_City").geometry()

# 3. Access Sentinel-2 Collection
# Look for images from the last 30 days to ensure we find data
start_date = (datetime.datetime.now() - datetime.timedelta(days=30)).strftime('%Y-%m-%d')
end_date = datetime.datetime.now().strftime('%Y-%m-%d')

s2_collection = (ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
    .filterBounds(kigali_aoi)
    .filterDate(start_date, end_date)
    .sort('CLOUDY_PIXEL_PERCENTAGE'))

# 4. Get the latest image
latest_image = s2_collection.first()

# 5. Check if image exists and visualize
if latest_image.getInfo():
    print(f"Latest Image ID: {latest_image.get('system:index').getInfo()}")
    
    # Create an interactive map
    Map = geemap.Map()
    Map.centerObject(kigali_aoi, 12)
    
    # Define visualization parameters
    viz_params = {'bands': ['B4', 'B3', 'B2'], 'min': 0, 'max': 3000}
    
    Map.addLayer(latest_image, viz_params, 'Latest Sentinel-2')
    Map.addLayer(kigali_aoi, {'color': 'red'}, 'Kigali Boundary', False)
    
    display(Map)
    
    # 6. Prepare Export (M2M style)
    # In Python, this creates the task and starts it immediately if you uncomment .start()
    task = ee.batch.Export.image.toDrive(
        image=latest_image.select(['B4', 'B3', 'B2', 'B8']),
        description='Kigali_Export_Local_Python',
        folder='GEE_Python_Outputs',
        region=kigali_aoi.getInfo()['coordinates'],
        scale=10,
        crs='EPSG:4326'
    )
    
    print("Ready to export. To run the export, execute: task.start()")
else:
    print("No images found in the specified date range.") "Add sync script"
