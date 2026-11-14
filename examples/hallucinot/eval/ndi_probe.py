import json, sys, time, uuid, urllib.request, os
KEY = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".nace_key")).read().strip()
B = "https://console.nace.ai"
def call(method, url, body=None, headers=None, raw=None):
    h = {"Authorization": "Bearer " + KEY}
    if body is not None: h["Content-Type"] = "application/json"
    h.update(headers or {})
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        return json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode()[:800]); raise
path = sys.argv[1]; name = os.path.basename(path)
t = time.time()
g = call("POST", B + "/v1/documents/upload-grants", {"path": name, "ttl_seconds": 600})
print("grant keys:", sorted(g.keys()))
bnd = uuid.uuid4().hex
fdata = open(path, "rb").read()
parts = (f"--{bnd}\r\nContent-Disposition: form-data; name=\"metadata\"\r\n\r\n" + json.dumps({"path": name}) + "\r\n").encode()
parts += f"--{bnd}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"{name}\"\r\nContent-Type: application/octet-stream\r\n\r\n".encode() + fdata + f"\r\n--{bnd}--\r\n".encode()
up = urllib.request.Request(g["upload_url"], data=parts, method="POST",
                            headers={"X-Upload-Token": g["token"], "Content-Type": f"multipart/form-data; boundary={bnd}"})
u = json.load(urllib.request.urlopen(up, timeout=120))
fid = u["result"]["file"]["file_id"]; print("uploaded file_id ok; upload took", round(time.time() - t, 1), "s")
j = call("POST", B + "/v1/documents/parse?wait_seconds=60",
         {"source": {"type": "workspace_file", "workspace_id": g["workspace_id"], "file_id": fid},
          "output": {"formats": ["markdown"]}})
print("job status:", j.get("status"), "| took", round(time.time() - t, 1), "s | cost:", j.get("cost"))
res = j.get("result") or {}
print("result keys:", sorted(res.keys()))
doc = res.get("document") or {}
print("document keys:", sorted(doc.keys()) if isinstance(doc, dict) else type(doc))
md = (doc.get("markdown") if isinstance(doc, dict) else None) or res.get("markdown")
print("---- markdown ----\n", (md or json.dumps(res)[:1500])[:1500])
