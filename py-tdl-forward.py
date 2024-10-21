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

    # Wait for the process to finish
    process.wait()

    if process.returncode == 0 and not error_occurred:
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
        time.sleep(1)  # Check for new URLs every 1 second
