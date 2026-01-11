#!/usr/bin/env python3
"""Test the export functionality"""

import requests
import json

# Step 1: Login to get token
login_url = "http://localhost:8080/api/token"
login_data = {
    "username": "Admin",
    "password": "password"
}

print("🔐 Logging in...")
response = requests.post(login_url, data=login_data)
if response.status_code != 200:
    print(f"❌ Login failed: {response.status_code}")
    print(response.text)
    exit(1)

token_data = response.json()
token = token_data.get("access_token")
print(f"✅ Login successful, token: {token[:20]}...")

# Step 2: Test export
export_url = "http://localhost:8080/api/export"
headers = {
    "Authorization": f"Bearer {token}"
}

print("\n📦 Testing export...")
response = requests.get(export_url, headers=headers)

print(f"Status Code: {response.status_code}")
print(f"Headers: {dict(response.headers)}")
print(f"Content Length: {len(response.content)} bytes")
print(f"Content Type: {response.headers.get('Content-Type')}")

if response.status_code == 200:
    # Save the file
    filename = "test_export.dtt"
    with open(filename, "wb") as f:
        f.write(response.content)
    print(f"✅ Export successful! Saved to {filename}")
    
    # Try to extract and inspect
    import zipfile
    import io
    
    try:
        with zipfile.ZipFile(io.BytesIO(response.content), 'r') as zip_file:
            print(f"\n📄 ZIP Contents:")
            for name in zip_file.namelist():
                info = zip_file.getinfo(name)
                print(f"  - {name} ({info.file_size} bytes)")
    except Exception as e:
        print(f"⚠️ Warning: Could not inspect ZIP: {e}")
else:
    print(f"❌ Export failed: {response.status_code}")
    print(f"Response: {response.text}")
