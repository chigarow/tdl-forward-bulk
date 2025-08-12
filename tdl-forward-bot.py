

import logging
import subprocess
import redis
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from datetime import datetime
import os
import configparser
import asyncio


# --- CONFIG ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'secrets.properties')
config = configparser.ConfigParser()
config.read(CONFIG_PATH)
BOT_TOKEN = config.get('DEFAULT', 'BOT_TOKEN', fallback=None)
if not BOT_TOKEN:
	raise RuntimeError('BOT_TOKEN not found in secrets.properties!')
REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 0
PROCESSED_URLS_KEY = "tdl:processed_urls"

# --- LOGGING ---
logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(levelname)s: %(message)s',
)

# --- REDIS ---
try:
	redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
	redis_client.ping()
	redis_available = True
	logging.info("Redis connection established")
except Exception as e:
	redis_available = False
	logging.warning(f"Redis connection failed: {e}")

def normalize_url(url):
	return url.split(" - ")[0].strip().replace("?single", "")

def is_url_processed(url):
	normalized_url = normalize_url(url)
	if redis_available:
		return redis_client.sismember(PROCESSED_URLS_KEY, normalized_url)
	return False

def mark_url_processed(url):
	normalized_url = normalize_url(url)
	if redis_available:
		redis_client.sadd(PROCESSED_URLS_KEY, normalized_url)


# --- QUEUE AND WORKER ---
queue = asyncio.Queue()

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not update.message or not update.message.text:
		return
	url = update.message.text.strip()
	user = update.effective_user.first_name if update.effective_user else "user"
	logging.info(f"Received from {user}: {url}")

	# Check for duplicate
	if is_url_processed(url):
		await update.message.reply_text("This link has already been processed.")
		return

	# Put job in queue
	await queue.put((update, url))
	qsize = queue.qsize()
	if qsize > 1:
		await update.message.reply_text(f"Your link is queued. Position: {qsize}")
	else:
		await update.message.reply_text("Your link is being processed...")

async def queue_worker():
	while True:
		update, url = await queue.get()
		try:
			await process_link(update, url)
		except Exception as e:
			logging.error(f"Error processing link: {e}")
		queue.task_done()

async def process_link(update: Update, url: str):
	import time as _time
	start_time = _time.time()
	# Call tdl CLI
	try:
		process = subprocess.Popen([
			"tdl", "forward", "--from", url.replace("?single", "")
		], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
		output_lines = []
		error_occurred = False
		for line in iter(process.stdout.readline, ""):
			output_lines.append(line.strip())
			if "Error" in line:
				error_occurred = True
		process.wait()
		output = "\n".join(output_lines)
	except Exception as e:
		await update.message.reply_text(f"Failed to run tdl: {e}")
		return
	elapsed = _time.time() - start_time

	# Log full output to a file for debugging
	log_file = f"tdl_forward_log_{datetime.now().strftime('%Y%m%d')}.txt"
	with open(log_file, "a") as f:
		f.write(f"\n{'='*40}\n{datetime.now()}\nURL: {url}\nOutput:\n{output}\n")

	# Mark as processed if successful
	if process.returncode == 0 and not error_occurred:
		mark_url_processed(url)
		human_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		await update.message.reply_text(
			f"✅ Forwarded successfully!\nTime: {human_time}\nElapsed: {elapsed:.2f} seconds"
		)
	else:
		await update.message.reply_text(f"❌ Failed to forward. See log file for details.")


def main():
	app = ApplicationBuilder().token(BOT_TOKEN).build()
	app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
	logging.info("Bot started. Waiting for messages...")

	# Start the queue worker in the event loop
	async def post_init(app):
		app.create_task(queue_worker())

	app.post_init = post_init
	app.run_polling()

if __name__ == "__main__":
	main()

