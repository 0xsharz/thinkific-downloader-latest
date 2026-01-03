import os
import re
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, Tuple


# --- Logging Setup ---
def setup_logging(log_file: str = "downloader.log"):
    """Configures logging to both console and file."""
    # Clear existing handlers to avoid duplicates if re-initialized
    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers = []

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    return logging.getLogger(__name__)


logger = logging.getLogger(__name__)


# --- Networking ---
def get_robust_session() -> requests.Session:
    """
    Creates a requests Session with automatic retries for robust networking.
    Retries on 500, 502, 503, 504 errors and connection timeouts.
    """
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,  # Wait 1s, 2s, 4s... between retries
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["HEAD", "GET", "OPTIONS"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# --- File Operations ---
def sanitize_filename(name: str, max_length: int = 50) -> str:
    """
    Sanitizes a string for filenames:
    1. Removes illegal characters.
    2. Replaces spaces/dots with underscores.
    3. Truncates to max_length.
    """
    name = str(name)
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = name.replace(' ', '_')
    name = name.replace('.', '_')

    if len(name) > max_length:
        name = name[:max_length]

    return name.strip('_')


def create_directory(path: str):
    """Creates a directory if it doesn't exist."""
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            logger.error(f"Failed to create directory {path}: {e}")


def save_text_file(path: str, content: str):
    """Saves text content to a file."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
    except OSError as e:
        logger.error(f"Failed to save text file {path}: {e}")


# --- Wistia Operations ---
def extract_wistia_id_from_page(url: str, session: requests.Session, headers: dict) -> Optional[str]:
    """Scrapes the video player page to find the Wistia Embed ID."""
    logger.debug(f"Scraping Player Page: {url}")
    try:
        response = session.get(url, headers=headers)
        response.raise_for_status()
        content = response.text

        if "Log In" in content and "password" in content:
            logger.error("Login page detected. Cookie likely expired.")
            return None

        match = re.search(r'fast\.wistia\.(?:com|net)/embed/medias/([a-zA-Z0-9]+)\.', content)
        if match: return match.group(1)

        match = re.search(r'/embed/medias/([a-zA-Z0-9]+)', content)
        if match: return match.group(1)

    except Exception as e:
        logger.error(f"Error scraping page {url}: {e}")

    return None


def get_wistia_bin_url(wistia_id: str, session: requests.Session, target_quality: str = '720p') -> Tuple[
    Optional[str], Optional[str]]:
    """Fetches Wistia metadata and finds the .bin file matching the target quality."""
    if not wistia_id: return None, None

    try:
        wistia_json_url = f"https://fast.wistia.com/embed/medias/{wistia_id}.json"
        logger.debug(f"Fetching Wistia JSON: {wistia_json_url}")

        w_response = session.get(wistia_json_url)
        w_response.raise_for_status()
        w_data = w_response.json()

        assets = w_data.get('media', {}).get('assets', [])

        for asset in assets:
            if asset.get('display_name') == target_quality:
                return asset['url'], target_quality

        # Fallback
        for asset in assets:
            if asset.get('display_name') == '720p':
                return asset['url'], '720p'

    except Exception as e:
        logger.error(f"Error parsing Wistia JSON for ID {wistia_id}: {e}")

    return None, None
