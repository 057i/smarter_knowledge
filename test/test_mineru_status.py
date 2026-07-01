import requests

token = "eyJ0eXBlIjoiSldUIiwiYWxnIjoiSFM1MTIifQ.eyJqdGkiOiIxMzIwMDk5NSIsInJvbCI6IlJPTEVfUkVHSVNURVIiLCJpc3MiOiJPcGVuWExhYiIsImlhdCI6MTc4MTE2NTYzMSwiY2xpZW50SWQiOiJsa3pkeDU3bnZ5MjJqa3BxOXgydyIsInBob25lIjoiIiwib3BlbklkIjpudWxsLCJ1dWlkIjoiODliOTM1OGEtN2Y1ZS00MDRhLWE1YTItYTJhYWFiZjNlZDgzIiwiZW1haWwiOiIiLCJleHAiOjE3ODg5NDE2MzF9.R9eAgDi5v5sm2y6-EFIWaEajKhCUhlm9bXcHhLNemrbzBQPtH6fm1D-64RepfwJrSLZamatrhJKIXb5_bUntAg"
base_url = "https://mineru.net/api/v4"

# 测试 MinerU 服务是否可访问
print(f"MinerU Base URL: {base_url}")
print(f"Token: {token[:30]}...")

# 测试获取批次列表
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

try:
    # 测试获取批次列表接口
    test_url = f"{base_url}/extract-results/batches"

    response = requests.get(test_url, headers=headers, timeout=10)
    print(f"\n批次列表响应: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        print(f"响应内容: {data}")

        if data.get("data") and len(data["data"]) > 0:
            print(f"\n最近的批次:")
            for batch in data["data"][:3]:
                print(f"  - batch_id: {batch.get('batch_id')}, state: {batch.get('state')}")
    else:
        print(f"响应内容: {response.text[:500]}")

except Exception as e:
    print(f"\n访问 MinerU 服务失败: {e}")

print("\n" + "="*50)
print("如果上面报错，说明 MinerU 服务可能:")
print("1. 服务不可用或维护中")
print("2. Token 已过期")
print("3. 网络问题")

