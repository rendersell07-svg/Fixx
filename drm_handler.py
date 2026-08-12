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
# 🔹 TRY TO IMPORT RAW API FOR FORUM TOPICS (if available)
# ================================================================
try:
    from pyrogram.raw.functions.messages import CreateForumTopic
    from pyrogram.raw.types import InputPeerChannel
    RAW_TOPIC_AVAILABLE = True
except ImportError:
    RAW_TOPIC_AVAILABLE = False
    print("⚠️ Raw CreateForumTopic not available. Forum topics will be disabled.")

# ================================================================
# 🧵 SAFE FORUM TOPIC CREATOR (works with or without raw API)
# ================================================================
async def create_forum_topic(client: Client, chat_id: int, name: str):
    """
    Creates a forum topic using the best available method.
    Returns thread_id (int) or None if failed.
    """
    # 1) Try high-level method (Pyrogram v2+)
    if hasattr(client, 'create_forum_topic'):
        try:
            topic = await client.create_forum_topic(chat_id, name)
            return topic.id
        except Exception as e:
            print(f"High-level create_forum_topic failed: {e}")

    # 2) Try raw API if available
    if RAW_TOPIC_AVAILABLE:
        try:
            peer = await client.resolve_peer(chat_id)
            request = CreateForumTopic(
                peer=peer,
                title=name,
                icon_color=0
            )
            result = await client.invoke(request)
            # Extract message id (which is the thread id)
            for update in result.updates:
                if hasattr(update, 'message') and update.message:
                    return update.message.id
            # fallback: try to get from result.messages?
            if hasattr(result, 'messages') and result.messages:
                return result.messages[0].id
        except Exception as e:
            print(f"Raw CreateForumTopic failed: {e}")

    # 3) If all fail, return None
    print(f"❌ Could not create forum topic '{name}'. Falling back to default thread.")
    return None

# ================================================================
# 🛠️ HELPER TO CONDITIONALLY PASS message_thread_id (for older pyrogram)
# ================================================================
def _get_send_kwargs(thread_id):
    """Returns kwargs for send_* methods only if thread_id is not None and pyrogram version supports it."""
    kwargs = {}
    if thread_id is not None:
        try:
            import pyrogram
            # Check if version is at least 2.0.0 (which supports message_thread_id)
            if hasattr(pyrogram, "__version__"):
                ver = pyrogram.__version__
                if ver and ver >= "2.0.0":
                    kwargs["message_thread_id"] = thread_id
            # If version check fails, we assume it's old and omit the param
        except:
            pass
    return kwargs

# ================================================================
# 🧩 PARSER – .txt को Groups (Topic + URLs) में बाँटता है
# ================================================================
def parse_txt_to_groups(content):
    lines = content.strip().split("\n")
    groups = []
    current_topic = "General Batch"
    current_urls = []

    for line in lines:
        line = line.strip()
        if not line:
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
# 🚀 DRM HANDLER – Auto Topic Thread (with safe fallback)
# ================================================================
async def drm_handler(bot: Client, m: Message):
    globals.processing_request = True
    globals.cancel_requested = False

    # Global settings
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

    # ============================================================
    # CASE 1: INPUT IS A .txt FILE
    # ============================================================
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

        # ===== PROCESS EACH GROUP =====
        total_failed = 0
        total_success = 0

        for group_idx, group in enumerate(groups):
            topic_name = group["topic"]
            urls = group["urls"]

            # --- Create Topic (Thread) using safe function ---
            thread_id = await create_forum_topic(bot, channel_id, topic_name)
            if thread_id is None:
                await m.reply_text(f"⚠️ Topic '{topic_name}' not created.\nFalling back to default thread.")
                # thread_id stays None

            # --- Send Batch Start ---
            await bot.send_message(
                chat_id=channel_id,
                text=f"📂 **Batch:** {topic_name}\n🔄 Total: {len(urls)} links",
                **_get_send_kwargs(thread_id)
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
                            await bot.send_message(channel_id, f'⚠️ Failed: {name1}\n{url}\nError: {e}', **_get_send_kwargs(thread_id))
                            count += 1
                            total_failed += 1
                            continue

                    # ---- tencdn / videos / media-cdn ----
                    if "tencdn.classplusapp" in url:
                        headers = {'host': 'api.classplusapp.com', 'x-access-token': f'{cptoken}', 'accept-language': 'EN', 'api-version': '18', 'app-version': '1.4.73.2', 'build-number': '35', 'connection': 'Keep-Alive', 'content-type': 'application/json', 'device-details': 'Xiaomi_Redmi 7_SDK-32', 'device-id': 'c28d3cb16bbdac01', 'region': 'IN', 'user-agent': 'Mobile-Android', 'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c', 'accept-encoding': 'gzip'}
                        params = {"url": f"{url}"}
                        response = requests.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                        url = response.json()['url']

                    if 'videos.classplusapp' in url:
                        url = requests.get(f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}', headers={'x-access-token': f'{cptoken}'}).json()['url']

                    if 'media-cdn.classplusapp.com' in url or 'media-cdn-alisg.classplusapp.com' in url or 'media-cdn-a.classplusapp.com' in url:
                        headers = {'host': 'api.classplusapp.com', 'x-access-token': f'{cptoken}', 'accept-language': 'EN', 'api-version': '18', 'app-version': '1.4.73.2', 'build-number': '35', 'connection': 'Keep-Alive', 'content-type': 'application/json', 'device-details': 'Xiaomi_Redmi 7_SDK-32', 'device-id': 'c28d3cb16bbdac01', 'region': 'IN', 'user-agent': 'Mobile-Android', 'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c', 'accept-encoding': 'gzip'}
                        params = {"url": f"{url}"}
                        response = requests.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                        url = response.json()['url']

                    # ---- Brightcove ----
                    if "edge.api.brightcove.com" in url:
                        bcov = f'bcov_auth={cwtoken}'
                        url = url.split("bcov_auth")[0]+bcov

                    # ---- PW ----
                    if "childId" in url and "parentId" in url:
                        url = f"https://anonymouspwplayer-0e5a3f512dec.herokuapp.com/pw?url={url}&token={pwtoken}"

                    # ---- APPX ----
                    if 'encrypted.m' in url:
                        appxkey = url.split('*')[1]
                        url = url.split('*')[0]

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
                                await bot.send_document(channel_id, f'{namef}.pdf', caption=cc1, **_get_send_kwargs(thread_id))
                                os.remove(f'{namef}.pdf')
                            else:
                                raise Exception(f"PDF download failed: {resp.status_code}")
                        else:
                            cmd_pdf = f'yt-dlp -o "{namef}.pdf" "{url}" -R 25 --fragment-retries 25'
                            os.system(cmd_pdf)
                            await bot.send_document(channel_id, f'{namef}.pdf', caption=cc1, **_get_send_kwargs(thread_id))
                            os.remove(f'{namef}.pdf')
                        count += 1
                        total_success += 1
                        continue

                    # ---- Image ----
                    if any(ext in url for ext in [".jpg", ".jpeg", ".png"]):
                        ext = url.split('.')[-1]
                        cmd_img = f'yt-dlp -o "{namef}.{ext}" "{url}"'
                        os.system(cmd_img)
                        await bot.send_photo(channel_id, f'{namef}.{ext}', caption=ccimg, **_get_send_kwargs(thread_id))
                        os.remove(f'{namef}.{ext}')
                        count += 1
                        total_success += 1
                        continue

                    # ---- DRM MPD ----
                    if 'drmcdni' in url or 'drm/wv' in url or 'drm/common' in url or 'mpd' in url:
                        prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}", **_get_send_kwargs(thread_id))
                        path = f"./downloads/{m.chat.id}"
                        res_file = await helper.decrypt_and_merge_video(url, keys_string, path, name, raw_text2)
                        await prog.delete()
                        await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, thread_id)
                        count += 1
                        total_success += 1
                        continue

                    # ---- APPX Encrypted ----
                    if 'encrypted.m' in url:
                        appxkey = url.split('*')[1]
                        url = url.split('*')[0]
                        prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}", **_get_send_kwargs(thread_id))
                        res_file = await helper.download_and_decrypt_video(url, cmd, name, appxkey)
                        await prog.delete()
                        await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, thread_id)
                        count += 1
                        total_success += 1
                        continue

                    # ---- Normal Video ----
                    prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}", **_get_send_kwargs(thread_id))
                    res_file = await helper.download_video(url, cmd, name)
                    await prog.delete()
                    await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, thread_id)
                    count += 1
                    total_success += 1

                except Exception as e:
                    await bot.send_message(channel_id, f'❌ Failed: {name1}\n{url}\nError: {e}', **_get_send_kwargs(thread_id))
                    count += 1
                    total_failed += 1

            # --- Group Completion ---
            await bot.send_message(
                chat_id=channel_id,
                text=f"✅ **{topic_name}** complete!",
                **_get_send_kwargs(thread_id)
            )

        # ===== FINAL SUMMARY =====
        await bot.send_message(
            chat_id=channel_id,
            text=f"🏁 **All batches processed.**\n✅ Success: {total_success}\n❌ Failed: {total_failed}",
            **_get_send_kwargs(None)  # no thread_id
        )
        await m.reply_text("✅ All tasks completed successfully!")

    # ============================================================
    # CASE 2: INPUT IS DIRECT TEXT (single or multiple links)
    # ============================================================
    elif m.text and "://" in m.text:
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

        # Ask for quality
        editable = await m.reply_text(
            "━━━━━━━━━━━⚡━━━━━━━━━━━\n"
            "🎥 **Enter Video Quality**\n"
            "━━━━━━━━━━━⚡━━━━━━━━━━━\n"
            "🎮 `144` | `240` | `360` | `480` | `720` | `1080`\n"
            "✔️ Send /d for default (480p)\n"
            "━━━━━━━━━━━━━━━━━━━━━━━"
        )
        try:
            input2: Message = await bot.listen(editable.chat.id, timeout=20)
            raw_text2 = input2.text
            await input2.delete(True)
        except asyncio.TimeoutError:
            raw_text2 = '480'
        await editable.delete()

        if raw_text2.lower() == '/d':
            raw_text2 = '480'
        quality = f"{raw_text2}p"
        if raw_text2 == "144":
            res = "256x144"
        elif raw_text2 == "240":
            res = "426x240"
        elif raw_text2 == "360":
            res = "640x360"
        elif raw_text2 == "480":
            res = "854x480"
        elif raw_text2 == "720":
            res = "1280x720"
        elif raw_text2 == "1080":
            res = "1920x1080"
        else:
            res = "UN"

        # Parse links from text (each line)
        urls = [line.strip() for line in m.text.split("\n") if "://" in line.strip()]
        if not urls:
            await m.reply_text("❌ No valid URLs found.")
            globals.processing_request = False
            return

        # Since no .txt, we treat all as one group
        topic_name = "Direct Links"
        channel_id = m.chat.id
        thread_id = None  # no topic

        # Send start message
        await bot.send_message(
            chat_id=channel_id,
            text=f"📂 **Batch:** {topic_name}\n🔄 Total: {len(urls)} links"
        )

        total_failed = 0
        total_success = 0
        count = 1
        for url_line in urls:
            if globals.cancel_requested:
                await m.reply_text("⏹️ Stopped by user.")
                globals.processing_request = False
                globals.cancel_requested = False
                return

            # Parse and title
            Vxy = url_line.split("://", 1)[1] if "://" in url_line else url_line
            Vxy = Vxy.replace("file/d/","uc?export=download&id=").replace("www.youtube-nocookie.com/embed", "youtu.be").replace("?modestbranding=1", "").replace("/view?usp=sharing","")
            url = "https://" + Vxy
            link0 = "https://" + Vxy

            raw_title = f"Video_{count}"
            name1 = f"Video_{count}"
            v_name = name1
            t_name = None
            display_title = name1
            name = f'{str(count).zfill(3)}) {name1[:60]}'
            namef = name1[:60]

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

            try:
                # ---- Same processing as above (without thread_id) ----
                if "visionias" in url:
                    async with ClientSession() as session:
                        async with session.get(url, headers={'User-Agent': 'Mozilla/5.0'}) as resp:
                            text = await resp.text()
                            url = re.search(r"(https://.*?playlist.m3u8.*?)\"", text).group(1)

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
                        await bot.send_message(channel_id, f'⚠️ Failed: {name1}\n{url}\nError: {e}')
                        count += 1
                        total_failed += 1
                        continue

                if "tencdn.classplusapp" in url:
                    headers = {'host': 'api.classplusapp.com', 'x-access-token': f'{cptoken}', 'accept-language': 'EN', 'api-version': '18', 'app-version': '1.4.73.2', 'build-number': '35', 'connection': 'Keep-Alive', 'content-type': 'application/json', 'device-details': 'Xiaomi_Redmi 7_SDK-32', 'device-id': 'c28d3cb16bbdac01', 'region': 'IN', 'user-agent': 'Mobile-Android', 'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c', 'accept-encoding': 'gzip'}
                    params = {"url": f"{url}"}
                    response = requests.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                    url = response.json()['url']

                if 'videos.classplusapp' in url:
                    url = requests.get(f'https://api.classplusapp.com/cams/uploader/video/jw-signed-url?url={url}', headers={'x-access-token': f'{cptoken}'}).json()['url']

                if 'media-cdn.classplusapp.com' in url or 'media-cdn-alisg.classplusapp.com' in url or 'media-cdn-a.classplusapp.com' in url:
                    headers = {'host': 'api.classplusapp.com', 'x-access-token': f'{cptoken}', 'accept-language': 'EN', 'api-version': '18', 'app-version': '1.4.73.2', 'build-number': '35', 'connection': 'Keep-Alive', 'content-type': 'application/json', 'device-details': 'Xiaomi_Redmi 7_SDK-32', 'device-id': 'c28d3cb16bbdac01', 'region': 'IN', 'user-agent': 'Mobile-Android', 'webengage-luid': '00000187-6fe4-5d41-a530-26186858be4c', 'accept-encoding': 'gzip'}
                    params = {"url": f"{url}"}
                    response = requests.get('https://api.classplusapp.com/cams/uploader/video/jw-signed-url', headers=headers, params=params)
                    url = response.json()['url']

                if "edge.api.brightcove.com" in url:
                    bcov = f'bcov_auth={cwtoken}'
                    url = url.split("bcov_auth")[0]+bcov

                if "childId" in url and "parentId" in url:
                    url = f"https://anonymouspwplayer-0e5a3f512dec.herokuapp.com/pw?url={url}&token={pwtoken}"

                if 'encrypted.m' in url:
                    appxkey = url.split('*')[1]
                    url = url.split('*')[0]

                if "youtu" in url:
                    ytf = f"bv*[height<={raw_text2}][ext=mp4]+ba[ext=m4a]/b[height<=?{raw_text2}]"
                    cmd = f'yt-dlp --cookies youtube_cookies.txt -f "{ytf}" "{url}" -o "{name}.mp4"'
                else:
                    ytf = f"b[height<={raw_text2}]/bv[height<={raw_text2}]+ba/b/bv+ba"
                    cmd = f'yt-dlp -f "{ytf}" "{url}" -o "{name}.mp4"'

                if "pdf" in url:
                    if "cwmediabkt99" in url:
                        scraper = cloudscraper.create_scraper()
                        resp = scraper.get(url)
                        if resp.status_code == 200:
                            with open(f'{namef}.pdf', 'wb') as f:
                                f.write(resp.content)
                            await bot.send_document(channel_id, f'{namef}.pdf', caption=cc1)
                            os.remove(f'{namef}.pdf')
                        else:
                            raise Exception(f"PDF download failed: {resp.status_code}")
                    else:
                        cmd_pdf = f'yt-dlp -o "{namef}.pdf" "{url}" -R 25 --fragment-retries 25'
                        os.system(cmd_pdf)
                        await bot.send_document(channel_id, f'{namef}.pdf', caption=cc1)
                        os.remove(f'{namef}.pdf')
                    count += 1
                    total_success += 1
                    continue

                if any(ext in url for ext in [".jpg", ".jpeg", ".png"]):
                    ext = url.split('.')[-1]
                    cmd_img = f'yt-dlp -o "{namef}.{ext}" "{url}"'
                    os.system(cmd_img)
                    await bot.send_photo(channel_id, f'{namef}.{ext}', caption=ccimg)
                    os.remove(f'{namef}.{ext}')
                    count += 1
                    total_success += 1
                    continue

                if 'drmcdni' in url or 'drm/wv' in url or 'drm/common' in url or 'mpd' in url:
                    prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}")
                    path = f"./downloads/{m.chat.id}"
                    res_file = await helper.decrypt_and_merge_video(url, keys_string, path, name, raw_text2)
                    await prog.delete()
                    await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, None)
                    count += 1
                    total_success += 1
                    continue

                if 'encrypted.m' in url:
                    appxkey = url.split('*')[1]
                    url = url.split('*')[0]
                    prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}")
                    res_file = await helper.download_and_decrypt_video(url, cmd, name, appxkey)
                    await prog.delete()
                    await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, None)
                    count += 1
                    total_success += 1
                    continue

                prog = await bot.send_message(channel_id, f"⏳ Downloading: {name1}")
                res_file = await helper.download_video(url, cmd, name)
                await prog.delete()
                await helper.send_vid(bot, m, cc, res_file, vidwatermark, thumb, name, prog, channel_id, None)
                count += 1
                total_success += 1

            except Exception as e:
                await bot.send_message(channel_id, f'❌ Failed: {name1}\n{url}\nError: {e}')
                count += 1
                total_failed += 1

        await bot.send_message(
            chat_id=channel_id,
            text=f"🏁 **All links processed.**\n✅ Success: {total_success}\n❌ Failed: {total_failed}"
        )
        await m.reply_text("✅ All tasks completed!")

    else:
        await m.reply_text("⚠️ Please send a .txt file or direct links.")
        globals.processing_request = False
        return

    globals.processing_request = False

# ================================================================
def register_drm_handlers(bot):
    @bot.on_message(filters.private & (filters.document | filters.text))
    async def call_drm_handler(bot: Client, m: Message):
        await drm_handler(bot, m)
