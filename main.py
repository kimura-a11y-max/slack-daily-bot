"""
Slack Daily News Bot（完全無料版）
- NewsAPI から最新ニュースを取得
- note RSS からトレンド記事を取得
- タイトル＋リンク付きで Slack に投稿（AI要約なし）
"""

import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

NEWSAPI_KEY       = os.environ.get("NEWSAPI_KEY", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")

NEWS_QUERY        = os.environ.get("NEWS_QUERY", "テクノロジー OR AI OR スタートアップ")
NEWS_LANGUAGE     = os.environ.get("NEWS_LANGUAGE", "jp")
NEWS_PAGE_SIZE    = int(os.environ.get("NEWS_PAGE_SIZE", "5"))
NOTE_RSS_URL      = os.environ.get("NOTE_RSS_URL", "https://note.com/api/v1/rss")
NOTE_MAX_ARTICLES = int(os.environ.get("NOTE_MAX_ARTICLES", "5"))

JST = timezone(timedelta(hours=9))


def fetch_newsapi_articles() -> list[dict]:
    if not NEWSAPI_KEY:
        print("[WARN] NEWSAPI_KEY が未設定です。スキップします。")
        return []
    yesterday = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
    params = urllib.parse.urlencode({
        "q": NEWS_QUERY, "language": NEWS_LANGUAGE, "from": yesterday,
        "sortBy": "relevancy", "pageSize": NEWS_PAGE_SIZE, "apiKey": NEWSAPI_KEY,
    })
    url = f"https://newsapi.org/v2/everything?{params}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SlackDailyBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        articles = [
            {"source": a.get("source", {}).get("name") or "NewsAPI",
             "title": a.get("title", ""), "url": a.get("url", "")}
            for a in data.get("articles", []) if a.get("title") and a.get("url")
        ]
        print(f"[INFO] NewsAPI: {len(articles)} 件取得")
        return articles
    except Exception as e:
        print(f"[ERROR] NewsAPI 取得失敗: {e}")
        return []


def fetch_note_rss() -> list[dict]:
    try:
        req = urllib.request.Request(NOTE_RSS_URL, headers={"User-Agent": "SlackDailyBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        articles = []
        for item in items[:NOTE_MAX_ARTICLES]:
            title = _xml_text(item, "title")
            link  = _xml_text(item, "link")
            if title and link:
                articles.append({"source": "note", "title": title, "url": link})
        print(f"[INFO] note RSS: {len(articles)} 件取得")
        return articles
    except Exception as e:
        print(f"[ERROR] note RSS 取得失敗: {e}")
        return []


def _xml_text(element, tag: str) -> str:
    child = element.find(tag)
    return (child.text or "").strip() if child is not None else ""


def build_slack_blocks(newsapi_articles: list[dict], note_articles: list[dict]) -> list[dict]:
    today = datetime.now(JST).strftime("%Y/%m/%d (%a)")
    blocks = [{"type": "header", "text": {"type": "plain_text", "text": f"Daily News Digest - {today}", "emoji": True}}]
    if newsapi_articles:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*:newspaper: 今日のニュース（NewsAPI）*"}})
        lines = [f"• <{a['url']}|{a['title']}> _{a['source']}_" for a in newsapi_articles]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
    if note_articles:
        blocks.append({"type": "divider"})
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "*:memo: note トレンド*"}})
        lines = [f"• <{a['url']}|{a['title']}>" for a in note_articles]
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(lines)}})
    if not newsapi_articles and not note_articles:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": "本日取得できた記事はありませんでした。"}})
    blocks.append({"type": "divider"})
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": "Powered by NewsAPI + note RSS"}]})
    return blocks


def post_to_slack(blocks: list[dict]) -> None:
    if not SLACK_WEBHOOK_URL:
        print("[WARN] SLACK_WEBHOOK_URL が未設定。標準出力に表示します。")
        print(json.dumps(blocks, ensure_ascii=False, indent=2))
        return
    body = json.dumps({"blocks": blocks}).encode()
    req  = urllib.request.Request(SLACK_WEBHOOK_URL, data=body,
                                   headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[INFO] Slack 投稿成功 (status={resp.status})")
    except Exception as e:
        print(f"[ERROR] Slack 投稿失敗: {e}")


def main():
    print(f"[START] {datetime.now(JST).isoformat()}")
    newsapi_articles = fetch_newsapi_articles()
    note_articles    = fetch_note_rss()
    blocks = build_slack_blocks(newsapi_articles, note_articles)
    post_to_slack(blocks)
    print(f"[END] {datetime.now(JST).isoformat()}")


if __name__ == "__main__":
    main()
