# read_token.py
import base64
import json
import sys

sys.stdout.reconfigure(encoding="utf-8")

token = "토큰 확인"

payload = token.split(".")[1]
payload += "=" * (-len(payload) % 4)   # base64 는 길이가 4의 배수여야 한다

print(json.dumps(json.loads(base64.urlsafe_b64decode(payload)), indent=2, ensure_ascii=False))
