import logging
import subprocess
import threading
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



# --- FILE-BASED PERSISTENCE ---
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
QUEUE_FILE = os.path.join(DATA_DIR, 'queue.txt')
PROCESSING_FILE = os.path.join(DATA_DIR, 'processing.txt')
FINISHED_FILE = os.path.join(DATA_DIR, 'finished.txt')
file_lock = threading.Lock()

def read_lines(filename):
	if not os.path.exists(filename):
		return []
	with open(filename, 'r') as f:
		return [line.strip() for line in f if line.strip()]

def write_lines(filename, lines):
	with open(filename, 'w') as f:
		for line in lines:
			f.write(line + '\n')

def append_line(filename, line):
	with open(filename, 'a') as f:
		f.write(line + '\n')

def clear_file(filename):
	open(filename, 'w').close()

def normalize_url(url):
	return url.split(" - ")[0].strip().replace("?single", "")


def is_url_processed_anywhere(url):
	normalized_url = normalize_url(url)
	with file_lock:
		finished = set(read_lines(FINISHED_FILE))
		queue = set(read_lines(QUEUE_FILE))
		processing = set(read_lines(PROCESSING_FILE))
	if normalized_url in finished:
		logging.info(f"Duplicate check: {normalized_url} found in finished.txt (already processed)")
		return 'finished'
	if normalized_url in processing:
		logging.info(f"Duplicate check: {normalized_url} is currently being processed (processing.txt)")
		return 'processing'
	if normalized_url in queue:
		logging.info(f"Duplicate check: {normalized_url} is in the queue (queue.txt)")
		return 'queue'
	logging.info(f"Duplicate check: {normalized_url} is new (not processed, not in queue)")
	return None


def mark_url_processed(url):
	normalized_url = normalize_url(url)
	with file_lock:
		append_line(FINISHED_FILE, normalized_url)
		clear_file(PROCESSING_FILE)



# --- QUEUE AND WORKER ---
queue = asyncio.Queue()
queue_links = []  # List of (url, user, chat_id, message_id) for /q, /remove, /clear
current_processing = None  # (url, user, chat_id, message_id)

# On startup, load queue and processing from files
def load_persistent_state():
	with file_lock:
		processing_lines = read_lines(PROCESSING_FILE)
		queue_lines = read_lines(QUEUE_FILE)
	# If processing.txt has a link, process it first
	if processing_lines:
		url = processing_lines[0]
		queue_links.append((url, '', None, None))
		queue.put_nowait((url, '', None, None))
	# Then load the rest of the queue
	for url in queue_lines:
		queue_links.append((url, '', None, None))
		queue.put_nowait((url, '', None, None))

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

	# Put job in queue and queue_links, and persist to file
	user_id = update.effective_user.id if update.effective_user else None
	chat_id = update.effective_chat.id if update.effective_chat else None
	message_id = update.message.message_id if update.message else None
	job = (url, user, chat_id, message_id)
	await queue.put(job)
	queue_links.append(job)
	with file_lock:
		append_line(QUEUE_FILE, normalize_url(url))
	# Feedback logic
	if current_processing is None and queue.qsize() == 1:
		await update.message.reply_text("Your link is being processed...")
	else:
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
		# Only write to processing.txt if not already there
		with file_lock:
			processing_lines = read_lines(PROCESSING_FILE)
			if not processing_lines or processing_lines[0] != normalize_url(url):
				write_lines(PROCESSING_FILE, [normalize_url(url)])
		# Remove from queue.txt if present
		normalized_url = normalize_url(url)
		queue_lines = read_lines(QUEUE_FILE)
		queue_lines = [l for l in queue_lines if l != normalized_url]
		write_lines(QUEUE_FILE, queue_lines)
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
	with file_lock:
		processing = read_lines(PROCESSING_FILE)
	if processing:
		await update.message.reply_text(f"Currently processing:\n{processing[0]}")
	else:
		await update.message.reply_text("No link under process.")

async def q_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	with file_lock:
		queue_list = read_lines(QUEUE_FILE)
	if not queue_list:
		await update.message.reply_text("Queue is empty.")
		return
	msg = "Links in queue:\n"
	for i, url in enumerate(queue_list, 1):
		msg += f"{i}. {url}\n"
	await update.message.reply_text(msg.strip())

async def remove_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not context.args:
		await update.message.reply_text("Usage: /remove THE_URL")
		return
	url_to_remove = " ".join(context.args).strip()
	with file_lock:
		queue_list = read_lines(QUEUE_FILE)
		if url_to_remove in queue_list:
			queue_list = [u for u in queue_list if u != url_to_remove]
			write_lines(QUEUE_FILE, queue_list)
			await update.message.reply_text(f"Removed: {url_to_remove}")
		else:
			await update.message.reply_text("URL not found in queue.")

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	with file_lock:
		clear_file(QUEUE_FILE)
	await update.message.reply_text("Queue cleared.")


async def empty_finished_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	with file_lock:
		count = len(read_lines(FINISHED_FILE))
		clear_file(FINISHED_FILE)
	await update.message.reply_text(f"Finished list cleared. Removed {count} processed URLs.")

async def delete_link_finished_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not context.args:
		await update.message.reply_text("Usage: /delete_link_finished THE_URL")
		return
	url_to_delete = " ".join(context.args).strip()
	normalized_url = normalize_url(url_to_delete)
	with file_lock:
		finished_list = read_lines(FINISHED_FILE)
		if normalized_url in finished_list:
			finished_list = [u for u in finished_list if u != normalized_url]
			write_lines(FINISHED_FILE, finished_list)
			await update.message.reply_text(f"Removed from finished: {normalized_url}")
		else:
			await update.message.reply_text(f"URL not found in finished: {normalized_url}")


def main():
	load_persistent_state()
	app = ApplicationBuilder().token(BOT_TOKEN).build()
	app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
	app.add_handler(CommandHandler("status", status_command))
	app.add_handler(CommandHandler("q", q_command))
	app.add_handler(CommandHandler("remove", remove_command))
	app.add_handler(CommandHandler("clear", clear_command))
	app.add_handler(CommandHandler("empty_finished", empty_finished_command))
	app.add_handler(CommandHandler("delete_link_finished", delete_link_finished_command))
	logging.info("Bot started. Waiting for messages...")

	# Start the queue worker in the event loop and set bot commands
	async def post_init(app):
		await app.bot.set_my_commands([
			("status", "Show current processing link or idle status"),
			("q", "Show all links in the queue"),
			("remove", "Remove a link from the queue by URL"),
			("clear", "Clear all links from the queue"),
			("empty_finished", "Clear all processed URLs from finished.txt"),
			("delete_link_finished", "Remove a specific URL from finished.txt"),
		])
		app.create_task(queue_worker())

	app.post_init = post_init
	app.run_polling()

if __name__ == "__main__":
	main()

