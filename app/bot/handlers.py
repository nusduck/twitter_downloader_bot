import logging
import html
import json
import traceback
import os
import re
import httpx
from io import BytesIO
from typing import List, Dict, Any, Optional, Tuple

from telegram import (
    Update, 
    InputMediaPhoto, 
    InputMediaVideo, 
    InputMediaAnimation,
    BotCommand,
    BotCommandScopeChat,
    constants
)
from telegram.ext import ContextTypes
from telegram.error import BadRequest, Conflict, Forbidden

from app.core.config import config
from app.downloader.twitter import TwitterDownloader, TwitterAPIError

logger = logging.getLogger(__name__)
downloader = TwitterDownloader()

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
        logger.info(f"Access denied to user {update.effective_user.id}")
        await update.message.reply_text(f"Access denied. Your id ({update.effective_user.id}) is not whitelisted.")
        return

    text = update.message.text
    tweet_ids = downloader.extract_tweet_ids(text)
    tag = downloader.extract_tweet_tag(text)

    # Update stats
    if 'stats' not in context.bot_data:
        context.bot_data['stats'] = {'messages_handled': 0, 'media_downloaded': 0}
    context.bot_data['stats']['messages_handled'] += 1

    if not tweet_ids:
        # Only reply if it looks like they tried to send a link but failed or if it's a private chat
        if "twitter.com" in text.lower() or "x.com" in text.lower():
            await update.message.reply_text("No supported tweet link found.")
        return

    for tweet_id in tweet_ids:
        try:
            media_list = await downloader.get_tweet_media(tweet_id)
            if not media_list:
                await update.message.reply_text(f"Tweet {tweet_id} has no media.")
                continue

            await reply_media(update, context, media_list, tag)
            
        except TwitterAPIError as e:
            await update.message.reply_text(f"Error scraping tweet {tweet_id}: {str(e)}")
        except Exception as e:
            logger.error(f"Error handling tweet {tweet_id}: {traceback.format_exc()}")
            try:
                await update.message.reply_text(f"An unexpected error occurred for tweet {tweet_id}.")
            except Exception:
                pass

async def reply_media(update: Update, context: ContextTypes.DEFAULT_TYPE, media_list: List[Dict[str, Any]], tag: str):
    photos = [m for m in media_list if m['type'] == 'image']
    videos = [m for m in media_list if m['type'] == 'video']
    gifs = [m for m in media_list if m['type'] == 'gif']
    
    caption = tag if tag else ""

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
        
        await update.message.reply_media_group(media=media_group)
        context.bot_data['stats']['media_downloaded'] += len(photos)

    # Handle GIFs
    for gif in gifs:
        await update.message.reply_animation(animation=gif['url'], caption=caption)
        context.bot_data['stats']['media_downloaded'] += 1

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
        # Debug log to see what the API returns
        logger.info(f"DEBUG: Processing video data: {video}")

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
            await update.message.reply_video(
                video=video_url,
                caption=caption,
                supports_streaming=True,
                width=width,
                height=height,
            )
            context.bot_data["stats"]["media_downloaded"] += 1
            continue
        except Exception as e:
            logger.warning(
                f"Failed to send video by URL: {e}. Falling back to local download/upload.",
                exc_info=True,
            )

        status_msg = None
        try:
            status_msg = await update.message.reply_text(
                "Telegram API rejected the URL. Downloading locally to re-upload (this might take a while)..."
            )
        except Exception:
            # Non-fatal: we can still try the fallback
            pass

        os.makedirs("data", exist_ok=True)
        base_id = video.get("id_str") or video.get("id") or update.update_id
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
                            "Failed to download thumbnail for fallback upload; sending without thumb",
                            exc_info=True,
                        )
                        temp_thumb_file = None

            # Send via local upload with preserved metadata
            if temp_thumb_file and os.path.exists(temp_thumb_file):
                with open(temp_video_file, "rb") as video_fp, open(temp_thumb_file, "rb") as thumb_fp:
                    try:
                        await update.message.reply_video(
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
                        logger.warning(f"Thumb rejected by Telegram, retrying without thumb: {e}")
                        video_fp.seek(0)
                        await update.message.reply_video(
                            video=video_fp,
                            caption=caption,
                            supports_streaming=True,
                            width=width,
                            height=height,
                        )
                        upload_success = True
            else:
                with open(temp_video_file, "rb") as video_fp:
                    await update.message.reply_video(
                        video=video_fp,
                        caption=caption,
                        supports_streaming=True,
                        width=width,
                        height=height,
                    )
                    upload_success = True

            if upload_success:
                context.bot_data["stats"]["media_downloaded"] += 1
                if status_msg is not None:
                    try:
                        await status_msg.delete()
                    except Exception as e:
                        logger.warning(f"Failed to delete status message: {e}")
                        try:
                            await status_msg.edit_text("✅ Video sent successfully!")
                        except Exception:
                            pass

        except Exception as e:
            # Check if this is a timeout during what was likely a successful upload
            is_timeout = "timeout" in str(e).lower()
            
            if upload_success or is_timeout:
                if is_timeout:
                    logger.warning(f"Upload timed out but might have succeeded: {e}")
                    if status_msg is not None:
                        try:
                            await status_msg.edit_text("⏳ Upload timed out, but the video may still appear shortly...")
                        except Exception:
                            pass
                else:
                    logger.warning(f"Upload was successful but post-upload cleanup failed: {e}")
            else:
                logger.error("Failed to send video after local download/upload", exc_info=True)
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
                    logger.warning(f"Failed to remove temp file: {p}", exc_info=True)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    if isinstance(context.error, Forbidden):
        return
    if isinstance(context.error, Conflict):
        logger.error("Telegram requests conflict")
        return

    logger.error(msg="Exception while handling an update:", exc_info=context.error)

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
            logger.error(f"Failed to send error report to developer: {e}")
