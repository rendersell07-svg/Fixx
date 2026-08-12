import os
import requests
import subprocess
import asyncio
import yt_dlp
from pytube import YouTube
from pyromod import listen
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from vars import CREDIT, cookies_file_path, AUTH_USERS
import globals

# ================================================================
# 🧩 PARSER – .txt को Groups (Topic + URLs) में बाँटता है
# ================================================================
def parse_txt_to_groups(content):
    """
    Parses the content of a .txt file.
    Returns a list of dict: [{"topic": "Name", "urls": ["url1", "url2"]}]
    """
    lines = content.strip().split("\n")
    groups = []
    current_topic = "YouTube Playlist"
    current_urls = []

    for line in lines:
        line = line.strip()
        if not line:  # blank line → group break
            if current_urls:
                groups.append({"topic": current_topic, "urls": current_urls.copy()})
                current_urls = []
            continue

        if line.startswith("#"):
            if current_urls:
                groups.append({"topic": current_topic, "urls": current_urls.copy()})
                current_urls = []
            current_topic = line.lstrip("# ").strip()
        elif "://" in line and ("youtube.com" in line or "youtu.be" in line):
            current_urls.append(line)

    if current_urls:
        groups.append({"topic": current_topic, "urls": current_urls.copy()})

    if not groups and current_urls:
        groups.append({"topic": "YouTube Playlist", "urls": current_urls})

    return groups

# ================================================================
# YOUTUBE HANDLER – Auto Topic Thread
# ================================================================
def register_youtube_handlers(bot):

    # ===== /cookies (unchanged) =====
    @bot.on_message(filters.command("cookies") & filters.private)
    async def cookies_handler(client: Client, m: Message):
        editable = await m.reply_text("**Please upload the YouTube Cookies file (.txt format).**")
        try:
            input_message: Message = await client.listen(m.chat.id)
            if not input_message.document or not input_message.document.file_name.endswith(".txt"):
                await m.reply_text("Invalid file type. Please upload a .txt file.")
                return
            downloaded_path = await input_message.download()
            with open(downloaded_path, "r") as uploaded_file:
                cookies_content = uploaded_file.read()
            with open(cookies_file_path, "w") as target_file:
                target_file.write(cookies_content)
            await editable.delete()
            await input_message.delete()
            await m.reply_text("✅ Cookies updated successfully.\n📂 Saved in `youtube_cookies.txt`.")
        except Exception as e:
            await m.reply_text(f"__**Failed Reason**__\n<blockquote>{str(e)}</blockquote>")

    # ===== /getcookies (unchanged) =====
    @bot.on_message(filters.command("getcookies") & filters.private)
    async def getcookies_handler(client: Client, m: Message):
        try:
            await client.send_document(chat_id=m.chat.id, document=cookies_file_path, caption="Here is the `youtube_cookies.txt` file.")
        except Exception as e:
            await m.reply_text(f"⚠️ An error occurred: {str(e)}")

    # ===== /ytm (with Auto Topic Thread) =====
    @bot.on_message(filters.command(["ytm"]))
    async def ytm_handler(bot: Client, m: Message):
        globals.processing_request = True
        globals.cancel_requested = False

        editable = await m.reply_text("**Input Type**\n\n<blockquote><b>01 • Send .txt file with YouTube links\n02 • Send Single or multiple YouTube links</b></blockquote>")
        input: Message = await bot.listen(editable.chat.id)

        # ----- CASE 1: .txt file -----
        if input.document and input.document.file_name.endswith(".txt"):
            x = await input.download()
            with open(x, "r") as f:
                content = f.read()
            os.remove(x)

            # Parse groups
            groups = parse_txt_to_groups(content)
            if not groups:
                await m.reply_text("❌ No valid YouTube links found.")
                globals.processing_request = False
                return

            # Ask for Channel/Group ID
            await editable.edit("**📢 Send Channel/Group ID or /d for current chat**")
            try:
                input7: Message = await bot.listen(editable.chat.id, timeout=20)
                raw_text7 = input7.text
                await input7.delete(True)
            except asyncio.TimeoutError:
                raw_text7 = '/d'
            await editable.delete()

            channel_id = m.chat.id if raw_text7 == '/d' else int(raw_text7)

            # Process each group
            for group in groups:
                topic_name = group["topic"]
                urls = group["urls"]

                # Create Topic
                try:
                    topic_obj = await bot.create_forum_topic(chat_id=channel_id, name=topic_name)
                    thread_id = topic_obj.id
                except Exception as e:
                    await m.reply_text(f"⚠️ Topic '{topic_name}' not created: {e}\nUsing default thread.")
                    thread_id = None

                # Batch start
                await bot.send_message(
                    chat_id=channel_id,
                    text=f"🎵 **Playlist:** {topic_name}\n🔄 Total: {len(urls)} songs",
                    message_thread_id=thread_id
                )

                count = 1
                for url_line in urls:
                    if globals.cancel_requested:
                        await m.reply_text("⏹️ Stopped.")
                        globals.processing_request = False
                        globals.cancel_requested = False
                        return

                    # Extract URL
                    if "://" in url_line:
                        url = url_line.split("://", 1)[1]
                        url = "https://" + url
                    else:
                        url = url_line

                    # Get title from YouTube
                    try:
                        oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                        response = requests.get(oembed_url)
                        audio_title = response.json().get('title', 'YouTube Video')
                        audio_title = audio_title.replace("_", " ")
                        name1 = f'{audio_title[:60]} {CREDIT}'
                        name = f'{audio_title[:60]}'
                    except:
                        name1 = f'Song {count}'
                        name = f'Song {count}'

                    # Download MP3
                    prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}", message_thread_id=thread_id)
                    cmd = f'yt-dlp -x --audio-format mp3 --cookies {cookies_file_path} "{url}" -o "{name}.mp3"'
                    os.system(cmd)

                    if os.path.exists(f'{name}.mp3'):
                        await prog.delete()
                        # Caption
                        mp3_caption = (
                            f"Index: {count}\n\n"
                            f"Title: {name1}.mp3\n\n"
                            f"Batch: {topic_name}\n\n"
                            f"Extracted By: {CREDIT}"
                        )
                        await bot.send_document(
                            chat_id=channel_id,
                            document=f'{name}.mp3',
                            caption=mp3_caption,
                            message_thread_id=thread_id
                        )
                        os.remove(f'{name}.mp3')
                    else:
                        await prog.delete()
                        await bot.send_message(channel_id, f'❌ Failed: {name1}', message_thread_id=thread_id)

                    count += 1

                # Group completion
                await bot.send_message(
                    chat_id=channel_id,
                    text=f"✅ **{topic_name}** complete!",
                    message_thread_id=thread_id
                )

            await m.reply_text("✅ All songs downloaded successfully!")

        # ----- CASE 2: Single or multiple links (no .txt) -----
        elif input.text:
            content = input.text.strip().split("\n")
            urls = []
            for line in content:
                if "://" in line and ("youtube.com" in line or "youtu.be" in line):
                    urls.append(line)
            await editable.delete()
            await input.delete(True)

            if not urls:
                await m.reply_text("❌ No valid YouTube links found.")
                globals.processing_request = False
                return

            # Single topic (no # headers)
            topic_name = "YouTube Links"
            channel_id = m.chat.id
            thread_id = None  # send in main chat

            count = 1
            for url_line in urls:
                if globals.cancel_requested:
                    await m.reply_text("⏹️ Stopped.")
                    globals.processing_request = False
                    globals.cancel_requested = False
                    return

                # Extract URL
                if "://" in url_line:
                    url = url_line.split("://", 1)[1]
                    url = "https://" + url
                else:
                    url = url_line

                try:
                    oembed_url = f"https://www.youtube.com/oembed?url={url}&format=json"
                    response = requests.get(oembed_url)
                    audio_title = response.json().get('title', 'YouTube Video')
                    audio_title = audio_title.replace("_", " ")
                    name1 = f'{audio_title[:60]} {CREDIT}'
                    name = f'{audio_title[:60]}'
                except:
                    name1 = f'Song {count}'
                    name = f'Song {count}'

                prog = await m.reply_text(f"⏳ Downloading: {name1}")
                cmd = f'yt-dlp -x --audio-format mp3 --cookies {cookies_file_path} "{url}" -o "{name}.mp3"'
                os.system(cmd)

                if os.path.exists(f'{name}.mp3'):
                    await prog.delete()
                    mp3_caption = (
                        f"Index: {count}\n\n"
                        f"Title: {name1}.mp3\n\n"
                        f"Batch: {topic_name}\n\n"
                        f"Extracted By: {CREDIT}"
                    )
                    await bot.send_document(
                        chat_id=m.chat.id,
                        document=f'{name}.mp3',
                        caption=mp3_caption
                    )
                    os.remove(f'{name}.mp3')
                else:
                    await prog.delete()
                    await m.reply_text(f'❌ Failed: {name1}')
                count += 1

            await m.reply_text("✅ All songs downloaded successfully!")

        else:
            await m.reply_text("**Invalid input. Send either a .txt file or YouTube links.**")
            globals.processing_request = False
            return

        globals.processing_request = False
