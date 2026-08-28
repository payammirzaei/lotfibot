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
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("lotfibot")


def session(context: ContextTypes.DEFAULT_TYPE) -> list[dict]:
    return context.chat_data.setdefault("items", [])


def reset_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.chat_data["items"] = []


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_session(context)
    await update.effective_message.reply_text(
        "Ready ✓\nSend or forward text and photos here.\n"
        "When you're done, tap ⚡ Generate HTML.",
        reply_markup=KEYBOARD,
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    reset_session(context)
    await update.effective_message.reply_text("Cleared ✓", reply_markup=KEYBOARD)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    items = session(context)
    texts = sum(1 for x in items if x["type"] == "text")
    images = sum(1 for x in items if x["type"] == "image")
    await update.effective_message.reply_text(
        f"Collected: {len(items)}\n📝 Text: {texts}\n🖼 Images: {images}",
        reply_markup=KEYBOARD,
    )


async def collect(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg:
        return

    if msg.text:
        if msg.text == BTN_GENERATE:
            await generate(update, context)
            return
        if msg.text == BTN_CLEAR:
            await clear(update, context)
            return
        if msg.text == BTN_STATUS:
            await status(update, context)
            return

    item = None

    if msg.photo:
        item = {
            "type": "image",
            "file_id": msg.photo[-1].file_id,
            "caption_html": msg.caption_html or (html.escape(msg.caption) if msg.caption else ""),
            "mime_type": "image/jpeg",
        }
    elif msg.document and (msg.document.mime_type or "").startswith("image/"):
        item = {
            "type": "image",
            "file_id": msg.document.file_id,
            "caption_html": msg.caption_html or (html.escape(msg.caption) if msg.caption else ""),
            "mime_type": msg.document.mime_type or "image/jpeg",
        }
    elif msg.text:
        item = {
            "type": "text",
            "html": msg.text_html or html.escape(msg.text),
        }

    if item:
        items = session(context)
        items.append(item)
        log.info(
            "collected chat=%s type=%s total=%s forwarded=%s",
            update.effective_chat.id if update.effective_chat else None,
            item["type"],
            len(items),
            bool(getattr(msg, "forward_origin", None)),
        )
        return

    log.info(
        "ignored chat=%s message_id=%s type=%s",
        update.effective_chat.id if update.effective_chat else None,
        getattr(msg, "message_id", None),
        getattr(msg, "effective_attachment", None).__class__.__name__
        if getattr(msg, "effective_attachment", None) is not None else "unknown",
    )
    await msg.reply_text(
        "This message type isn't supported yet. Send/forward text or images.",
        reply_markup=KEYBOARD,
    )


def render_html(items: list[dict], asset_names: dict[int, str]) -> str:
    blocks = []
    for i, item in enumerate(items):
        n = i + 1
        if item["type"] == "text":
            blocks.append(
                f'<article class="card"><div class="content" dir="auto">{item["html"]}</div></article>'
            )
        else:
            src = html.escape(asset_names[i], quote=True)
            caption = item.get("caption_html") or ""
            cap = f'<figcaption dir="auto">{caption}</figcaption>' if caption else ""
            blocks.append(
                f'<article class="card"><figure><img src="{src}" loading="lazy" alt="Image {n}">{cap}</figure></article>'
            )

    created = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body = "\n".join(blocks)

    return f"""<!doctype html>
<html lang="fa" dir="auto">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Chat Export</title>
<style>
:root {{
  color-scheme: light dark;
  --panel:#121a2d; --text:#eef3ff; --muted:#93a4c7; --line:rgba(255,255,255,.09);
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:linear-gradient(180deg,#0b1020,#0d1426);
  color:var(--text); font-family:system-ui,-apple-system,"Segoe UI",Roboto,Arial,sans-serif;
}}
.wrap {{ width:min(920px,calc(100% - 28px)); margin:auto; padding:32px 0 64px; }}
.hero,.card {{
  border:1px solid var(--line); background:var(--panel); border-radius:22px;
  box-shadow:0 10px 35px rgba(0,0,0,.18); overflow:hidden;
}}
.hero {{ padding:26px; margin-bottom:16px; }}
h1 {{ margin:0 0 8px; font-size:clamp(28px,6vw,44px); }}
.meta {{ color:var(--muted); font-size:14px; }}
.feed {{ display:grid; gap:14px; }}
.content {{
  padding:20px 22px; white-space:pre-wrap; unicode-bidi:plaintext;
  line-height:1.8; font-size:17px; overflow-wrap:anywhere;
}}
figure {{ margin:0; }}
img {{ display:block; width:100%; height:auto; max-height:82vh; object-fit:contain; background:#080d18; }}
figcaption {{ padding:16px 20px 20px; white-space:pre-wrap; unicode-bidi:plaintext; line-height:1.8; }}
a {{ color:#7dd3fc; }}
footer {{ margin-top:20px; text-align:center; color:var(--muted); font-size:13px; }}
@media (prefers-color-scheme:light) {{
  :root {{ --panel:#fff; --text:#172033; --muted:#64748b; --line:rgba(15,23,42,.09); }}
  body {{ background:linear-gradient(180deg,#f7f9fc,#eef3f8); }}
  img {{ background:#f3f4f6; }}
  a {{ color:#0369a1; }}
}}
</style>
</head>
<body>
<main class="wrap">
<section class="hero">
<h1>Chat Export</h1>
<div class="meta">{len(items)} items · Generated {created}</div>
</section>
<section class="feed">{body}</section>
<footer>Generated by Chat to HTML Bot</footer>
</main>
</body>
</html>"""


async def generate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    items = list(session(context))

    log.info(
        "generate chat=%s count=%s",
        update.effective_chat.id if update.effective_chat else None,
        len(items),
    )

    if not items:
        await msg.reply_text(
            "Nothing collected yet. Send or forward some messages first.",
            reply_markup=KEYBOARD,
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id,
        action=ChatAction.UPLOAD_DOCUMENT,
    )
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

            (root / "index.html").write_text(
                render_html(items, asset_names),
                encoding="utf-8",
            )

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
        try:
            await progress.delete()
        except Exception:
            pass
    except Exception:
        log.exception("generation failed")
        await progress.edit_text(
            "Generation failed. Messages are still in this session; try Generate again."
        )


def main() -> None:
    app = Application.builder().token(TOKEN).concurrent_updates(False).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(~filters.COMMAND, collect))
    log.info("Bot starting with long polling")
    app.run_polling(drop_pending_updates=False)


if __name__ == "__main__":
    main()
