import subprocess
import time
import logging
from datetime import datetime
import redis

# Set up logging to console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        # logging.FileHandler("forward_log.txt"),  # File handler
        logging.StreamHandler()  # Console handler
    ]
)

# Redis connection and configuration
REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB = 0
PROCESSED_URLS_KEY = "tdl:processed_urls"

# Initialize Redis client
try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    redis_client.ping()  # Test connection
    redis_available = True
    logging.info("Redis connection established")
except (redis.ConnectionError, redis.exceptions.ConnectionError):
    redis_available = False
    logging.warning("Redis connection failed - falling back to file-based tracking")

def normalize_url(url):
    """Normalize URL by removing ?single parameter and any timestamp."""
    # Split by dash and take the first part (the URL itself)
    base_url = url.split(" - ")[0].strip()
    # Remove ?single parameter if present
    return base_url.replace("?single", "")

def sync_redis_from_file():
    """Synchronize Redis set with URLs from done-url.txt"""
    if not redis_available:
        return
    
    try:
        with open("done-url.txt", "r") as f:
            for line in f:
                if line.strip():
                    normalized_url = normalize_url(line)
                    redis_client.sadd(PROCESSED_URLS_KEY, normalized_url)
        
        url_count = redis_client.scard(PROCESSED_URLS_KEY)
        logging.info(f"Synchronized {url_count} URLs to Redis")
    except FileNotFoundError:
        logging.info("done-url.txt not found. Creating a new one.")
        with open("done-url.txt", "w") as f:
            pass

def get_processed_urls():
    """Read done-url.txt and return a set of normalized URLs that have been processed."""
    # If Redis is available, we'll still load file data as backup,
    # but we'll primarily use Redis for lookups
    processed_urls = set()
    try:
        with open("done-url.txt", "r") as f:
            for line in f:
                if line.strip():
                    normalized_url = normalize_url(line)
                    processed_urls.add(normalized_url)
    except FileNotFoundError:
        logging.info("done-url.txt not found. Creating a new one.")
        with open("done-url.txt", "w") as f:
            pass
    return processed_urls

def is_url_processed(url):
    """Check if URL has been processed using Redis if available, otherwise use in-memory set."""
    normalized_url = normalize_url(url)
    if redis_available:
        return redis_client.sismember(PROCESSED_URLS_KEY, normalized_url)
    else:
        return normalized_url in processed_urls

def mark_url_processed(url, processed_urls):
    """Mark URL as processed in Redis and update in-memory set if needed."""
    normalized_url = normalize_url(url)
    if redis_available:
        redis_client.sadd(PROCESSED_URLS_KEY, normalized_url)
    
    # Always update in-memory set as fallback
    processed_urls.add(normalized_url)

def process_url(url, processed_urls):
    """Processes a single URL using tdl."""
    clean_url = url.replace("?single", "")
    
    # Check if URL is already processed
    if is_url_processed(url):
        logging.info(f"Duplicate URL detected: {clean_url}")
        # Add the URL to duplicate-url.txt with a timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open("duplicate-url.txt", "a") as dup_file:
            dup_file.write(f"{url} - {timestamp}\n")
        return True  # Return True to remove from the queue
    
    logging.info(f"Processing URL: {clean_url}")
    error_occurred = False
    deleted_message = False
    invalid_message = False
    chat_id_invalid = False
    username_invalid = False
    error_reason = ""
    
    process = subprocess.Popen(
        ["tdl", "forward", "--from", clean_url],
        stdout=subprocess.PIPE,  
        stderr=subprocess.STDOUT, 
        text=True, 
        bufsize=1  # Line buffering
    )

    for line in iter(process.stdout.readline, ""):  # Iterate over the output lines
        logging.info(line.strip())
        if "Error" in line:
            error_occurred = True
        if "may be deleted" in line:
            deleted_message = True
            error_reason = "MESSAGE_DELETED"
        if "invalid message" in line:
            invalid_message = True
            error_reason = "INVALID_MESSAGE"
        if "CHAT_ID_INVALID" in line:
            chat_id_invalid = True
            error_reason = "CHAT_ID_INVALID"
        if "USERNAME_INVALID" in line:
            username_invalid = True
            error_reason = "USERNAME_INVALID"

    # Wait for the process to finish
    process.wait()

    if invalid_message or chat_id_invalid or username_invalid:
        log_message = "Invalid URL detected"
        if invalid_message:
            log_message = "Invalid message detected"
        elif chat_id_invalid:
            log_message = "Chat ID invalid"
        elif username_invalid:
            log_message = "Username invalid"
            
        logging.warning(f"{log_message}: {clean_url}")
        # Add the URL to invalid-url.txt with a timestamp and reason
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open("invalid-url.txt", "a") as invalid_file:
            invalid_file.write(f"{url} - {timestamp} - {error_reason}\n")
        return True  # Return True to remove from the queue
    elif deleted_message:
        logging.warning(f"Message has been deleted: {clean_url}")
        # Add the URL to deleted-messages-url.txt with a timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open("deleted-messages-url.txt", "a") as deleted_file:
            deleted_file.write(f"{url} - {timestamp} - {error_reason}\n")
        return True  # Return True to remove from the queue
    elif process.returncode == 0 and not error_occurred:
        logging.info(f"Successfully forwarded: {clean_url}")
        # Add the URL to done-url.txt with a timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open("done-url.txt", "a") as done_file:
            done_file.write(f"{url} - {timestamp}\n")
        
        # Mark URL as processed in Redis and update in-memory set
        mark_url_processed(url, processed_urls)
        return True
    else:
        # Log the specific error from the output
        logging.error(f"Error occurred while forwarding: {clean_url}")
        time.sleep(5)  # Retry after 5 seconds
        return False

def process_urls(processed_urls):
    """Continuously processes URLs from url-forward.txt one by one."""
    try:
        with open("url-forward.txt", "r") as f:
            first_line = f.readline().strip()

        # Check if the file is empty 
        if not first_line:
            logging.info("url-forward.txt is empty. Stopping script.")
            return False

        if process_url(first_line, processed_urls):
            with open("url-forward.txt", "r") as f:
                lines = f.readlines()
            with open("url-forward.txt", "w") as f:
                f.writelines(lines[1:])  # Write all lines except the first
    except FileNotFoundError:
        logging.info("url-forward.txt not found. Stopping script.")
        return False  # Indicate script should stop

    return True  # Continue if the file was not empty


if __name__ == "__main__":
    # Load all processed URLs once at the start
    processed_urls = get_processed_urls()
    logging.info(f"Loaded {len(processed_urls)} previously processed URLs")
    
    # If Redis is available, sync file data to Redis
    if redis_available:
        sync_redis_from_file()
    
    while process_urls(processed_urls):
        time.sleep(0.01)  # Check for new URLs every 0.01 second
