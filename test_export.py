import urllib.request
import json

url = 'http://localhost:8000/api/export/generate'
payload = json.dumps({
    "export_type": "scores",
    "filter_condition": {"class_id": 29},
    "format": "xlsx",
    "options": {}
}, ensure_ascii=False).encode('utf-8')

req = urllib.request.Request(url, data=payload, method='POST', headers={'Content-Type': 'application/json'})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    print(json.dumps(data, ensure_ascii=False, indent=2))

# Download the file
download_url = f'http://localhost:8000/api/export/download/{data["id"]}'
req2 = urllib.request.Request(download_url)
with urllib.request.urlopen(req2) as resp2:
    content = resp2.read()
    path = f'h:/DAIMA/CJjiangxuej/test_export_{data["id"]}.xlsx'
    with open(path, 'wb') as f:
        f.write(content)
    print(f'Downloaded to {path}, size={len(content)} bytes')
