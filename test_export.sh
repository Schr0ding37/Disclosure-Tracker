#!/bin/bash

# Test export functionality

echo "🔐 Step 1: Login..."
TOKEN_RESPONSE=$(curl -s -X POST http://localhost:8080/api/token \
  -d "username=Admin&password=password")

echo "Token Response: $TOKEN_RESPONSE"

TOKEN=$(echo $TOKEN_RESPONSE | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null)

if [ -z "$TOKEN" ]; then
    echo "❌ Failed to get token"
    exit 1
fi

echo "✅ Token received: ${TOKEN:0:20}..."

echo ""
echo "📦 Step 2: Testing export..."
curl -v -X GET "http://localhost:8080/api/export" \
  -H "Authorization: Bearer $TOKEN" \
  -o test_export.dtt

echo ""
echo "📊 Step 3: Checking file..."
if [ -f "test_export.dtt" ]; then
    FILE_SIZE=$(wc -c < test_export.dtt)
    echo "✅ File downloaded: test_export.dtt ($FILE_SIZE bytes)"
    
    # Check if it's a valid ZIP
    if file test_export.dtt | grep -q "Zip"; then
        echo "✅ File is a valid ZIP archive"
        echo ""
        echo "📄 ZIP Contents:"
        unzip -l test_export.dtt
    else
        echo "❌ File is NOT a valid ZIP"
        echo "File type:"
        file test_export.dtt
        echo ""
        echo "First 200 bytes:"
        head -c 200 test_export.dtt
    fi
else
    echo "❌ File was not downloaded"
fi
