import html
import logging
import mimetypes
import os
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from telegram import ReplyKeyboardMarkup, Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

BTN_GENERATE = "⚡ Generate HTML"
BTN_CLEAR = "🗑 Clear"
BTN_STATUS = "📊 Status"

KEYBOARD = ReplyKeyboardMarkup(
    [[BTN_GENERATE], [BTN_STATUS, BTN_CLEAR]],
    resize_keyboard=True,
    is_persistent=True,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("lotfibot")


def session(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    return context.user_data.setdefault("items", [])


def reset_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data["items"] = []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_session(context)
    await update.effective_message.reply_text(
        "Send or forward text and photos here.\n"
        "When you're done, tap ⚡ Generate HTML and I'll return a ZIP.",
        reply_markup=KEYBOARD,
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_session(context)
    await update.effective_message.reply_text("Cleared. Send the new messages.", reply_markup=KEYBOARD)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = session(context)
    texts = sum(1 for x in items if x["type"] == "text")
    images = sum(1 for x in items if x["type"] == "image")
    await update.effective_message.reply_text(
        f"Collected: {len(items)} items\n📝 Text: {texts}\n🖼 Images: {images}",
        reply_markup=KEYBOARD,
    )


async def collect_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return

    if msg.text == BTN_GENERATE:
        await generate(update, context)
        return
    if msg.text == BTN_CLEAR:
        await clear(update, context)
        return
    if msg.text == BTN_STATUS:
        await status(update, context)
        return

    session(context).append(
        {
            "type": "text",
            "html": msg.text_html or html.escape(msg.text),
        }
    )
    await msg.reply_text(f"✓ Added #{len(session(context))}", reply_markup=KEYBOARD)


async def collect_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.photo:
        return

    photo = msg.photo[-1]
    session(context).append(
        {
            "type": "image",
            "file_id": photo.file_id,
            "caption_html": msg.caption_html or (html.escape(msg.caption) if msg.caption else ""),
            "mime_type": "image/jpeg",
        }
    )
    await msg.reply_text(f"✓ Added #{len(session(context))}", reply_markup=KEYBOARD)


async def collect_image_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    doc = msg.document if msg else None
    if not doc or not (doc.mime_type or "").startswith("image/"):
        return

    session(context).append(
        {
            "type": "image",
            "file_id": doc.file_id,
            "caption_html": msg.caption_html or (html.escape(msg.caption) if msg.caption else ""),
            "mime_type": doc.mime_type or "image/jpeg",
        }
    )
    await msg.reply_text(f"✓ Added #{len(session(context))}", reply_markup=KEYBOARD)


def render_html(items: list[dict], asset_names: dict[int, str]) -> str:
    blocks = []
    for i, item in enumerate(items):
        n = i + 1
        if item["type"] == "text":
            blocks.append(
                f'<article class="card text-card" data-index="{n}">'
                f'<div class="content" dir="auto">{item["html"]}</div>'
                f"</article>"
            )
        else:
            src = html.escape(asset_names[i], quote=True)
            caption = item.get("caption_html") or ""
            cap = f'<figcaption dir="auto">{caption}</figcaption>' if caption else ""
            blocks.append(
                f'<article class="card image-card" data-index="{n}">'
                f'<figure><img src="{src}" loading="lazy" alt="Image {n}">{cap}</figure>'
                f"</article>"
            )

    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = "\n".join(blocks)
    return f"""<!doctype html>
<html lang="en" dir="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chat Export</title>
<style>
:root {{
  color-scheme: light dark;
  --bg:#0b1020;
  --panel:#121a2d;
  --text:#eef3ff;
  --muted:#93a4c7;
  --line:rgba(255,255,255,.09);
  --shadow:0 16px 50px rgba(0,0,0,.28);
}}
* {{ box-sizing:border-box; }}
html {{ scroll-behavior:smooth; }}
body {{
  margin:0; background:linear-gradient(180deg,#0b1020 0%,#0d1426 100%);
  color:var(--text); font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;
}}
.wrap {{ width:min(920px,calc(100% - 28px)); margin:0 auto; padding:32px 0 64px; }}
.hero {{
  padding:28px; margin-bottom:18px; border:1px solid var(--line); border-radius:24px;
  background:rgba(18,26,45,.78); backdrop-filter:blur(10px); box-shadow:var(--shadow);
}}
h1 {{ margin:0 0 8px; font-size:clamp(28px,6vw,46px); letter-spacing:-.04em; }}
.meta {{ color:var(--muted); font-size:14px; }}
.feed {{ display:grid; gap:14px; }}
.card {{
  border:1px solid var(--line); border-radius:22px; background:var(--panel); overflow:hidden;
  box-shadow:0 8px 30px rgba(0,0,0,.18);
}}
.content {{
  padding:20px 22px; white-space:pre-wrap; unicode-bidi:plaintext; line-height:1.75;
  font-size:17px; overflow-wrap:anywhere;
}}
.content a, figcaption a {{ color:#7dd3fc; }}
figure {{ margin:0; }}
img {{ display:block; width:100%; height:auto; max-height:78vh; object-fit:contain; background:#080d18; }}
figcaption {{
  padding:16px 18px 18px; white-space:pre-wrap; unicode-bidi:plaintext; line-height:1.7;
}}
footer {{ margin-top:22px; text-align:center; color:var(--muted); font-size:13px; }}
@media (prefers-color-scheme: light) {{
  :root {{--bg:#f4f7fb;--panel:#fff;--text:#172033;--muted:#64748b;--line:rgba(15,23,42,.09);--shadow:0 14px 42px rgba(15,23,42,.08);}}
  body {{ background:linear-gradient(180deg,#f7f9fc,#eef3f8); }}
  .hero {{ background:rgba(255,255,255,.86); }}
  img {{ background:#f3f4f6; }}
  .content a, figcaption a {{ color:#0369a1; }}
}}
</style>
</head>
<body>
<main class="wrap">
  <section class="hero">
    <h1>Chat Export</h1>
    <div class="meta">{len(items)} items · Generated {created}</div>
  </section>
  <section class="feed">
    {body}
  </section>
  <footer>Generated by Chat to HTML Bot</footer>
</main>
</body>
</html>"""


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    items = list(session(context))
    if not items:
        await msg.reply_text("Nothing collected yet. Send or forward some messages first.", reply_markup=KEYBOARD)
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.UPLOAD_DOCUMENT)
    progress = await msg.reply_text(f"Building ZIP from {len(items)} items…")

    try:
        with tempfile.TemporaryDirectory(prefix="lotfibot_") as tmp:
            root = Path(tmp) / "export"
            assets = root / "assets"
            assets.mkdir(parents=True)

            asset_names: dict[int, str] = {}
            image_no = 0

            for i, item in enumerate(items):
                if item["type"] != "image":
                    continue

                image_no += 1
                mime = item.get("mime_type") or "image/jpeg"
                ext = mimetypes.guess_extension(mime) or ".jpg"
                if ext == ".jpe":
                    ext = ".jpg"

                name = f"image_{image_no:03d}{ext}"
                path = assets / name
                tg_file = await context.bot.get_file(item["file_id"])
                await tg_file.download_to_drive(custom_path=path)
                asset_names[i] = f"assets/{name}"

            (root / "index.html").write_text(render_html(items, asset_names), encoding="utf-8")

            zip_path = Path(tmp) / "chat_export.zip"
            with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                for file in root.rglob("*"):
                    if file.is_file():
                        zf.write(file, file.relative_to(root))

            with zip_path.open("rb") as f:
                await msg.reply_document(
                    document=f,
                    filename="chat_export.zip",
                    caption=f"Done ✓ {len(items)} items exported.",
                    reply_markup=KEYBOARD,
                )

        reset_session(context)
        await progress.delete()
    except Exception:
        log.exception("generation failed")
        await progress.edit_text(
            "Generation failed. Your collected messages are still saved in this session, so you can try again."
        )


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "I currently accept text, photos, and image files.",
        reply_markup=KEYBOARD,
    )


def main() -> None:
    app = Application.builder().token(TOKEN).concurrent_updates(False).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.PHOTO, collect_photo))
    app.add_handler(MessageHandler(filters.Document.IMAGE, collect_image_document))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, collect_text))
    app.add_handler(MessageHandler(~filters.COMMAND, unknown))
    log.info("Bot starting with long polling")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
