

import logging
import subprocess
import redis
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, CommandHandler, filters, ContextTypes
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


def is_url_processed_anywhere(url):
	normalized_url = normalize_url(url)
	# Check Redis
	if redis_available and redis_client.sismember(PROCESSED_URLS_KEY, normalized_url):
		logging.info(f"Duplicate check: {normalized_url} found in Redis (already processed)")
		return 'redis'
	# Check current_processing
	if current_processing and normalize_url(current_processing[0]) == normalized_url:
		logging.info(f"Duplicate check: {normalized_url} is currently being processed")
		return 'processing'
	# Check queue_links
	for queued_url, *_ in queue_links:
		if normalize_url(queued_url) == normalized_url:
			logging.info(f"Duplicate check: {normalized_url} is in the queue")
			return 'queue'
	logging.info(f"Duplicate check: {normalized_url} is new (not processed, not in queue)")
	return None

def mark_url_processed(url):
	normalized_url = normalize_url(url)
	if redis_available:
		redis_client.sadd(PROCESSED_URLS_KEY, normalized_url)


# --- QUEUE AND WORKER ---
queue = asyncio.Queue()
queue_links = []  # List of (url, user, chat_id, message_id) for /q, /remove, /clear
current_processing = None  # (url, user, chat_id, message_id)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not update.message or not update.message.text:
		return
	url = update.message.text.strip()
	user = update.effective_user.first_name if update.effective_user else "user"
	logging.info(f"Received from {user}: {url}")

	# Check for duplicate in Redis, queue, or currently processing
	duplicate_status = is_url_processed_anywhere(url)
	if duplicate_status:
		if duplicate_status == 'redis':
			await update.message.reply_text("This link has already been processed.")
		elif duplicate_status == 'processing':
			await update.message.reply_text("This link is currently being processed.")
		elif duplicate_status == 'queue':
			await update.message.reply_text("This link is already in the queue.")
		else:
			await update.message.reply_text("This link is a duplicate.")
		return

	# Put job in queue and queue_links
	user_id = update.effective_user.id if update.effective_user else None
	chat_id = update.effective_chat.id if update.effective_chat else None
	message_id = update.message.message_id if update.message else None
	job = (url, user, chat_id, message_id)
	await queue.put(job)
	queue_links.append(job)
	# Feedback logic
	# If nothing is being processed and this is the only job, it's being processed now
	if current_processing is None and queue.qsize() == 1:
		await update.message.reply_text("Your link is being processed...")
	else:
		# Position in queue is the number of jobs ahead of this one (including current_processing)
		position = queue.qsize()
		await update.message.reply_text(f"Your link is in the queue. Position: {position}")

async def queue_worker():
	global current_processing
	while True:
		job = await queue.get()
		url, user, chat_id, message_id = job
		current_processing = job
		# Remove from queue_links (first occurrence)
		for i, (u, _, _, _) in enumerate(queue_links):
			if u == url:
				del queue_links[i]
				break
		try:
			await process_link(url, user, chat_id, message_id)
		except Exception as e:
			logging.error(f"Error processing link: {e}")
		current_processing = None
		queue.task_done()

async def process_link(url: str, user: str, chat_id: int, message_id: int):
	import time as _time
	from telegram import Bot
	start_time = _time.time()
	# Call tdl CLI asynchronously
	try:
		process = await asyncio.create_subprocess_exec(
			"tdl", "forward", "--from", url.replace("?single", ""),
			stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
		)
		output_lines = []
		error_occurred = False
		# Read output line by line asynchronously (decode bytes)
		while True:
			line = await process.stdout.readline()
			if not line:
				break
			line_str = line.decode("utf-8", errors="replace").strip()
			output_lines.append(line_str)
			if "Error" in line_str:
				error_occurred = True
		await process.wait()
		output = "\n".join(output_lines)
	except Exception as e:
		await send_message(chat_id, f"Failed to run tdl: {e}", reply_to_message_id=message_id)
		return
	elapsed = _time.time() - start_time

	# Log full output to a file for debugging
	log_file = f"tdl_forward_log_{datetime.now().strftime('%Y%m%d')}.txt"
	with open(log_file, "a") as f:
		f.write(f"\n{'='*40}\n{datetime.now()}\nURL: {url}\nOutput:\n{output}\n")

	# Mark as processed if successful
	if process.returncode == 0 and not error_occurred:
		human_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		try:
			await send_message(chat_id,
				f"✅ Forwarded successfully!\nTime: {human_time}\nElapsed: {elapsed:.2f} seconds",
				reply_to_message_id=message_id)
			# Only mark as processed after successfully sending the success message
			mark_url_processed(url)
		except Exception as e:
			logging.error(f"Failed to send success message: {e}")
			# Don't mark as processed if we couldn't send the success message
	else:
		await send_message(chat_id, f"❌ Failed to forward. See log file for details.", reply_to_message_id=message_id)

# Helper to send message from outside handler
async def send_message(chat_id, text, reply_to_message_id=None):
	from telegram import Bot
	bot = Bot(BOT_TOKEN)
	await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id)

# --- COMMANDS ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if current_processing:
		url, user, chat_id, message_id = current_processing
		await update.message.reply_text(f"Currently processing:\n{url}\nFrom: {user}")
	else:
		await update.message.reply_text("No link under process.")

async def q_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not queue_links:
		await update.message.reply_text("Queue is empty.")
		return
	msg = "Links in queue:\n"
	for i, (url, user, chat_id, message_id) in enumerate(queue_links, 1):
		msg += f"{i}. {url} (from {user})\n"
	await update.message.reply_text(msg.strip())

async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not context.args:
		await update.message.reply_text("Usage: /remove THE_URL")
		return
	url_to_remove = " ".join(context.args).strip()
	for i, (url, user, chat_id, message_id) in enumerate(queue_links):
		if url == url_to_remove:
			del queue_links[i]
			await update.message.reply_text(f"Removed: {url_to_remove}")
			return
	await update.message.reply_text("URL not found in queue.")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	queue_links.clear()
	# Drain the asyncio.Queue
	while not queue.empty():
		try:
			queue.get_nowait()
			queue.task_done()
		except Exception:
			break
	await update.message.reply_text("Queue cleared.")

async def empty_redis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if redis_available:
		count = redis_client.scard(PROCESSED_URLS_KEY)
		redis_client.delete(PROCESSED_URLS_KEY)
		await update.message.reply_text(f"Redis cleared. Removed {count} processed URLs.")
	else:
		await update.message.reply_text("Redis is not available.")

async def delete_link_redis_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not context.args:
		await update.message.reply_text("Usage: /delete_link_redis THE_URL")
		return
	
	if not redis_available:
		await update.message.reply_text("Redis is not available.")
		return
	
	url_to_delete = " ".join(context.args).strip()
	normalized_url = normalize_url(url_to_delete)
	
	# Check if the URL exists in Redis
	if redis_client.sismember(PROCESSED_URLS_KEY, normalized_url):
		redis_client.srem(PROCESSED_URLS_KEY, normalized_url)
		await update.message.reply_text(f"Removed from Redis: {normalized_url}")
	else:
		await update.message.reply_text(f"URL not found in Redis: {normalized_url}")


def main():
	app = ApplicationBuilder().token(BOT_TOKEN).build()
	app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
	app.add_handler(CommandHandler("status", status_command))
	app.add_handler(CommandHandler("q", q_command))
	app.add_handler(CommandHandler("remove", remove_command))
	app.add_handler(CommandHandler("clear", clear_command))
	app.add_handler(CommandHandler("empty_redis", empty_redis_command))
	app.add_handler(CommandHandler("delete_link_redis", delete_link_redis_command))
	logging.info("Bot started. Waiting for messages...")

	# Start the queue worker in the event loop and set bot commands
	async def post_init(app):
		await app.bot.set_my_commands([
			("status", "Show current processing link or idle status"),
			("q", "Show all links in the queue"),
			("remove", "Remove a link from the queue by URL"),
			("clear", "Clear all links from the queue"),
			("empty_redis", "Clear all processed URLs from Redis"),
			("delete_link_redis", "Remove a specific URL from Redis"),
		])
		app.create_task(queue_worker())

	app.post_init = post_init
	app.run_polling()

if __name__ == "__main__":
	main()

