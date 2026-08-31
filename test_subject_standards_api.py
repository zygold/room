import urllib.request
import json

url = 'http://localhost:8000/api/subject-standards'
req = urllib.request.Request(url)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode('utf-8'))
    print(json.dumps(data, ensure_ascii=False, indent=2))
