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

# Admin chat ID for error notifications
ADMIN_CHAT_ID = config.get('DEFAULT', 'ADMIN_CHAT_ID', fallback=None)


# --- FILE-BASED PERSISTENCE ---
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
os.makedirs(DATA_DIR, exist_ok=True)
QUEUE_FILE = os.path.join(DATA_DIR, 'queue.txt')
PROCESSING_FILE = os.path.join(DATA_DIR, 'processing.txt')
FINISHED_FILE = os.path.join(DATA_DIR, 'finished.txt')
FAILED_FILE = os.path.join(DATA_DIR, 'failed.txt')
USERS_FILE = os.path.join(DATA_DIR, 'users.txt')
PASSWORD = config.get('DEFAULT', 'PASSWORD', fallback=None)
file_lock = threading.Lock()
def append_failed(url, reason=None):
	# Add a failed forward to failed.txt with GMT+7 timestamp
	from datetime import datetime, timezone, timedelta
	tz = timezone(timedelta(hours=7))
	now = datetime.now(tz)
	timestamp = now.strftime('%Y-%m-%d %H:%M:%S GMT+7')
	line = f"{timestamp} | {normalize_url(url)}"
	if reason:
		line += f" | {reason}"
	with file_lock:
		append_line(FAILED_FILE, line)

# --- USER AUTHENTICATION ---
def read_users():
	users = {}
	if not os.path.exists(USERS_FILE):
		return users
	with open(USERS_FILE, 'r') as f:
		for line in f:
			if '=' in line:
				uid, status = line.strip().split('=', 1)
				users[uid] = status
	return users

def write_users(users):
	with open(USERS_FILE, 'w') as f:
		for uid, status in users.items():
			f.write(f"{uid}={status}\n")

def set_user_status(user_id, status):
	users = read_users()
	users[str(user_id)] = status
	write_users(users)

def get_user_status(user_id):
	users = read_users()
	return users.get(str(user_id), None)

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
	# Normalize a Telegram URL by removing any " - " suffix and stripping the ?single parameter
	import re
	if not url:
		return url
	# Remove any trailing ' - ...' metadata
	base = url.split(" - ")[0].strip()
	# Remove occurrences of '?single' or '?single=...' (and any accidental leftover '?' or '&')
	# Examples handled: '.../12345?single', '.../12345?single=true', '.../12345?single=&other=1'
	base = re.sub(r"\?single(?:=[^&]*)?", "", base)
	# If there are leftover sequences like '?&' or '??' or trailing '&' clean them up
	base = re.sub(r"[?&]{2,}", "?", base)
	base = re.sub(r"[?&]$", "", base)
	return base


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
current_progress = None  # Store current progress info (percentage, eta, speed)
bulk_batches = {}  # Track bulk submissions: {batch_id: {chat_id, message_id, total, completed, failed}}

# On startup, load queue and processing from files
def load_persistent_state():
	with file_lock:
		processing_lines = read_lines(PROCESSING_FILE)
		queue_lines = read_lines(QUEUE_FILE)
	# If processing.txt has a link, process it first
	if processing_lines:
		url = normalize_url(processing_lines[0])
		queue_links.append((url, '', None, None, None))  # Add None for batch_id
		queue.put_nowait((url, '', None, None, None))
	# Then load the rest of the queue
	for url in queue_lines:
		n = normalize_url(url)
		queue_links.append((n, '', None, None, None))  # Add None for batch_id
		queue.put_nowait((n, '', None, None, None))

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
	if not update.message or not update.message.text:
		return
	user_id = update.effective_user.id if update.effective_user else None
	user = update.effective_user.first_name if update.effective_user else "user"
	chat_id = update.effective_chat.id if update.effective_chat else None
	message_id = update.message.message_id if update.message else None
	text = update.message.text.strip()
	logging.info(f"Received from {user} ({user_id}): {text}")

	# --- AUTHENTICATION CHECK ---
	status = get_user_status(user_id)
	if status == 'authenticated':
		pass  # continue to normal processing
	elif status == 'not_authenticated' or status is None:
		# If user is not authenticated, check if they are trying to enter password
		if PASSWORD and text == PASSWORD:
			set_user_status(user_id, 'authenticated')
			await update.message.reply_text("✅ You are now authenticated! You can use the bot.")
			return
		else:
			set_user_status(user_id, 'not_authenticated')
			await update.message.reply_text("🔒 Please enter the password to use this bot.")
			return

	# --- NORMAL BOT LOGIC (only for authenticated users) ---
	text_lines = text.strip().split('\n')
	valid_urls = []
	
	# Extract valid Telegram URLs from the message
	for line in text_lines:
		line = line.strip()
		if line and ('t.me/' in line or 'telegram.me/' in line):
			# Basic URL validation for Telegram links
			if line.startswith('http'):
				valid_urls.append(line)
	
	# If no valid URLs found, treat the entire message as a single URL (backward compatibility)
	if not valid_urls:
		valid_urls = [text]
	
	# Process each URL
	added_count = 0
	duplicate_count = 0
	duplicate_details = []
	
	# Generate batch ID for bulk submissions (multiple URLs)
	batch_id = None
	if len(valid_urls) > 1:
		import uuid
		batch_id = str(uuid.uuid4())
		bulk_batches[batch_id] = {
			'chat_id': chat_id,
			'message_id': message_id,
			'total': len(valid_urls),
			'completed': 0,
			'failed': 0,
			'user': user
		}
	
	for url in valid_urls:
		# Normalize URL first (remove ?single and similar) then check for duplicates
		normalized = normalize_url(url)
		# Check for duplicate based on finished.txt, queue.txt, and processing.txt
		duplicate_status = is_url_processed_anywhere(normalized)
		if duplicate_status:
			duplicate_count += 1
			duplicate_details.append(f"• {normalized} ({duplicate_status})")
			continue
		
		# Put job in queue and queue_links, and persist to file
		job = (normalized, user, chat_id, message_id, batch_id)  # use normalized URL in job
		await queue.put(job)
		queue_links.append(job)
		with file_lock:
			append_line(QUEUE_FILE, normalized)
		added_count += 1
	
	# Provide feedback to user
	if added_count == 0 and duplicate_count > 0:
		# All URLs were duplicates
		if duplicate_count == 1:
			await update.message.reply_text(f"This link is a duplicate and has already been processed or is in queue.")
		else:
			msg = f"All {duplicate_count} links are duplicates:\n" + "\n".join(duplicate_details[:10])
			if len(duplicate_details) > 10:
				msg += f"\n... and {len(duplicate_details) - 10} more"
			await update.message.reply_text(msg)
	elif added_count > 0:
		# Some or all URLs were added
		if duplicate_count == 0:
			# All URLs were added successfully
			if added_count == 1:
				if current_processing is None and queue.qsize() == 1:
					await update.message.reply_text("Your link is being processed...")
				else:
					position = queue.qsize()
					await update.message.reply_text(f"Your link is in the queue. Position: {position}")
			else:
				await update.message.reply_text(f"✅ Added {added_count} links to the queue. Queue position starts at: {queue.qsize() - added_count + 1}")
		else:
			# Some URLs added, some duplicates
			msg = f"✅ Added {added_count} new links to the queue.\n"
			msg += f"⚠️ Skipped {duplicate_count} duplicates"
			if duplicate_count <= 5:
				msg += ":\n" + "\n".join(duplicate_details)
			await update.message.reply_text(msg)

async def queue_worker():
	global current_processing, current_progress
	while True:
		job = await queue.get()
		url, user, chat_id, message_id = job[:4]  # Handle both old and new job formats
		batch_id = job[4] if len(job) > 4 else None
		current_processing = job
		current_progress = None  # Reset progress for new job
		
		# Log job details for debugging
		logging.info(f"Processing job: URL={url}, chat_id={chat_id}, message_id={message_id}, batch_id={batch_id}")
		
		# Remove from queue_links (first occurrence)
		for i, (u, _, _, _, _) in enumerate(queue_links):
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
			await process_link(url, user, chat_id, message_id, batch_id)
		except Exception as e:
			error_msg = f"Error processing link {url}: {e}"
			logging.error(error_msg)
			await send_error_to_admin(error_msg)
		current_processing = None
		current_progress = None  # Clear progress when done
		queue.task_done()

async def process_link(url: str, user: str, chat_id: int, message_id: int, batch_id: str = None):
	import time as _time
	import re
	from telegram import Bot
	global current_progress
	start_time = _time.time()
	# Call tdl CLI asynchronously
	try:
		clean_for_tdl = normalize_url(url)
		process = await asyncio.create_subprocess_exec(
			"tdl", "forward", "--from", clean_for_tdl,
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
			
			# Log each line for debugging
			if line_str and ("%" in line_str or "ETA" in line_str or "MB/s" in line_str):
				logging.info(f"TDL Output Line: {line_str}")
			
			# Remove ANSI color codes from the line for cleaner parsing
			clean_line = re.sub(r'\x1b\[[0-9;]*m', '', line_str)
			
			# Extract progress information from tdl output
			# Pattern 1: Look for percentage, ETA, and speed in the format like "3.0% [...] [...; ~ETA: 8m42s; 5.28 MB/s]"
			progress_match = re.search(r'(\d+\.?\d*)%.*?ETA:\s*([^;\]]+).*?(\d+\.?\d+\s*[KMGT]?B/s)', clean_line)
			if progress_match:
				percentage = progress_match.group(1)
				eta = progress_match.group(2).strip()
				speed = progress_match.group(3).strip()
				current_progress = {
					'percentage': percentage,
					'eta': eta,
					'speed': speed
				}
				logging.info(f"Progress update (pattern 1): {percentage}% - ETA: {eta} - Speed: {speed}")
			else:
				# Pattern 2: Look for percentage and try to find ETA separately
				percent_match = re.search(r'(\d+\.?\d*)%', clean_line)
				if percent_match:
					percentage = percent_match.group(1)
					
					# Look for ETA pattern
					eta_match = re.search(r'ETA:\s*([^;\]\s]+)', clean_line)
					eta = eta_match.group(1).strip() if eta_match else "Calculating..."
					
					# Look for speed pattern  
					speed_match = re.search(r'(\d+\.?\d+\s*[KMGT]?B/s)', clean_line)
					speed = speed_match.group(1).strip() if speed_match else "N/A"
					
					current_progress = {
						'percentage': percentage,
						'eta': eta,
						'speed': speed
					}
					logging.info(f"Progress update (pattern 2): {percentage}% - ETA: {eta} - Speed: {speed}")
		
		await process.wait()
		output = "\n".join(output_lines)
	except Exception as e:
		error_msg = f"Failed to run tdl for {url}: {e}"
		logging.error(error_msg)
		await send_error_to_admin(error_msg)
		await send_message(chat_id, f"Failed to run tdl: {e}", reply_to_message_id=message_id)
		return
	elapsed = _time.time() - start_time

	# Helper function to format elapsed time in human-readable format
	def format_elapsed_time(seconds):
		if seconds < 60:
			return f"{seconds:.2f} seconds"
		
		minutes = int(seconds // 60)
		remaining_seconds = seconds % 60
		
		if minutes < 60:
			if remaining_seconds < 1:
				return f"{minutes} minutes"
			else:
				return f"{minutes} minutes {remaining_seconds:.1f} seconds"
		
		hours = int(minutes // 60)
		remaining_minutes = minutes % 60
		
		if hours < 24:
			if remaining_minutes == 0 and remaining_seconds < 1:
				return f"{hours} hours"
			elif remaining_seconds < 1:
				return f"{hours} hours {remaining_minutes} minutes"
			else:
				return f"{hours} hours {remaining_minutes} minutes {remaining_seconds:.1f} seconds"
		
		days = int(hours // 24)
		remaining_hours = hours % 24
		
		if remaining_hours == 0 and remaining_minutes == 0 and remaining_seconds < 1:
			return f"{days} days"
		elif remaining_minutes == 0 and remaining_seconds < 1:
			return f"{days} days {remaining_hours} hours"
		elif remaining_seconds < 1:
			return f"{days} days {remaining_hours} hours {remaining_minutes} minutes"
		else:
			return f"{days} days {remaining_hours} hours {remaining_minutes} minutes {remaining_seconds:.1f} seconds"

	# Log full output to a file for debugging
	log_file = f"tdl_forward_log_{datetime.now().strftime('%Y%m%d')}.txt"
	with open(log_file, "a") as f:
		f.write(f"\n{'='*40}\n{datetime.now()}\nURL: {url}\nOutput:\n{output}\n")

	# Mark as processed if successful
	if process.returncode == 0 and not error_occurred:
		human_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
		elapsed_formatted = format_elapsed_time(elapsed)
		
		# Handle bulk vs single link notifications
		if batch_id and batch_id in bulk_batches:
			# This is part of a bulk submission
			bulk_batches[batch_id]['completed'] += 1
			
			# Check if this batch is complete
			batch_info = bulk_batches[batch_id]
			if batch_info['completed'] + batch_info['failed'] >= batch_info['total']:
				# Send summary notification
				summary_msg = f"📦 Bulk processing complete!\n"
				summary_msg += f"✅ Completed: {batch_info['completed']}\n"
				if batch_info['failed'] > 0:
					summary_msg += f"❌ Failed: {batch_info['failed']}\n"
				summary_msg += f"📊 Total: {batch_info['total']} links"
				
				# Validate chat_id before sending
				if batch_info['chat_id'] and batch_info['chat_id'] != '':
					try:
						await send_message(batch_info['chat_id'], summary_msg, reply_to_message_id=batch_info['message_id'])
					except Exception as e:
						error_msg = f"Failed to send bulk summary (success): {e}"
						logging.error(error_msg)
						await send_error_to_admin(error_msg)
				else:
					error_msg = f"Batch summary not sent (success): chat_id is empty for batch {batch_id}"
					logging.error(error_msg)
					await send_error_to_admin(error_msg)
				
				# Clean up batch tracking
				del bulk_batches[batch_id]
		else:
			# Single link - send individual notification
			# Validate chat_id before sending
			if chat_id and chat_id != '':
				try:
					await send_message(chat_id,
						f"✅ Forwarded successfully!\nTime: {human_time}\nElapsed: {elapsed_formatted}",
						reply_to_message_id=message_id)
				except Exception as e:
					error_msg = f"Failed to send success message: {e}"
					logging.error(error_msg)
					await send_error_to_admin(error_msg)
					# Don't mark as processed if we couldn't send the success message
					return
			else:
				error_msg = f"Success message not sent: chat_id is empty for URL {url}"
				logging.error(error_msg)
				await send_error_to_admin(error_msg)
		
		# Only mark as processed after successfully handling notifications
		mark_url_processed(url)
	else:
		# Handle failures
		if batch_id and batch_id in bulk_batches:
			bulk_batches[batch_id]['failed'] += 1
			
			# Check if this batch is complete
			batch_info = bulk_batches[batch_id]
			if batch_info['completed'] + batch_info['failed'] >= batch_info['total']:
				# Send summary notification
				summary_msg = f"📦 Bulk processing complete!\n"
				summary_msg += f"✅ Completed: {batch_info['completed']}\n"
				if batch_info['failed'] > 0:
					summary_msg += f"❌ Failed: {batch_info['failed']}\n"
				summary_msg += f"📊 Total: {batch_info['total']} links"
				
				# Validate chat_id before sending
				if batch_info['chat_id'] and batch_info['chat_id'] != '':
					try:
						await send_message(batch_info['chat_id'], summary_msg, reply_to_message_id=batch_info['message_id'])
					except Exception as e:
						error_msg = f"Failed to send bulk summary (failure): {e}"
						logging.error(error_msg)
						await send_error_to_admin(error_msg)
				else:
					error_msg = f"Batch summary not sent (failure): chat_id is empty for batch {batch_id}"
					logging.error(error_msg)
					await send_error_to_admin(error_msg)
				
				# Clean up batch tracking
				del bulk_batches[batch_id]
		else:
			# Single link failure notification
			# Validate chat_id before sending
			if chat_id and chat_id != '':
				await send_message(chat_id, f"❌ Failed to forward. See log file for details.", reply_to_message_id=message_id)
			else:
				error_msg = f"Failure message not sent: chat_id is empty for URL {url}"
				logging.error(error_msg)
				await send_error_to_admin(error_msg)
		
		append_failed(url)
async def failed_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
	with file_lock:
		failed_list = read_lines(FAILED_FILE)
	if not failed_list:
		await update.message.reply_text("No failed forwards.")
		return
	msg = "Failed forwards (latest on bottom):\n"
	for line in failed_list:
		msg += f"{line}\n"
	await update.message.reply_text(msg.strip())

# Helper to send message from outside handler
async def send_message(chat_id, text, reply_to_message_id=None):
	from telegram import Bot
	
	# Validate chat_id
	if not chat_id or chat_id == '':
		raise ValueError("Chat_id is empty")
	
	bot = Bot(BOT_TOKEN)
	await bot.send_message(chat_id=chat_id, text=text, reply_to_message_id=reply_to_message_id)

# Helper to send error notifications to admin
async def send_error_to_admin(error_message):
	if ADMIN_CHAT_ID:
		try:
			from telegram import Bot
			bot = Bot(BOT_TOKEN)
			timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			formatted_message = f"🚨 Bot Error [{timestamp}]\n\n{error_message}"
			await bot.send_message(chat_id=ADMIN_CHAT_ID, text=formatted_message)
		except Exception as e:
			logging.error(f"Failed to send error to admin: {e}")
	else:
		logging.warning("ADMIN_CHAT_ID not configured - error notifications disabled")


# --- COMMANDS ---
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
	with file_lock:
		processing = read_lines(PROCESSING_FILE)
	if processing:
		status_msg = f"Currently processing:\n{processing[0]}"
		if current_progress:
			status_msg += f"\n\n📊 Progress: {current_progress['percentage']}%"
			status_msg += f"\n⏱️ ETA: {current_progress['eta']}"
			status_msg += f"\n🚀 Speed: {current_progress['speed']}"
		await update.message.reply_text(status_msg)
	else:
		await update.message.reply_text("No link under process.")

async def q_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
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
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
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
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
	with file_lock:
		clear_file(QUEUE_FILE)
	await update.message.reply_text("Queue cleared.")


async def empty_finished_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
	with file_lock:
		count = len(read_lines(FINISHED_FILE))
		clear_file(FINISHED_FILE)
	await update.message.reply_text(f"Finished list cleared. Removed {count} processed URLs.")

async def set_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
	
	# Set the current chat as admin chat for error notifications
	global ADMIN_CHAT_ID
	ADMIN_CHAT_ID = update.effective_chat.id
	
	# Save to config file
	config.set('DEFAULT', 'ADMIN_CHAT_ID', str(ADMIN_CHAT_ID))
	with open(CONFIG_PATH, 'w') as configfile:
		config.write(configfile)
	
	await update.message.reply_text(f"✅ Admin chat set! Error notifications will be sent to this chat.\nChat ID: {ADMIN_CHAT_ID}")

async def delete_link_finished_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
	user_id = update.effective_user.id if update.effective_user else None
	status = get_user_status(user_id)
	if status != 'authenticated':
		await update.message.reply_text("🔒 Please enter the password to use this bot.")
		return
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
	app.add_handler(CommandHandler("failed", failed_command))
	app.add_handler(CommandHandler("set_admin", set_admin_command))
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
			("failed", "Show all failed forwards with timestamp (GMT+7)"),
			("set_admin", "Set current chat as admin for error notifications"),
		])
		app.create_task(queue_worker())

	app.post_init = post_init
	app.run_polling()

if __name__ == "__main__":
	main()

