"""
Slack Daily News Bot
- NewsAPI で業界ニュース取得
- note RSS でフィード取得
- Slack Webhook で投稿（デバッグログ強化版）
"""

import os
import json
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

NEWSAPI_KEY        = os.environ.get("NEWSAPI_KEY", "")
SLACK_WEBHOOK_URL  = os.environ.get("SLACK_WEBHOOK_URL", "")

NEWS_QUERY         = os.environ.get("NEWS_QUERY", "マーケティング OR AI OR インサイドセールス")
NEWS_LANGUAGE      = os.environ.get("NEWS_LANGUAGE", "ja")
NEWS_PAGE_SIZE     = int(os.environ.get("NEWS_PAGE_SIZE", "5"))
NOTE_RSS_URL       = os.environ.get("NOTE_RSS_URL", "https://note.com/api/v1/rss")
NOTE_MAX_ARTICLES  = int(os.environ.get("NOTE_MAX_ARTICLES", "5"))

JST = timezone(timedelta(hours=9))


def fetch_newsapi_articles() -> list[dict]:
    print("[DEBUG] ========== NewsAPI 取得開始 ==========")
    if not NEWSAPI_KEY:
        print("[WARN] NEWSAPI_KEY が設定されていません")
        return []
    
    yesterday = (datetime.now(JST) - timedelta(days=1)).strftime("%Y-%m-%d")
    params = urllib.parse.urlencode({
        "q": NEWS_QUERY,
        "language": NEWS_LANGUAGE,
        "sortBy": "relevancy",
        "pageSize": NEWS_PAGE_SIZE,
        "apiKey": NEWSAPI_KEY,
    })
    url = f"https://newsapi.org/v2/everything?{params}"
    
    print(f"[DEBUG] リクエスト URL: {url[:100]}...")  # キー部分は隠す
    print(f"[DEBUG] キーワード: {NEWS_QUERY}")
    print(f"[DEBUG] 言語: {NEWS_LANGUAGE}")
    
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SlackDailyBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        
        print(f"[DEBUG] ステータス: {data.get('status')}")
        print(f"[DEBUG] 総件数: {data.get('totalResults')}")
        
        articles = [
            {
                "source": a.get("source", {}).get("name") or "NewsAPI",
                "title": a.get("title", ""),
                "url": a.get("url", "")
            }
            for a in data.get("articles", [])
            if a.get("title") and a.get("url")
        ]
        
        print(f"[INFO] NewsAPI: {len(articles)}件 取得")
        for i, a in enumerate(articles[:3], 1):
            print(f"  {i}. {a['title'][:50]}...")
        
        return articles
    
    except Exception as e:
        print(f"[ERROR] NewsAPI エラー: {type(e).__name__}: {e}")
        return []


def fetch_note_rss() -> list[dict]:
    print("[DEBUG] ========== note RSS 取得開始 ==========")
    print(f"[DEBUG] RSS URL: {NOTE_RSS_URL}")
    
    try:
        req = urllib.request.Request(NOTE_RSS_URL, headers={"User-Agent": "SlackDailyBot/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_data = resp.read()
        
        print(f"[DEBUG] XML サイズ: {len(xml_data)} bytes")
        
        root = ET.fromstring(xml_data)
        items = root.findall(".//item")
        
        print(f"[DEBUG] 取得アイテム数: {len(items)}")
        
        articles = []
        for item in items[:NOTE_MAX_ARTICLES]:
            title_elem = item.find("title")
            link_elem = item.find("link")
            
            title = (title_elem.text or "").strip() if title_elem is not None else ""
            link = (link_elem.text or "").strip() if link_elem is not None else ""
            
            if title and link:
                articles.append({"source": "note", "title": title, "url": link})
                print(f"  ✓ {title[:50]}...")
        
        print(f"[INFO] note RSS: {len(articles)}件 取得")
        return articles
    
    except Exception as e:
        print(f"[ERROR] note RSS エラー: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return []


def build_slack_blocks(newsapi_articles: list[dict], note_articles: list[dict]) -> list[dict]:
    today = datetime.now(JST).strftime("%Y/%m/%d (%a)")
    
    blocks = [{
        "type": "header",
        "text": {
            "type": "plain_text",
            "text": f"📰 Daily News Digest - {today}",
            "emoji": True
        }
    }]
    
    if newsapi_articles:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*🔔 業界ニュース（NewsAPI）*"
            }
        })
        
        lines = [f"• <{a['url']}|{a['title']}>" for a in newsapi_articles]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)}
        })
    
    if note_articles:
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*📝 note 記事*"}
        })
        
        lines = [f"• <{a['url']}|{a['title']}>" for a in note_articles]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "\n".join(lines)}
        })
    
    if not newsapi_articles and not note_articles:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "本日取得できた記事はありませんでした。"
            }
        })
    
    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": "Powered by NewsAPI + note RSS"
        }]
    })
    
    return blocks


def post_to_slack(blocks: list[dict]) -> None:
    if not SLACK_WEBHOOK_URL:
        print("[WARN] SLACK_WEBHOOK_URL が設定されていません")
        print("[DEBUG] 投稿内容:")
        print(json.dumps(blocks, ensure_ascii=False, indent=2))
        return
    
    body = json.dumps({"blocks": blocks}).encode()
    req = urllib.request.Request(
        SLACK_WEBHOOK_URL,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[INFO] Slack 投稿: ステータス {resp.status}")
    except Exception as e:
        print(f"[ERROR] Slack 投稿エラー: {type(e).__name__}: {e}")


def main():
    print(f"[START] {datetime.now(JST).isoformat()}")
    print("[DEBUG] 環境変数チェック:")
    print(f"  NEWSAPI_KEY: {'✓' if NEWSAPI_KEY else '✗ 未設定'}")
    print(f"  SLACK_WEBHOOK_URL: {'✓' if SLACK_WEBHOOK_URL else '✗ 未設定'}")
    print(f"  NEWS_QUERY: {NEWS_QUERY}")
    
    newsapi_articles = fetch_newsapi_articles()
    note_articles = fetch_note_rss()
    
    print(f"\n[SUMMARY] NewsAPI: {len(newsapi_articles)}件, note: {len(note_articles)}件")
    
    blocks = build_slack_blocks(newsapi_articles, note_articles)
    post_to_slack(blocks)
    
    print(f"[END] {datetime.now(JST).isoformat()}")


if __name__ == "__main__":
    main()
