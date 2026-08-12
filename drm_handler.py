import os, re, sys, m3u8, json, time, pytz, asyncio, requests, subprocess, urllib, urllib.parse
import tgcrypto, cloudscraper, random, aiohttp, ffmpeg, shutil, zipfile, aiofiles, yt_dlp

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
from base64 import b64encode, b64decode
from logs import logging
from bs4 import BeautifulSoup
from aiohttp import ClientSession
from subprocess import getstatusoutput
from pytube import YouTube
from aiohttp import web
from pyromod import listen
from pyrogram import Client, filters
from pyrogram.errors import FloodWait, PeerIdInvalid, UserIsBlocked, InputUserDeactivated
from pyrogram.errors.exceptions.bad_request_400 import StickerEmojiInvalid
from pyrogram.types.messages_and_media import message
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, InputMediaPhoto

import saini as helper
import globals
from utils import progress_bar
from vars import API_ID, API_HASH, BOT_TOKEN, OWNER, CREDIT, AUTH_USERS, TOTAL_USERS, cookies_file_path

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
    current_topic = "General Batch"
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
        elif "://" in line:
            current_urls.append(line)

    if current_urls:
        groups.append({"topic": current_topic, "urls": current_urls.copy()})

    if not groups and current_urls:
        groups.append({"topic": "General Batch", "urls": current_urls})

    return groups

# ================================================================
# 🚀 DRM HANDLER – Auto Topic Thread वाला संस्करण
# ================================================================
async def drm_handler(bot: Client, m: Message):
    globals.processing_request = True
    globals.cancel_requested = False

    # Global settings (from /settings)
    caption = globals.caption
    endfilename = globals.endfilename
    thumb = globals.thumb
    CR = globals.CR
    cwtoken = globals.cwtoken
    cptoken = globals.cptoken
    pwtoken = globals.pwtoken
    vidwatermark = globals.vidwatermark
    raw_text2 = globals.raw_text2
    quality = globals.quality
    res = globals.res
    topic = globals.topic

    user_id = m.from_user.id

    # ===== 1. INPUT =====
    if m.document and m.document.file_name.endswith('.txt'):
        x = await m.download()
        file_name, ext = os.path.splitext(os.path.basename(x))
        with open(x, "r") as f:
            content = f.read()
        os.remove(x)

        # Premium check
        if m.chat.id not in AUTH_USERS:
            await bot.send_message(
                m.chat.id,
                f"<blockquote>__**Oopss! You are not a Premium member**__\n"
                f"__**Please Upgrade Your Plan**__\n"
                f"__**Your User id** __- `{m.chat.id}`</blockquote>"
            )
            globals.processing_request = False
            return

        # Ask for Channel/Group ID
        editable = await m.reply_text("**📢 Send Channel/Group ID or /d for current chat**\n\n<blockquote><i>🔹 Make me admin.\n🔸 Send /id in your channel to get ID.\nExample: -100XXXXXXXXXXX</i></blockquote>")
        try:
            input7: Message = await bot.listen(editable.chat.id, timeout=30)
            raw_text7 = input7.text
            await input7.delete(True)
        except asyncio.TimeoutError:
            raw_text7 = '/d'
        await editable.delete()
        channel_id = m.chat.id if raw_text7 == '/d' else int(raw_text7)

        # Parse groups
        groups = parse_txt_to_groups(content)
        if not groups:
            await m.reply_text("❌ No valid URLs found.")
            globals.processing_request = False
            return

        # ===== 2. PROCESS EACH GROUP =====
        total_failed = 0
        total_success = 0

        for group_idx, group in enumerate(groups):
            topic_name = group["topic"]
            urls = group["urls"]

            # --- Create Topic (Thread) ---
            try:
                topic_obj = await bot.create_forum_topic(chat_id=channel_id, name=topic_name)
                thread_id = topic_obj.id
            except Exception as e:
                await m.reply_text(f"⚠️ Topic '{topic_name}' not created: {e}\nFalling back to default thread.")
                thread_id = None

            # --- Send Batch Start ---
            await bot.send_message(
                chat_id=channel_id,
                text=f"📂 **Batch:** {topic_name}\n🔄 Total: {len(urls)} links",
                message_thread_id=thread_id
            )

            # --- Process URLs in this group ---
            count = 1
            for url_line in urls:
                if globals.cancel_requested:
                    await m.reply_text("⏹️ Stopped by user.")
                    globals.processing_request = False
                    globals.cancel_requested = False
                    return

                # 🔹 Parse URL and extract title
                Vxy = url_line.split("://", 1)[1] if "://" in url_line else url_line
                Vxy = Vxy.replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","")
                url = "https://" + Vxy
                link0 = "https://" + Vxy

                # Title extraction
                raw_title = url_line.split(":", 1)[0] if ":" in url_line else f"Video_{count}"
                name1 = raw_title.replace("(", "[").replace(")", "]").replace("_", "").replace("\t", "").replace(":", "").replace("/", "").replace("+", "").replace("#", "").replace("|", "").replace("@", "").replace("*", "").replace(".", "").replace("https", "").replace("http", "").strip()

                if topic == "/yes":
                    t_match = re.search(r"[\(\[]([^\)\]]+)[\)\]]", raw_title)
                    if t_match:
                        t_name = t_match.group(1).strip()
                        v_name = re.sub(r"^[\(\[][^\)\]]+[\)\]]\s*", "", raw_title)
                        v_name = re.sub(r"[\(\[][^\)\]]+[\)\]]", "", v_name)
                        v_name = re.sub(r":.*", "", v_name).strip()
                    else:
                        t_name = "Untitled"
                        v_name = re.sub(r":.*", "", raw_title).strip()
                else:
                    t_name = None
                    v_name = name1

                display_title = v_name if topic == "/yes" else name1

                if endfilename == "/d":
                    name = f'{str(count).zfill(3)}) {name1[:60]}'
                    namef = f'{name1[:60]}'
                else:
                    name = f'{str(count).zfill(3)}) {name1[:60]} {endfilename}'
                    namef = f'{name1[:60]} {endfilename}'

                # 🔹 Build Caption (new format)
                def build_caption(title, ext, idx, batch, topic_text, credit):
                    lines = [f"Index: {idx}", f"Title: {title}.{ext}"]
                    if topic_text:
                        lines.append(f"Topic: {topic_text}")
                    lines.append(f"Batch: {batch}")
                    lines.append(f"Extracted By: {credit}")
                    return "\n\n".join(lines)

                cc   = build_caption(display_title, "mp4", count, topic_name, t_name, CR)
                cc1  = build_caption(display_title, "pdf", count, topic_name, t_name, CR)
                ccimg = build_caption(display_title, "jpg", count, topic_name, t_name, CR)
                ccm  = build_caption(display_title, "mp3", count, topic_name, t_name, CR)

                # 🔹 Process URL based on type
                try:
                    # ---- VisionIAS ----
                    if "visionias" in url:
                        async with ClientSession() as session:
                            async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                                text = await resp.text()
                                url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

                    # ---- Classplus DRM ----
                    if "classplusapp.com/drm/" in url or "cpvod.testbook.com" in url:
                        url = url.replace("https://cpvod.testbook.com/","https://media-cdn.classplusapp.com/drm/")
                        try:
                            api_url = f"https://sainibotsdrm.vercel.app/api?url={url}&token={cptoken}&auth=4443683167"
                            response = requests.get(api_url)
                            data = response.json()
                            if data.get("keys") and "url" in data:
                                mpd = data.get('url')
                                keys = data.get('keys')
                                url = mpd
                                keys_string = " ".join([f"--key {key}" for key in keys])
                            else:
                                raise Exception(f"{data.get('error', 'Token expired')}")
                        except Exception as e:
                            await bot.send_message(channel_id, f'⚠️ Failed: {name1}\n{url}\nError: {e}', message_thread_id=thread_id)
                            count += 1
                            total_failed += 1
                            continue

                    # ---- YouTube ----
                    if "youtu" in url:
                        ytf = f"bv*[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[height<=?{raw_text2}]"
                        cmd = f'yt-dlp --cookies youtube_cookies.txt -f "{ytf}" "{url}" -o "{name}.mp4"'
                    else:
                        ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"
                        cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

                    # ---- PDF ----
                    if "pdf" in url:
                        if "cwmediabkt99" in url:
                            scraper = cloudscraper.create_scraper()
                            resp = scraper.get(url)
                            if resp.status_code == 200:
                                with open(f'{namef}.pdf', 'wb') as f:
                                    f.write(resp.content)
                                await bot.send_document(channel_id, f'{namef}.pdf', caption=cc1, message_thread_id=thread_id)
                                os.remove(f'{namef}.pdf')
                            else:
                                raise Exception(f"PDF download failed: {resp.status_code}")
                        else:
                            cmd_pdf = f'yt-dlp -o "{namef}.pdf" "{url}" -R 25 --fragment-retries 25'
                            os.system(cmd_pdf)
                            await bot.send_document(channel_id, f'{namef}.pdf', caption=cc1, message_thread_id=thread_id)
                            os.remove(f'{namef}.pdf')
                        count += 1
                        total_success += 1
                        continue

                    # ---- Image ----
                    if any(ext in url for ext in [".jpg", ".jpeg", ".png"]):
                        ext = url.split('.')[-1]
                        cmd_img = f'yt-dlp -o "{namef}.{ext}" "{url}"'
                        os.system(cmd_img)
                        await bot.send_photo(channel_id, f'{namef}.{ext}', caption=ccimg, message_thread_id=thread_id)
                        os.remove(f'{namef}.{ext}')
                        count += 1
                        total_success += 1
                        continue

                    # ---- DRM MPD ----
                    if 'drmcdni' in url or 'drm/wv' in url or 'drm/common' in url:
                        prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}", message_thread_id=thread_id)
                        path = f"./downloads/{m.chat.id}"
                        res_file = await helper.decrypt_and_merge_video(url, keys_string, path, name, raw_text2)
                        await prog.delete()
                        await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, thread_id)
                        count += 1
                        total_success += 1
                        continue

                    # ---- Encrypted APPX ----
                    if 'encrypted.m' in url:
                        appxkey = url.split('*')[1]
                        url = url.split('*')[0]
                        prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}", message_thread_id=thread_id)
                        res_file = await helper.download_and_decrypt_video(url, cmd, name, appxkey)
                        await prog.delete()
                        await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, thread_id)
                        count += 1
                        total_success += 1
                        continue

                    # ---- Normal Video ----
                    prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}", message_thread_id=thread_id)
                    res_file = await helper.download_video(url, cmd, name)
                    await prog.delete()
                    await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, thread_id)
                    count += 1
                    total_success += 1

                except Exception as e:
                    await bot.send_message(channel_id, f'❌ Failed: {name1}\n{url}\nError: {e}', message_thread_id=thread_id)
                    count += 1
                    total_failed += 1

            # --- Group Completion ---
            await bot.send_message(
                chat_id=channel_id,
                text=f"✅ **{topic_name}** complete!",
                message_thread_id=thread_id
            )

        # ===== 3. FINAL SUMMARY =====
        await bot.send_message(
            chat_id=channel_id,
            text=f"🏁 **All batches processed.**\n✅ Success: {total_success}\n❌ Failed: {total_failed}",
            message_thread_id=None
        )
        await m.reply_text("✅ All tasks completed successfully!")

    else:
        # ----- SINGLE LINK (no .txt) -----
        await m.reply_text("⚠️ Please send a .txt file with proper format.")
        globals.processing_request = False
        return

    globals.processing_request = False

# ================================================================
def register_drm_handlers(bot):
    @bot.on_message(filters.private & (filters.document | filters.text))
    async def call_drm_handler(bot: Client, m: Message):
        await drm_handler(bot, m)
