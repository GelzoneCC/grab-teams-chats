# teams-chats

Export Microsoft Teams chats to self-contained, human-readable HTML files. The script reads the chat you have open in Teams on the web, so no Graph API or app registration is needed.

## Output

The script writes one file per chat: `exports/<chat title>_<YYYYMMDD>.html`.

- Messages are grouped by day, with sender and local time. Your own messages are right-aligned.
- Formatting, links, mentions and quotes are kept.
- Images are embedded as data URIs, so the file works offline. Files with many images can get large, around 40 MB for about 8,000 messages.
- Light and dark themes follow your system setting.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Microsoft Edge.

```
uv sync
```

The script drives your installed Edge, so it doesn't download a browser.

## Usage

1. Start Edge with a debugging port and a separate profile:

   ```
   "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --user-data-dir=C:\AI\WorkSpace\teams-chats\.edge-profile
   ```

   You need the separate profile because Edge 136 and later ignore the debugging port on your normal profile. Sign in to Teams on the web there once, and the profile keeps you signed in. It can run alongside your normal Edge.

2. Run the exporter:

   ```
   uv run export_chats.py [--since YYYY-MM-DD] [--out exports]
   ```

3. Click a chat in the debug Edge window, then press Enter in the terminal. Repeat for more chats, and type `q` to quit.

Don't use the Edge window while an export runs. A long chat can take from several minutes to about an hour.

## How it works

- The script connects to Edge over CDP (`localhost:9222`) and finds the Teams tab.
- It jumps to the newest message, then scrolls up one screen at a time and collects messages as it goes. Teams only keeps visible messages in the page, so collecting at every step avoids gaps.
- At the top it waits up to 20 seconds for Teams to load older messages. It stops after three tries in a row bring in nothing.
- It removes duplicate messages by Teams message id and sorts them by timestamp. For a colleague who has left, Teams titles the chat with *your* name, so the file is named after the other participants instead.

## Known issues

- **Teams stops loading history.** On long chats, Teams on the web can show a spinner forever without sending any request, and the export stops at that point. To work around it, scroll to the top in Edge by hand, then export the missing older part starting from that position. Merge that part into the existing file.
- **Teams changes its page layout.** All page selectors are in the `SELECTORS` dict at the top of `export_chats.py`. If an export comes back empty, check those selectors first.

## Privacy

`.edge-profile/` holds your Teams sign-in session and `exports/` holds chat content. Both are git-ignored. Keep them private, and check that exporting chats is allowed under your company's data policy.
