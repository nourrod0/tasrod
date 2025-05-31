import threading
import subprocess

# تشغيل telegram_bot.py في Thread
def run_bot():
    subprocess.run(["python3", "telegram_bot.py"])

# تشغيل البوت
bot_thread = threading.Thread(target=run_bot)
bot_thread.start()

# تشغيل السيرفر Flask
subprocess.run(["gunicorn", "main:app"])
