import subprocess
import time
import logging
from datetime import datetime

# Set up logging to console and file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s',
    handlers=[
        # logging.FileHandler("forward_log.txt"),  # File handler
        logging.StreamHandler()  # Console handler
    ]
)

def process_url(url):
    """Processes a single URL using tdl."""
    clean_url = url.replace("?single", "")
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
        return True
    else:
        # Log the specific error from the output
        logging.error(f"Error occurred while forwarding: {clean_url}")
        time.sleep(5)  # Retry after 5 seconds
        return False

def process_urls():
    """Continuously processes URLs from url-forward.txt one by one."""
    try:
        with open("url-forward.txt", "r") as f:
            first_line = f.readline().strip()

        # Check if the file is empty 
        if not first_line:
            logging.info("url-forward.txt is empty. Stopping script.")
            return False

        if process_url(first_line):
            with open("url-forward.txt", "r") as f:
                lines = f.readlines()
            with open("url-forward.txt", "w") as f:
                f.writelines(lines[1:])  # Write all lines except the first
    except FileNotFoundError:
        logging.info("url-forward.txt not found. Stopping script.")
        return False  # Indicate script should stop

    return True  # Continue if the file was not empty


if __name__ == "__main__":
    while process_urls():
        time.sleep(0.01)  # Check for new URLs every 0.01 second
