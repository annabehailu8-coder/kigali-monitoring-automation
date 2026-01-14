import ee
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
