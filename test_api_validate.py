import urllib.request
import json

url = 'http://localhost:8000/api/import/validate/32'
req = urllib.request.Request(url, method='POST')
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    print(json.dumps(data, ensure_ascii=False, indent=2)[:2000])
