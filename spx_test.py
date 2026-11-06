import requests
from html.parser import HTMLParser

URL = "https://egy.app.spx-learning-square.com/login"

class LoginParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        a = dict(attrs)

        if tag == "form":
            print("FORM:", {
                "method": a.get("method"),
                "action": a.get("action")
            })

        if tag == "input":
            print("FIELD:", {
                "name": a.get("name"),
                "type": a.get("type")
            })

try:
    s = requests.Session()
    r = s.get(URL, timeout=20)

    print("STATUS:", r.status_code)
    print("FINAL URL:", r.url)
    print("CONTENT TYPE:", r.headers.get("Content-Type"))

    parser = LoginParser()
    parser.feed(r.text)

    print("SPX PAGE CHECK COMPLETED")

except Exception as e:
    print("CONNECTION ERROR:", type(e).name)
