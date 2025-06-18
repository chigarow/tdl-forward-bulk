import pyperclip
import time
import os
from datetime import datetime, timezone, timedelta

def normalize_url(url):
    """Remove '?single' parameter from telegram URLs"""
    if "?single" in url:
        return url.replace("?single", "")
    return url

def ensure_newline_at_end(file_path):
    """Ensure the file ends with a newline character"""
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        with open(file_path, 'r+') as file:
            # Move to the end of file
            file.seek(0, os.SEEK_END)
            if file.tell() > 0:
                # Move back one character
                file.seek(file.tell() - 1, os.SEEK_SET)
                # Read last character
                last_char = file.read(1)
                # If last character is not a newline, add one
                if last_char != '\n':
                    file.write('\n')

def get_timestamp_gmt7():
    """Returns the current timestamp in GMT+7 format"""
    gmt7 = timezone(timedelta(hours=7))
    now_gmt7 = datetime.now(gmt7)
    return now_gmt7.strftime("%Y-%m-%d %H:%M:%S %Z%z")

def load_done_links(done_file_path):
    """Load all links from done-url.txt, ignoring timestamps and normalizing URLs"""
    done_links = set()
    if os.path.exists(done_file_path):
        with open(done_file_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Only take the link part before ' - ' if present
                link = line.split(' - ')[0]
                # Normalize the URL by removing ?single parameter
                normalized_link = normalize_url(link)
                done_links.add(normalized_link)
    return done_links

def main():
    print("Monitoring clipboard for Telegram links...")
    print("Press Ctrl+C to stop")
    
    # Path to the url-forward.txt file
    file_path = os.path.join(os.path.dirname(__file__), "url-forward.txt")
    done_file_path = os.path.join(os.path.dirname(__file__), "done-url.txt")
    # Ensure file ends with newline
    ensure_newline_at_end(file_path)
    
    # Initialize with current clipboard to ignore initial content
    last_copied = pyperclip.paste().strip()
    print("Initial clipboard content ignored. Waiting for new Telegram links...")
    
    try:
        while True:
            # Get current clipboard content
            current_clipboard = pyperclip.paste().strip()
            
            # Check if it's a new content and contains a Telegram link
            if current_clipboard != last_copied and "https://t.me/" in current_clipboard:
                # Make sure it's a valid URL (basic check)
                if current_clipboard.startswith("https://"):
                    # Load done links for each check
                    done_links = load_done_links(done_file_path)
                    link_only = current_clipboard.split(' - ')[0]
                    # Normalize the URL before checking if it exists in done_links
                    normalized_link = normalize_url(link_only)
                    if normalized_link in done_links:
                        print(f"[{get_timestamp_gmt7()}] Link already in done-url.txt, skipping: {link_only}")
                    else:
                        timestamp = get_timestamp_gmt7()
                        print(f"[{timestamp}] Found Telegram link: {current_clipboard}")
                        
                        # Ensure file ends with newline before appending
                        ensure_newline_at_end(file_path)
                        
                        # Append to file
                        with open(file_path, 'a') as file:
                            file.write(current_clipboard + "\n")
                        
                        print(f"[{timestamp}] Link added to url-forward.txt")
            
            # Update last copied text regardless of whether it was added to file
            last_copied = current_clipboard
            
            # Sleep to reduce CPU usage
            time.sleep(0.5)
    
    except KeyboardInterrupt:
        print("\nMonitoring stopped")

if __name__ == "__main__":
    # Check if pyperclip is installed
    try:
        import pyperclip
    except ImportError:
        print("The pyperclip module is not installed. Installing...")
        import subprocess
        subprocess.check_call(["pip3", "install", "pyperclip"])
        print("pyperclip installed successfully!")
    
    main()