# Telegram CLI Forwarder

This project uses the Telegram CLI (`tdl`) to automate the forwarding of messages from a specific Telegram channel or chat via command-line interface (CLI). It includes both Python scripts for manual forwarding and a Telegram bot (`tdl-forward-bot.py`) for automated queue-based forwarding.


## Features

### Python Scripts
- **`py-tdl-forward.py`**: Processes a list of URLs from a file (`url-forward.txt`) and forwards them one by one.
- **`py-tdl-forward-iterate.py`**: Iterates through a range of message numbers from a base URL and forwards them automatically.
- **`termux-put-into-url-forward.py`**: Android script for Termux that monitors clipboard for Telegram links and adds them to your forwarding list.

### Telegram Bot (`tdl-forward-bot.py`)
A fully-featured Telegram bot for managing message forwarding with:
- **Queue Management**: Add multiple URLs and process them sequentially
- **URL Range Support**: Send ranges like `https://t.me/channel/100 - https://t.me/channel/110` to auto-generate and queue all messages in the range
- **Bulk Forwarding**: Submit multiple links at once with batch tracking
- **Progress Monitoring**: Real-time progress updates with speed and ETA
- **Duplicate Detection**: Automatic checking against processed, queued, and in-progress URLs
- **Redis Caching**: Optional Redis integration for ultra-fast duplicate detection and improved performance
- **User Authentication**: Password-protected access
- **Admin Notifications**: Error alerts sent to configured admin chat
- **Persistent State**: Queue survives bot restarts
- **Performance Optimized**: Uses 16 threads and unlimited DC pool for maximum speed (2-5 MB/s)

### Redis Integration Benefits

Both `py-tdl-forward.py` and `tdl-forward-bot.py` support Redis for improved performance:

**Performance Improvements:**
- **10-100x faster duplicate detection**: O(1) Redis lookup vs O(n) file scanning
- **Reduced disk I/O**: In-memory caching reduces file system operations
- **Better scalability**: Handles thousands of URLs efficiently
- **Instant startup**: No need to load entire finished.txt into memory

**How It Works:**
1. On startup, the bot syncs existing URLs from `finished.txt` into Redis
2. Duplicate checks query Redis first (if available) before checking files
3. Processed URLs are stored in both Redis and files for redundancy
4. Automatic fallback to file-based tracking if Redis is unavailable

**Redis Key Used:**
- Bot: `tdl:bot:processed_urls`
- Script: `tdl:processed_urls`

**Testing:**
All Redis functionality is thoroughly tested with 16 unit tests covering:
- Connection establishment and fallback
- URL normalization and deduplication
- Sync from files to Redis
- Error handling and graceful degradation
- Performance with bulk operations


## Requirements

- Python 3.6+
- `tdl` (Telegram CLI) - [Installation Guide](https://docs.iyear.me/tdl/)
- Python packages: `psutil`, `python-telegram-bot`, `redis`
- Redis server (optional, for improved performance)
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

   - On Android (Termux):

         source venv/bin/activate

5. **Install the required dependencies:**

   After activating the virtual environment, install the required Python packages by running:

       pip install -r requirements.txt

6. **Install and configure Redis (Optional but Recommended):**

   Redis provides significant performance improvements for duplicate detection and URL caching.

   **For macOS:**
   ```bash
   brew install redis
   brew services start redis
   ```

   **For Linux:**
   ```bash
   sudo apt-get install redis-server
   sudo systemctl start redis-server
   sudo systemctl enable redis-server
   ```

   **For Android (Termux):**
   ```bash
   pkg install redis
   redis-server --daemonize yes
   ```

   **Verify Redis is running:**
   ```bash
   redis-cli ping
   # Should return: PONG
   ```

   **Note:** The bot will automatically fall back to file-based tracking if Redis is unavailable. However, Redis is highly recommended for:
   - Faster duplicate detection (O(1) lookup vs file scanning)
   - Better performance with large histories
   - Reduced disk I/O

7. **Configure the Telegram Bot (Optional):**

   If you want to use the bot interface:
   
   a. Create a `secrets.properties` file in the project directory:
   ```
   [DEFAULT]
   BOT_TOKEN = your_telegram_bot_token_here
   PASSWORD = your_bot_password_here
   ADMIN_CHAT_ID = your_telegram_chat_id_for_errors
   # Redis configuration (optional, defaults shown)
   REDIS_HOST = 127.0.0.1
   REDIS_PORT = 6379
   REDIS_DB = 0
   # Logging configuration (optional, defaults shown)
   LOG_LEVEL = INFO
   ```
   
   **Log Levels:**
   - `DEBUG`: Detailed logs including duplicate checks and all operations (use for troubleshooting)
   - `INFO`: Standard logs with processing start/end, errors, and important events (recommended)
   - `WARNING`: Only warnings and errors
   - `ERROR`: Only errors
   
   **Note:** The bot automatically filters out TDL progress output (percentage, ETA, speed) at all log levels to prevent flooding `nohup.out`. You'll only see clean start/completion logs.
   
   b. Get your bot token from [@BotFather](https://t.me/BotFather) on Telegram
   
   c. Set a password for user authentication
   
   d. Use `/set_admin` command in the bot to configure admin notifications

8. **Install the Telegram CLI (tdl):**

   Make sure you have `tdl` installed on your system. Follow the installation instructions from the [official tdl documentation](https://docs.iyear.me/tdl/).

## Usage


### 0. Using the Telegram Bot (Recommended)

The bot provides the easiest and most feature-rich way to forward messages.

1. **Start the bot:**
   ```bash
   python3 tdl-forward-bot.py
   ```

2. **Authenticate:**
   - Send the password you configured in `secrets.properties` to the bot
   - You'll see: "✅ You are now authenticated! You can use the bot."

3. **Forward messages:**
   - Simply send Telegram URLs to the bot (one or multiple per message)
   - **URL Range Support**: Send a range like `https://t.me/channel/100 - https://t.me/channel/110` to auto-generate and queue all messages from 100 to 110
   - **Mixed Input Support**: Combine ranges and individual URLs in a single message
   - The bot will queue them and process sequentially
   - Get real-time progress updates with speed and ETA (logged every 15 seconds)

4. **URL Range and Mixed Input Examples:**
   ```
   # Single range - generates URLs from 69748 to 69754
   https://t.me/Meetingroom18/69748 - https://t.me/Meetingroom18/69754
   
   # Result: Bot automatically generates and queues:
   # https://t.me/Meetingroom18/69748
   # https://t.me/Meetingroom18/69749
   # https://t.me/Meetingroom18/69750
   # https://t.me/Meetingroom18/69751
   # https://t.me/Meetingroom18/69752
   # https://t.me/Meetingroom18/69753
   # https://t.me/Meetingroom18/69754
   
   # Mixed input - ranges and individual URLs in one message
   https://t.me/Meetingroom18/69748 - https://t.me/Meetingroom18/69826
   https://t.me/Meetingroom18/69848?single
   https://t.me/Meetingroom18/69854
   https://t.me/Meetingroom18/69858
   
   # Result: Bot processes:
   # - All URLs from 69748 to 69826 (79 URLs from range)
   # - Plus 3 individual URLs (69848, 69854, 69858)
   # - Total: 82 URLs in queue, all normalized (no ?single)
   
   # Multiple ranges in one message
   https://t.me/channel/10 - https://t.me/channel/15
   https://t.me/channel/20 - https://t.me/channel/25
   https://t.me/channel/100
   
   # Result: Generates 6 URLs from first range, 6 from second, plus 1 individual = 13 total
   ```
   
   **Range Limitations:**
   - Maximum 1000 URLs per range (to prevent abuse)
   - Start message ID must be ≤ end message ID
   - Works with both `t.me` and `telegram.me` domains
   - Supports private chats (`/c/...`) format
   - Automatic duplicate detection still applies to generated URLs

5. **Available Commands:**
   - `/status` - Show current processing link with progress details
   - `/q [page]` - View queue (paginated, 20 per page)
   - `/finished_url [page]` - View completed forwards (paginated)
   - `/failed [page]` - View failed forwards with timestamps (paginated)
   - `/remove <url>` - Remove a specific URL from queue
   - `/clear` - Clear entire queue
   - `/empty_finished` - Clear finished URLs list
   - `/delete_link_finished <url>` - Remove specific URL from finished list
   - `/sanitize_finished_urls` - Normalize and deduplicate finished.txt
   - `/set_admin` - Set current chat for error notifications

6. **Features:**
   - **URL Range Expansion**: Send `URL1 - URL2` to auto-generate all intermediate URLs
   - **Mixed Input Support**: Combine multiple ranges and individual URLs in a single message
   - **Periodic Progress Logging**: Progress (percentage, ETA, speed) logged every 15 seconds at INFO level
   - Bulk forwarding: Send multiple URLs at once, get summary when done
   - Automatic duplicate detection across queue, processing, and finished lists
   - Progress tracking: Real-time percentage, ETA, and transfer speed via `/status` command
   - Persistent queue: Survives bot restarts
   - Performance optimized: 16 threads, unlimited DC pool (2-5 MB/s typical)

   Note: The `/failed` command shows the newest failed entries first (newest on page 1). Use `/failed <page>` to navigate older failures. This ordering is intentional to make it easier to spot recent problems quickly.


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


## Logging

The bot uses a clean, optimized logging system designed to prevent log file bloat while maintaining essential information for debugging.

### Log Levels

Configure the log level in `secrets.properties`:
```
LOG_LEVEL = INFO
```

Available levels:
- **DEBUG**: Detailed logs including duplicate checks, Redis operations, and all events (verbose)
- **INFO** (recommended): Standard logs with processing start/end, errors, and state changes
- **WARNING**: Only warnings and errors
- **ERROR**: Only errors

### What Gets Logged

**Always logged (at INFO level):**
- Bot startup and initialization
- User authentication events
- Processing start: `▶ Processing: <url>`
- **Periodic progress updates**: `📊 Progress: X% | ⏱️ ETA: Xm | 🚀 Speed: X MB/s` (logged every 15 seconds during transfers)
- Processing completion: `✓ Completed: <url> (took X seconds)`
- Processing failures: `✗ Failed: <url> (return code: X)`
- Redis sync operations
- Errors and exceptions

**Filtered out (to prevent log flooding):**
- Real-time TDL progress output lines (raw percentage updates from TDL every second)
- Individual duplicate checks (logged at DEBUG level only)
- Every user message (only commands are logged)

**Note**: Progress information (percentage, ETA, speed) is logged periodically (every 15 seconds) to provide visibility into long-running transfers without flooding logs. You can also use `/status` command in the bot to see real-time progress at any time.

### Example Clean Log Output

```
2025-10-08 15:23:30,100 - INFO: Redis connection established
2025-10-08 15:23:30,150 - INFO: Redis sync complete: 5000 URLs loaded
2025-10-08 15:23:30,200 - INFO: Bot started. Waiting for messages...
2025-10-08 15:23:45,300 - INFO: User authenticated: John (12345)
2025-10-08 15:24:10,500 - INFO: ▶ Processing: https://t.me/example/123
2025-10-08 15:24:25,500 - INFO: 📊 Progress: 15.2% | ⏱️ ETA: 1m30s | 🚀 Speed: 1.85 MB/s
2025-10-08 15:24:40,500 - INFO: 📊 Progress: 35.8% | ⏱️ ETA: 1m05s | 🚀 Speed: 2.05 MB/s
2025-10-08 15:24:55,500 - INFO: 📊 Progress: 58.3% | ⏱️ ETA: 45s | 🚀 Speed: 2.13 MB/s
2025-10-08 15:25:10,500 - INFO: 📊 Progress: 82.1% | ⏱️ ETA: 20s | 🚀 Speed: 2.18 MB/s
2025-10-08 15:25:25,800 - INFO: ✓ Completed: https://t.me/example/123 (took 1 minute 15 seconds)
2025-10-08 15:25:30,100 - INFO: ▶ Processing: https://t.me/example/456
2025-10-08 15:26:30,400 - INFO: ✓ Completed: https://t.me/example/456 (took 1 minute)
```

### Troubleshooting

If you need more detailed logs for debugging:
1. Set `LOG_LEVEL = DEBUG` in `secrets.properties`
2. Restart the bot
3. Check logs for detailed duplicate checks, Redis operations, and all events
4. Remember to set back to `INFO` after troubleshooting to avoid log bloat

## Notes

- The `tdl` CLI must be configured properly to interact with your Telegram account. Ensure that you have set up `tdl` and authorized it to access your Telegram data.
- The scripts handle simple errors and retries. If a URL fails to forward, it will retry after a brief delay.
- On Android, ensure that battery optimization is disabled for Termux if you want the script to run for extended periods.


## License

This project is licensed under the MIT License. See the [LICENSE]() file for details.
