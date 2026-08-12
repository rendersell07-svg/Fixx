import os
import requests
import subprocess
from pyrogram import Client, filters
from pyrogram.types import Message
from vars import CREDIT

async def text_to_txt(bot: Client, message: Message):
    user_id = str(message.from_user.id)
    editable = await message.reply_text(f"<blockquote><b>Welcome to the Text to .txt Converter!\nSend the **text** for convert into a `.txt` file.</b></blockquote>")
    input_message: Message = await bot.listen(message.chat.id)
    if not input_message.text:
        await message.reply_text("**Send valid text data**")
        return

    text_data = input_message.text.strip()
    await input_message.delete()
    
    await editable.edit("**🔄 Send file name or send /d for filename**")
    inputn: Message = await bot.listen(message.chat.id)
    raw_textn = inputn.text
    await inputn.delete()
    await editable.delete()

    if raw_textn == '/d':
        custom_file_name = 'txt_file'
    else:
        custom_file_name = raw_textn

    txt_file = os.path.join("downloads", f'{custom_file_name}.txt')
    os.makedirs(os.path.dirname(txt_file), exist_ok=True)
    with open(txt_file, 'w') as f:
        f.write(text_data)
    
    # ============ नया TXT file caption ============
    txt_caption = (
        f"Index: 1\n\n"
        f"Title: {custom_file_name}.txt\n\n"
        f"Batch: {custom_file_name}\n\n"
        f"Extracted By: {CREDIT}"
    )
    await message.reply_document(document=txt_file, caption=txt_caption)
    os.remove(txt_file)

# Define paths for uploaded file and processed file
UPLOAD_FOLDER = '/path/to/upload/folder'
EDITED_FILE_PATH = '/path/to/save/edited_output.txt'

def register_text_handlers(bot):
    @bot.on_message(filters.command(["t2t"]))
    async def call_text_to_txt(bot: Client, m: Message):
        await text_to_txt(bot, m)
