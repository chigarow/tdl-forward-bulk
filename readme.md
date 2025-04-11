# Telegram CLI Forwarder

This project uses the Telegram CLI (`tdl`) to automate the forwarding of messages from a specific Telegram channel or chat via command-line interface (CLI). It offers three main scripts for different forwarding tasks: `py-tdl-forward.py`, `py-tdl-forward-iterate.py`, and `termux-put-into-url-forward.py`.


## Features

- **`py-tdl-forward.py`**: Processes a list of URLs from a file (`url-forward.txt`) and forwards them one by one.
- **`py-tdl-forward-iterate.py`**: Iterates through a range of message numbers from a base URL and forwards them automatically.
- **`termux-put-into-url-forward.py`**: Android script for Termux that monitors clipboard for Telegram links and adds them to your forwarding list.


## Requirements

- Python 3.6+
- `tdl` (Telegram CLI)
- The Python package `psutil`
- For Android: Termux and Termux:API


## Setup

1. **Clone the repository:**

       
       git clone https://github.com/chigarow/tdl-forward-bulk
       cd tdl-forward-bulk

2. **Create a virtual environment:**

   It is recommended to use `venv` for isolating the project's dependencies.

       
       python3 -m venv venv
       
3. **Activate the virtual environment:**

   - On macOS/Linux:

         source venv/bin/activate

   - On Windows:

         .\venv\Scripts\activate

4. **Install the required dependencies:**

   After activating the virtual environment, install the required Python packages by running:

       pip install -r requirements.txt

   The only dependency currently listed is `psutil`.

5. **Install the Telegram CLI (tdl):**

   Make sure you have `tdl` installed on your system. Follow the installation instructions from the [official tdl documentation](https://github.com/vysheng/tg).


## Usage

There are three scripts you can use, depending on your needs:


### 1. Forwarding URLs from a file (`py-tdl-forward.py`)

This script reads URLs from a file (`url-forward.txt`) and forwards them using `tdl`. It processes each URL one by one.

1. **Edit `url-forward.txt`:**\
   Add the URLs you want to forward. Each URL should be on a new line.

2. **Run the script:**

       python3 py-tdl-forward.py

   The script will process each URL and log the results. If a URL is successfully forwarded, it will be logged into the `done-url.txt` file.


### 2. Forwarding messages by number range (`py-tdl-forward-iterate.py`)

This script generates URLs from a base URL by appending a range of message numbers, then forwards each message using `tdl`.

1. **Edit the base URL and range:**\
   Modify the following variables in the script to suit your Telegram channel and message range:

    ```
       base_url = "https://t.me/c/1877657920"  # Your Telegram channel URL
       start_number = 1298  # Starting message number
       end_number = 2756  # Ending message number
    ```

2. **Run the script:**
    ```
       python py-tdl-forward-iterate.py
    ```
   The script will process each message number in the range and log the results. If a URL is successfully forwarded, it will be logged into the `done-url.txt` file.


### 3. Android setup with Termux (`termux-put-into-url-forward.py`)

This script monitors your Android clipboard for Telegram links and automatically adds them to your forwarding list.

1. **Install Termux on your Android device:**
   - Download and install Termux from [F-Droid](https://f-droid.org/packages/com.termux/) (recommended) or Google Play Store
   - Open Termux and wait for the initial setup to complete

2. **Install required packages:**
   ```
   pkg update
   pkg upgrade
   pkg install python
   pkg install git
   pkg install termux-api
   ```

3. **Install the Termux:API app:**
   - Download and install Termux:API from [F-Droid](https://f-droid.org/packages/com.termux.api/) or Google Play Store
   - Grant necessary permissions when prompted

4. **Clone the repository:**
   ```
   git clone https://github.com/chigarow/tdl-forward-bulk
   cd tdl-forward-bulk
   ```

5. **Make the script executable:**
   ```
   chmod +x termux-put-into-url-forward.py
   ```

6. **Run the script:**
   ```
   python termux-put-into-url-forward.py
   ```

7. **How to use:**
   - Keep the script running in Termux
   - When browsing Telegram, copy any message link you want to forward
   - The script will automatically detect the link and add it to `url-forward.txt`
   - You can later use `py-tdl-forward.py` to process these links

8. **Run in the background (optional):**
   - To keep the script running even when Termux is closed:
     ```
     nohup python termux-put-into-url-forward.py &
     ```
   - To stop the background process later:
     ```
     pkill -f termux-put-into-url-forward.py
     ```


## Logging

- The scripts log messages to the console. For file-based logging, you can uncomment the `logging.FileHandler` line in the `logging.basicConfig()` setup section of the scripts.


## Notes

- The `tdl` CLI must be configured properly to interact with your Telegram account. Ensure that you have set up `tdl` and authorized it to access your Telegram data.
- The scripts handle simple errors and retries. If a URL fails to forward, it will retry after a brief delay.
- On Android, ensure that battery optimization is disabled for Termux if you want the script to run for extended periods.


## License

This project is licensed under the MIT License. See the [LICENSE]() file for details.
