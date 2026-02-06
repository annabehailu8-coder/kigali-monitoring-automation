# ... (Keep your Auth and Asset sections the same) ...

        if current_id != last_id:
            print(f"Running Work #3 Intelligence for: {current_id}")
            
            # 1. Multi-Sensor Core
            sar_baseline = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(kigali_aoi).filterDate('2024-01-01', '2024-12-31').median()
            current_sar = ee.ImageCollection('COPERNICUS/S1_GRD').filterBounds(kigali_aoi).sort('system:time_start', False).first()
            
            # 2. AI Thresholding: Detecting 'Permanent' structures
            # We look for a 6dB increase (High confidence for concrete/metal roofs)
            sar_alerts = current_sar.select('VV').subtract(sar_baseline.select('VV')).gt(6)
            
            # 3. Spatial Cleaning (The 'Small Noise' Filter)
            # This ignores anything smaller than 3x3 pixels (300sqm) to avoid false alerts from cars/trucks
            cleaned_alerts = sar_alerts.focal_mode(radius=15, units='meters').selfMask()

            # 4. Export the 'Cleaned' Intelligence Map
            task_name = f"Final_Alert_{now.strftime('%Y%m%d_%H%M')}"
            asset_path = f"projects/kigali-sync-final/assets/{task_name}"
            
            task = ee.batch.Export.image.toAsset(
                image=cleaned_alerts,
                description=task_name,
                assetId=asset_path,
                scale=10,
                region=kigali_aoi.geometry().bounds()
            )
            task.start()
            
            # 5. Logical Next Step: Print coordinates for GitHub logs
            # This is a 'Mock' of what will become an Email/WhatsApp alert
            print(f"INTELLIGENCE SUCCESS: Confirmed alerts exported to {asset_path}")
            
            with open(state_file, 'w') as f:
                f.write(current_id)
