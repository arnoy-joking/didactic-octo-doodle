from flask import Flask, request, jsonify
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound
import requests
import re

app = Flask(__name__)

def get_video_id(url):
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def get_proxy():
    try:
        resp = requests.get(
            "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc", 
            timeout=5
        )
        data = resp.json()
        for item in data.get('data', []):
            ip = item.get('ip')
            port = item.get('port')
            protocol = item.get('protocols', ['http'])[0]
            if ip and port:
                proxy_url = f"{protocol}://{ip}:{port}"
                return {"http": proxy_url, "https": proxy_url}
    except Exception:
        return None
    return None

@app.route("/api/subtitles", methods=["GET", "POST"])
def transcript():
    if request.method == "POST":
        url = request.json.get("url")
    else:
        url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing YouTube URL parameter."}), 400
    video_id = get_video_id(url)
    if not video_id:
        return jsonify({"error": "Invalid YouTube URL."}), 400
    proxy = get_proxy()
    if not proxy:
        return jsonify({"error": "Could not obtain a proxy."}), 500
    orig_request = requests.request
    def proxy_request(method, url, **kwargs):
        kwargs['proxies'] = proxy
        kwargs['timeout'] = 10
        return orig_request(method, url, **kwargs)
    requests.request = proxy_request
    lang_codes = ['en', 'bn', 'hi', 'ar']
    try:
        try:
            transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=lang_codes)
        except NoTranscriptFound:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            found = False
            for candidate in ['bn', 'hi', 'ar']:
                for t in transcript_list:
                    if t.is_generated and t.language_code == candidate and t.is_translatable:
                        transcript = t.translate('en').fetch()
                        found = True
                        break
                if found:
                    break
            if not found:
                return jsonify({"error": "No suitable transcripts found."}), 404
        transcript_text = "\n".join([item['text'] for item in transcript])
        return jsonify({"transcript": transcript_text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        requests.request = requests.sessions.Session.request

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
