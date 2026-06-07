import logging
import html
import traceback
import os
import re
import time
import httpx
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple

from telegram import (
    Update, 
    InputMediaPhoto, 
    constants
)
from telegram.ext import ContextTypes
from telegram.error import BadRequest, Conflict, Forbidden

from app.core.config import config
from app.downloader.twitter import TwitterDownloader, TwitterAPIError

logger = logging.getLogger(__name__)
downloader = TwitterDownloader()

def ensure_stats(bot_data: Dict[str, Any]) -> Dict[str, int]:
    if "stats" not in bot_data:
        bot_data["stats"] = {"messages_handled": 0, "media_downloaded": 0}
    return bot_data["stats"]

class MessageReplyTarget:
    def __init__(self, message):
        self.message = message
        self.log_context = "chat_id=%s message_id=%s" % (
            message.chat_id,
            message.message_id,
        )

    async def reply_text(self, *args, **kwargs):
        return await self.message.reply_text(*args, **kwargs)

    async def reply_media_group(self, *args, **kwargs):
        return await self.message.reply_media_group(*args, **kwargs)

    async def reply_animation(self, *args, **kwargs):
        return await self.message.reply_animation(*args, **kwargs)

    async def reply_video(self, *args, **kwargs):
        return await self.message.reply_video(*args, **kwargs)

class ChatReplyTarget:
    def __init__(self, bot, chat_id: int):
        self.bot = bot
        self.chat_id = chat_id
        self.log_context = f"chat_id={chat_id}"

    async def reply_text(self, text, *args, **kwargs):
        return await self.bot.send_message(chat_id=self.chat_id, text=text, *args, **kwargs)

    async def reply_media_group(self, media, *args, **kwargs):
        return await self.bot.send_media_group(chat_id=self.chat_id, media=media, *args, **kwargs)

    async def reply_animation(self, animation, *args, **kwargs):
        return await self.bot.send_animation(
            chat_id=self.chat_id,
            animation=animation,
            *args,
            **kwargs,
        )

    async def reply_video(self, video, *args, **kwargs):
        return await self.bot.send_video(
            chat_id=self.chat_id,
            video=video,
            *args,
            **kwargs,
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    await update.message.reply_markdown_v2(
        fr"Hi {user.mention_markdown_v2()}\!"
        "\nSend tweet link here and I will download media in the best available quality for you\."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    await update.message.reply_text('Send tweet link here and I will download media in the best available quality for you.')

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send stats when the command /stats is issued."""
    stats = context.bot_data.get('stats', {'messages_handled': 0, 'media_downloaded': 0})
    await update.message.reply_markdown_v2(
        f"*Bot stats:*\n"
        f"Messages handled: *{stats.get('messages_handled')}*\n"
        f"Media downloaded: *{stats.get('media_downloaded')}*"
    )

async def reset_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset stats when the command /resetstats is issued."""
    context.bot_data['stats'] = {'messages_handled': 0, 'media_downloaded': 0}
    await update.message.reply_text("Bot stats have been reset")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the user message."""
    if not update.message or not update.message.text:
        return

    # Check privacy
    if config.IS_BOT_PRIVATE and update.effective_user.id != config.DEVELOPER_ID:
        logger.info(
            "Access denied user_id=%s chat_id=%s",
            update.effective_user.id,
            update.effective_chat.id if update.effective_chat else None,
        )
        await update.message.reply_text(f"Access denied. Your id ({update.effective_user.id}) is not whitelisted.")
        return

    await process_tweet_text(
        update.message.text,
        MessageReplyTarget(update.message),
        context.bot_data,
        temp_id=str(update.update_id),
    )

async def process_tweet_text(
    text: str,
    target,
    bot_data: Dict[str, Any],
    temp_id: Optional[str] = None,
    caption_url: Optional[str] = None,
) -> int:
    """Process one text payload containing one or more X/Twitter URLs."""
    tweet_ids = downloader.extract_tweet_ids(text)
    tag = downloader.extract_tweet_tag(text)
    target_context = getattr(target, "log_context", "target=unknown")

    stats = ensure_stats(bot_data)
    stats["messages_handled"] += 1

    if not tweet_ids:
        lower_text = text.lower()
        # Only reply if it looks like they tried to send a link but failed or if it's a private chat
        if "twitter.com" in lower_text or "x.com" in lower_text:
            logger.info("No supported tweet link found %s", target_context)
            await target.reply_text("No supported tweet link found.")
        else:
            logger.debug("Ignored text without tweet link %s", target_context)
        return 0

    logger.info("Processing tweet request count=%s tweet_ids=%s %s", len(tweet_ids), ",".join(tweet_ids), target_context)
    processed = 0
    for tweet_id in tweet_ids:
        try:
            media_list = await downloader.get_tweet_media(tweet_id)
            if not media_list:
                logger.info("Tweet has no media tweet_id=%s %s", tweet_id, target_context)
                await target.reply_text(f"Tweet {tweet_id} has no media.")
                continue

            logger.info(
                "Tweet media resolved tweet_id=%s media_count=%s %s",
                tweet_id,
                len(media_list),
                target_context,
            )
            await reply_media(
                target,
                bot_data,
                media_list,
                tag,
                temp_id=temp_id or f"shortcut_{tweet_id}_{int(time.time())}",
                caption_url=caption_url,
            )
            processed += 1
            
        except TwitterAPIError as e:
            logger.warning("Tweet scrape failed tweet_id=%s error=%s %s", tweet_id, e, target_context)
            await target.reply_text(f"Error scraping tweet {tweet_id}: {str(e)}")
        except Exception:
            logger.exception("Unexpected tweet handling error tweet_id=%s %s", tweet_id, target_context)
            try:
                await target.reply_text(f"An unexpected error occurred for tweet {tweet_id}.")
            except Exception:
                pass
    return processed

async def reply_media(
    target,
    bot_data: Dict[str, Any],
    media_list: List[Dict[str, Any]],
    tag: str,
    temp_id: str,
    caption_url: Optional[str] = None,
):
    stats = ensure_stats(bot_data)
    photos = [m for m in media_list if m['type'] == 'image']
    videos = [m for m in media_list if m['type'] == 'video']
    gifs = [m for m in media_list if m['type'] == 'gif']
    
    caption_parts = []
    if caption_url:
        caption_parts.append(caption_url)
    if tag:
        caption_parts.append(tag)
    caption = "\n".join(caption_parts)

    # Handle Photos
    if photos:
        media_group = []
        for i, photo in enumerate(photos):
            # Try to get original size
            photo_url = photo['url']
            if 'format=' not in photo_url:
                if '?' in photo_url:
                    photo_url += "&name=orig"
                else:
                    photo_url += "?name=orig"
            
            media_group.append(InputMediaPhoto(media=photo_url, caption=caption if i == 0 else ""))
        
        await target.reply_media_group(media=media_group)
        stats['media_downloaded'] += len(photos)

    # Handle GIFs
    for gif in gifs:
        await target.reply_animation(animation=gif['url'], caption=caption)
        stats['media_downloaded'] += 1

    # Handle Videos
    def _safe_int(v):
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    def _extract_resolution_from_url(url: str) -> Tuple[Optional[int], Optional[int]]:
        """Try to extract WxH from URL patterns like 1920x1080."""
        if not url:
            return None, None
        m = re.search(r"(?P<w>\d{3,4})x(?P<h>\d{3,4})", url)
        if not m:
            return None, None
        return _safe_int(m.group("w")), _safe_int(m.group("h"))

    for video in videos:
        logger.debug("Processing video media data=%s", video)

        video_url = video["url"]
        
        # vxtwitter uses 'size' dictionary for width/height
        size_data = video.get("size", {})
        width = _safe_int(size_data.get("width"))
        height = _safe_int(size_data.get("height"))
        
        # Fallback to direct keys if not in size dict
        if width is None: width = _safe_int(video.get("width"))
        if height is None: height = _safe_int(video.get("height"))
        
        thumbnail_url = (
            video.get("thumbnail_url")
            or video.get("thumbnail")
            or video.get("preview_image_url")
            or video.get("poster")
        )

        # If still missing, try to derive resolution from the URL itself
        if width is None or height is None:
            uw, uh = _extract_resolution_from_url(video_url)
            if width is None:
                width = uw
            if height is None:
                height = uh

        # Use Local Bot API to handle up to 2GB.
        # We can just pass the URL, and if the Local Bot API Server is configured,
        # it will handle the download/upload.
        try:
            await target.reply_video(
                video=video_url,
                caption=caption,
                supports_streaming=True,
                width=width,
                height=height,
            )
            stats["media_downloaded"] += 1
            logger.info("Video sent by URL width=%s height=%s", width, height)
            continue
        except Exception as e:
            logger.warning(
                "Telegram rejected video URL, falling back to local upload error=%s",
                e,
            )

        status_msg = None
        try:
            status_msg = await target.reply_text(
                "Telegram API rejected the URL. Downloading locally to re-upload (this might take a while)..."
            )
        except Exception:
            # Non-fatal: we can still try the fallback
            pass

        os.makedirs("data", exist_ok=True)
        base_id = video.get("id_str") or video.get("id") or temp_id
        base_id = re.sub(r"[^a-zA-Z0-9_.-]", "_", str(base_id))
        temp_video_file = os.path.join("data", f"temp_video_{base_id}.mp4")
        temp_thumb_file = os.path.join("data", f"temp_thumb_{base_id}.jpg") if thumbnail_url else None
        
        upload_success = False
        try:
            timeout = httpx.Timeout(1200.0)
            async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
                # Download video
                async with client.stream("GET", video_url) as response:
                    response.raise_for_status()
                    with open(temp_video_file, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            f.write(chunk)

                # Download thumbnail (Telegram doesn't accept thumb as URL for upload)
                if thumbnail_url and temp_thumb_file:
                    try:
                        r = await client.get(thumbnail_url)
                        r.raise_for_status()
                        with open(temp_thumb_file, "wb") as tf:
                            tf.write(r.content)
                    except Exception:
                        logger.warning(
                            "Thumbnail download failed, sending video without thumbnail",
                            exc_info=True,
                        )
                        temp_thumb_file = None

            # Send via local upload with preserved metadata
            if temp_thumb_file and os.path.exists(temp_thumb_file):
                with open(temp_video_file, "rb") as video_fp, open(temp_thumb_file, "rb") as thumb_fp:
                    try:
                        await target.reply_video(
                            video=video_fp,
                            caption=caption,
                            supports_streaming=True,
                            width=width,
                            height=height,
                            thumbnail=thumb_fp,
                        )
                        upload_success = True
                    except BadRequest as e:
                        # Telegram is picky about thumb (format/size/dimensions). If thumb fails,
                        # retry without thumb rather than failing the whole send.
                        logger.warning("Telegram rejected thumbnail, retrying without it error=%s", e)
                        video_fp.seek(0)
                        await target.reply_video(
                            video=video_fp,
                            caption=caption,
                            supports_streaming=True,
                            width=width,
                            height=height,
                        )
                        upload_success = True
            else:
                with open(temp_video_file, "rb") as video_fp:
                    await target.reply_video(
                        video=video_fp,
                        caption=caption,
                        supports_streaming=True,
                        width=width,
                        height=height,
                    )
                    upload_success = True

            if upload_success:
                stats["media_downloaded"] += 1
                if status_msg is not None:
                    try:
                        await status_msg.delete()
                    except Exception as e:
                        logger.warning("Failed to delete upload status message error=%s", e)
                        try:
                            await status_msg.edit_text("✅ Video sent successfully!")
                        except Exception:
                            pass

        except Exception as e:
            # Check if this is a timeout during what was likely a successful upload
            is_timeout = "timeout" in str(e).lower()
            
            if upload_success or is_timeout:
                if is_timeout:
                    logger.warning("Video upload timed out after send attempt error=%s", e)
                    if status_msg is not None:
                        try:
                            await status_msg.edit_text("⏳ Upload timed out, but the video may still appear shortly...")
                        except Exception:
                            pass
                else:
                    logger.warning("Video upload completed but cleanup failed error=%s", e)
            else:
                logger.exception("Local video upload failed")
                if status_msg is not None:
                    try:
                        await status_msg.edit_text(f"❌ Failed to send video. Direct link: {video_url}")
                    except Exception:
                        pass
        finally:
            # Clean up temp files
            for p in (temp_video_file, temp_thumb_file):
                if not p:
                    continue
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except Exception:
                    logger.warning("Failed to remove temp file path=%s", p, exc_info=True)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    if isinstance(context.error, Forbidden):
        return
    if isinstance(context.error, Conflict):
        logger.error("Telegram update conflict")
        return

    logger.error(
        "Unhandled Telegram update error",
        exc_info=(type(context.error), context.error, context.error.__traceback__),
    )

    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)

    if config.DEVELOPER_ID:
        try:
            # Prepare error report as file if too long
            message = f"Error: {str(context.error)}\n\n{tb_string}"
            if len(message) > 4000:
                document = BytesIO(message.encode())
                document.name = "error_report.txt"
                await context.bot.send_document(
                    chat_id=config.DEVELOPER_ID, 
                    document=document, 
                    caption="#error_report"
                )
            else:
                await context.bot.send_message(
                    chat_id=config.DEVELOPER_ID, 
                    text=f"#error_report\n<pre>{html.escape(message)}</pre>",
                    parse_mode=constants.ParseMode.HTML
                )
        except Exception as e:
            logger.error("Failed to send error report to developer error=%s", e)
