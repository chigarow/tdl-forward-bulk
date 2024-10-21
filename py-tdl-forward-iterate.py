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

def process_url(base_url, number):
    """Processes a single URL using tdl."""
    url = f"{base_url}/{number}"
    logging.info(f"Processing URL: {url}")
    error_occurred = False

    process = subprocess.Popen(
        ["tdl", "forward", "--from", url, "--single"],
        stdout=subprocess.PIPE,  
        stderr=subprocess.STDOUT, 
        text=True, 
        bufsize=1  # Line buffering
    )

    for line in iter(process.stdout.readline, ""):  # Iterate over the output lines
        logging.info(line.strip())
        if "Error" in line or "invalid message" in line:
            error_occurred = True

    # Wait for the process to finish
    process.wait()

    if process.returncode == 0 and not error_occurred:
        logging.info(f"Successfully forwarded: {url}")
        # Add the URL to done-url.txt with a timestamp
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open("done-url.txt", "a") as done_file:
            done_file.write(f"{url} - {timestamp}\n")
        return True
    else:
        logging.error(f"Error occurred while forwarding: {url}")
        return False

def process_urls(base_url, start_number, end_number):
    """Processes URLs from base_url with numbers from start_number to end_number."""
    for number in range(start_number, end_number + 1):
        success = process_url(base_url, number)
        if not success:
            logging.info(f"Retrying URL {base_url}/{number} after a 5-second delay.")
            time.sleep(0.5)  # Wait before continuing to the next URL

if __name__ == "__main__":
    base_url = "https://t.me/c/1877657920"  # Define your base URL here
    start_number = 1298  # Define your start number here
    end_number = 2756  # Define your end number here

    process_urls(base_url, start_number, end_number)
