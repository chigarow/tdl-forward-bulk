import pyperclip
import time
import os

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

def main():
    print("Monitoring clipboard for Telegram links...")
    print("Press Ctrl+C to stop")
    
    # Path to the url-forward.txt file
    file_path = os.path.join(os.path.dirname(__file__), "url-forward.txt")
    
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
                    print(f"Found Telegram link: {current_clipboard}")
                    
                    # Ensure file ends with newline before appending
                    ensure_newline_at_end(file_path)
                    
                    # Append to file
                    with open(file_path, 'a') as file:
                        file.write(current_clipboard + "\n")
                    
                    print("Link added to url-forward.txt")
            
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