import urllib.request, urllib.error

try:
    data = b"email=admin%40campuskart.com&password=Admin%402026"
    req = urllib.request.Request("http://127.0.0.1:5000/login", data=data)
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    urllib.request.urlopen(req)
    print("Success")
except urllib.error.HTTPError as e:
    print('ERROR:', e.code)
    html = e.read().decode('utf-8')
    lines = [line for line in html.split('\n')]
    for i, line in enumerate(lines):
        if 'Traceback' in line or 'File ' in line or 'Error' in line:
            print(line)
