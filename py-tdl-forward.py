import subprocess
import time
import logging
from datetime import datetime, timezone, timedelta
import os

# Set up logging to console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        # logging.FileHandler("forward_log.txt"),  # File handler
        logging.StreamHandler()  # Console handler
    ]
)

def get_timestamp_gmt7():
    """Returns the current timestamp in GMT+7 format"""
    gmt7 = timezone(timedelta(hours=7))
    now_gmt7 = datetime.now(gmt7)
    return now_gmt7.strftime("%Y-%m-%d %H:%M:%S")

def load_done_links(done_file_path):
    """Load all links from done-url.txt, ignoring timestamps"""
    done_links = set()
    if os.path.exists(done_file_path):
        with open(done_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                link = line.split(' - ')[0]
                done_links.add(link)
    return done_links

def process_url(url):
    """Processes a single URL using tdl."""
    clean_url = url.replace("?single", "")
    logging.info(f"Processing URL: {clean_url}")
    error_occurred = False
    deleted_message = False

    process = subprocess.Popen(
        ["tdl", "forward", "--from", clean_url],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1  # Line buffering
    )

    for line in iter(process.stdout.readline, ""):
        logging.info(line.strip())
        if "Error" in line:
            error_occurred = True
        if "may be deleted" in line:
            deleted_message = True

    process.wait()

    if deleted_message:
        logging.warning(f"Message has been deleted: {clean_url}")
        timestamp = get_timestamp_gmt7()
        with open("deleted-messages-url.txt", "a") as deleted_file:
            deleted_file.write(f"{url} - {timestamp}\n")
        return True
    elif process.returncode == 0 and not error_occurred:
        logging.info(f"Successfully forwarded: {clean_url}")
        timestamp = get_timestamp_gmt7()
        with open("done-url.txt", "a") as done_file:
            done_file.write(f"{url} - {timestamp}\n")
        return True
    else:
        logging.error(f"Error occurred while forwarding: {clean_url}")
        time.sleep(5)
        return False

def process_urls():
    """Continuously processes URLs from url-forward.txt one by one, skipping duplicates."""
    done_file_path = "done-url.txt"
    duplicate_file_path = "duplicate-url.txt"
    try:
        with open("url-forward.txt", "r") as f:
            first_line = f.readline().strip()

        if not first_line:
            logging.info("url-forward.txt is empty. Stopping script.")
            return False

        # Check for duplication
        done_links = load_done_links(done_file_path)
        link_only = first_line.split(' - ')[0]
        if link_only in done_links:
            timestamp = get_timestamp_gmt7()
            logging.info(f"Duplicate found, moving to duplicate-url.txt: {link_only}")
            with open(duplicate_file_path, "a") as dup_file:
                dup_file.write(f"{first_line} - {timestamp}\n")
            # Remove the first line from url-forward.txt
            with open("url-forward.txt", "r") as f:
                lines = f.readlines()
            with open("url-forward.txt", "w") as f:
                f.writelines(lines[1:])
            return True  # Continue processing

        # Not a duplicate, process as usual
        if process_url(first_line):
            with open("url-forward.txt", "r") as f:
                lines = f.readlines()
            with open("url-forward.txt", "w") as f:
                f.writelines(lines[1:])
    except FileNotFoundError:
        logging.info("url-forward.txt not found. Stopping script.")
        return False

    return True

if __name__ == "__main__":
    while process_urls():
        time.sleep(0.01)
