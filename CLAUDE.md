# CLAUDE.md

This is a single-script tool, `export_chats.py`, that exports the Teams chat open in Edge to HTML. The README covers usage.

## Constraints
- **No Microsoft Graph API.** Company policy forbids it. Data comes only from the rendered Teams web page, read with Playwright over CDP.
- **Use uv, not pip:** `uv add <pkg>`, `uv run export_chats.py`.
- **Edge 153 ignores `--remote-debugging-port` on the default profile.** Always use `--user-data-dir=C:\AI\WorkSpace\teams-chats\.edge-profile`. The Teams tab URL is `teams.cloud.microsoft`.
- The Teams UI language is Traditional Chinese. Don't rely on visible text or aria-labels. Use `data-tid` hooks and `<time datetime>`, which is ISO UTC.
- Set `sys.stdout.reconfigure(encoding="utf-8")` when printing chat text. The Windows console is not UTF-8.

## DOM (verified 2026-09 against the live page)
- `chat-pane-item` wraps each message or day divider.
- `chat-pane-message` holds the message, with a stable id in `data-mid`.
- `message-author-name` is missing on consecutive messages from the same sender, so the author is carried forward.
- `.fui-ChatMyMessage` marks your own messages.
- `message-pane-list-viewport` is the scroll container, and `chat-title` is the header.
- Teams only keeps visible messages in the page, so collect messages at every scroll step. Never jump straight to the top, or messages get skipped.

## Working with a live session
- Probe the page read-only first: count `[data-tid]` values and dump a DOM skeleton. Do this before changing the extraction code.
- Long exports: run in the background and tell the user not to touch the Edge window.
- To check an export, count messages per author, compare the first and last dates, and list the largest gaps between days. Confirm completeness with the user, who can scroll the chat in Teams.
- Teams can stall while loading history: a spinner shows but it sends no network requests. When that happens, the user scrolls to the top by hand. Then scroll **down** from there to the first message already exported, and merge the result into the existing file. Back up the file first.
