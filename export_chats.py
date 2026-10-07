"""Export the Teams chat open in Edge to a readable HTML file.

Edge must run with a debugging port and its own profile, e.g.:
  msedge.exe --remote-debugging-port=9222 --user-data-dir=C:\\AI\\WorkSpace\\teams-chats\\.edge-profile
Then: uv run export_chats.py [--since YYYY-MM-DD] [--out exports]
"""

import argparse
import html
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"

# Teams DOM hooks; update here if Teams changes its markup.
SELECTORS = {
    "title": '[data-tid="chat-title"]',
    "viewport": '[data-tid="message-pane-list-viewport"]',
    "item": '[data-tid="chat-pane-item"]',
    "message": '[data-tid="chat-pane-message"]',
    "author": '[data-tid="message-author-name"]',
    "content": "[data-message-content]",
}

# Collects the messages currently rendered. Images are inlined as data URIs
# because Teams serves them from blob:/authenticated URLs that won't work offline.
EXTRACT_JS = r"""async (S) => {
  const toDataUri = async (src) => {
    try {
      const blob = await (await fetch(src, {credentials: 'include'})).blob();
      return await new Promise(r => { const f = new FileReader(); f.onload = () => r(f.result); f.readAsDataURL(blob); });
    } catch { return src; }
  };
  const out = [];
  for (const item of document.querySelectorAll(S.item)) {
    const msg = item.querySelector(S.message);
    if (!msg) continue;
    const body = msg.cloneNode(true);
    body.querySelectorAll('button, [role="none"], script, style').forEach(e => e.remove());
    for (const img of body.querySelectorAll('img')) {
      const src = img.currentSrc || img.src;
      if (src && !src.startsWith('data:')) img.src = await toDataUri(src);
      img.removeAttribute('srcset');
    }
    out.push({
      id: msg.dataset.mid,
      author: item.querySelector(S.author)?.innerText.trim() || '',
      timestamp: item.querySelector('time[datetime]')?.getAttribute('datetime') || '',
      mine: !!item.querySelector('.fui-ChatMyMessage'),
      html: body.innerHTML,
    });
  }
  return out;
}"""


# Id of the oldest message currently rendered in the viewport.
FIRST_MID_JS = "(el, sel) => el.querySelector(sel)?.dataset.mid || ''"


def connect(p):
    browser = p.chromium.connect_over_cdp(CDP_URL)
    for ctx in browser.contexts:
        for page in ctx.pages:
            if "teams.cloud.microsoft" in page.url or "teams.microsoft.com" in page.url:
                return page
    sys.exit("No Teams tab found in the debug Edge window.")


def load_history(page, since):
    """Scroll up one screen at a time (so virtualized messages aren't skipped),
    collecting messages until the top is reached and nothing new loads."""
    messages, misses = {}, 0
    page.eval_on_selector(SELECTORS["viewport"], "el => el.scrollTop = el.scrollHeight")
    time.sleep(2)
    while misses < 3:
        for m in page.evaluate(EXTRACT_JS, SELECTORS):
            messages.setdefault(m["id"], m)
        oldest = min((m["timestamp"] for m in messages.values() if m["timestamp"]), default="")
        print(f"\r  {len(messages)} messages, oldest {oldest[:10]}", end="", flush=True)
        if since and oldest and oldest < since:
            break
        at_top = page.eval_on_selector(
            SELECTORS["viewport"], "el => { el.scrollTop -= el.clientHeight * 0.8; return el.scrollTop <= 0; }"
        )
        if not at_top:
            time.sleep(0.3)
            continue
        # At the top: Teams may take many seconds to fetch older messages.
        # Wait for the first rendered message to change; nudge the scroll to re-trigger loading.
        first = page.eval_on_selector(SELECTORS["viewport"], FIRST_MID_JS, SELECTORS["message"])
        page.eval_on_selector(SELECTORS["viewport"], "el => { el.scrollTop = 300; el.scrollTop = 0; }")
        try:
            page.wait_for_function(
                f"([v, s, f]) => ({FIRST_MID_JS})(document.querySelector(v), s) !== f",
                arg=[SELECTORS["viewport"], SELECTORS["message"], first],
                timeout=20000,
            )
            misses = 0
        except PlaywrightTimeout:
            misses += 1
    print()
    result = sorted(messages.values(), key=lambda m: (m["timestamp"], m["id"]))
    if since:
        result = [m for m in result if not m["timestamp"] or m["timestamp"] >= since]
    # Consecutive messages from one sender omit the author name; carry it forward.
    last = ""
    for m in result:
        m["author"] = m["author"] or last
        last = m["author"]
    return result


def clean_html(fragment):
    fragment = re.sub(r"<(script|style)\b.*?</\1>", "", fragment, flags=re.S | re.I)
    return re.sub(r"\s on\w+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", "", fragment, flags=re.I)


CSS = """
:root { --bg:#f5f5f5; --fg:#242424; --muted:#707070; --card:#fff; --mine:#e8ebfa; --line:#e0e0e0; --accent:#5b5fc7; }
@media (prefers-color-scheme: dark) { :root { --bg:#1f1f1f; --fg:#e6e6e6; --muted:#a0a0a0; --card:#2b2b2b; --mine:#2f3259; --line:#3a3a3a; --accent:#9ea2ff; } }
body { margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 "Segoe UI", "Microsoft JhengHei", sans-serif; }
main { max-width:860px; margin:0 auto; padding:24px 16px 64px; }
header { border-bottom:1px solid var(--line); margin-bottom:16px; }
h1 { font-size:22px; margin:0 0 4px; } .meta { color:var(--muted); font-size:13px; margin-bottom:12px; }
.day { text-align:center; color:var(--muted); font-size:13px; margin:24px 0 8px; }
.msg { background:var(--card); border-radius:8px; padding:8px 12px; margin:6px 0; max-width:85%; overflow-wrap:anywhere; }
.msg.mine { background:var(--mine); margin-left:auto; }
.who { font-weight:600; font-size:13px; } .when { color:var(--muted); font-size:12px; margin-left:8px; }
.body p { margin:4px 0; } .body img { max-width:100%; height:auto; } a { color:var(--accent); }
blockquote { border-left:3px solid var(--line); margin:4px 0; padding-left:8px; color:var(--muted); }
"""


def render_html(title, messages):
    people = sorted({m["author"] for m in messages if m["author"]})
    parts, day = [], None
    for m in messages:
        ts = datetime.fromisoformat(m["timestamp"].replace("Z", "+00:00")).astimezone() if m["timestamp"] else None
        d = ts.strftime("%Y-%m-%d (%a)") if ts else "Unknown date"
        if d != day:
            parts.append(f'<div class="day">{d}</div>')
            day = d
        when = ts.strftime("%H:%M") if ts else ""
        parts.append(
            f'<div class="msg{" mine" if m["mine"] else ""}"><div><span class="who">{html.escape(m["author"])}</span>'
            f'<span class="when">{when}</span></div><div class="body">{clean_html(m["html"])}</div></div>'
        )
    exported = datetime.now().strftime("%Y-%m-%d %H:%M")
    return (
        f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body><main><header><h1>{html.escape(title)}</h1>"
        f'<div class="meta">Participants: {html.escape(", ".join(people))}<br>{len(messages)} messages · exported {exported}</div>'
        f"</header>{''.join(parts)}</main></body></html>"
    )


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", help="only export messages on/after this date (YYYY-MM-DD)")
    ap.add_argument("--out", default="exports", help="output folder (default: exports)")
    args = ap.parse_args()
    since = datetime.fromisoformat(args.since).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") if args.since else None
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    sys.stdout.reconfigure(encoding="utf-8")

    with sync_playwright() as p:
        page = connect(p)
        while input("Open a chat in Edge, then press Enter to export (q to quit): ").strip().lower() != "q":
            title = page.inner_text(SELECTORS["title"]).strip()
            print(f"Exporting: {title}")
            messages = load_history(page, since)
            # With a departed user Teams titles the chat with your own name; use the others instead.
            me = {m["author"] for m in messages if m["mine"]}
            if title in me:
                title = ", ".join(sorted({m["author"] for m in messages} - me - {""})) or title
            name =re.sub(r'[\\/:*?"<>|]', "_", title)
            path = out / f"{name}_{datetime.now():%Y%m%d}.html"
            path.write_text(render_html(title, messages), encoding="utf-8")
            print(f"Saved {len(messages)} messages -> {path}")


if __name__ == "__main__":
    main()
