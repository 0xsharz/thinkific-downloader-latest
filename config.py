import os
import sys
from dotenv import load_dotenv

# Load env.sample file
load_dotenv()


class Config:
    COURSE_LINK = os.getenv("COURSE_LINK")
    COOKIE_DATA = os.getenv("COOKIE_DATA")
    CLIENT_DATE = os.getenv("CLIENT_DATE")
    QUALITY = os.getenv("VIDEO_DOWNLOAD_QUALITY", "720p")

    # Logging Config
    LOG_FILE = "downloader.log"

    # Base headers required for Thinkific API
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Cookie": COOKIE_DATA,
        # "Date": CLIENT_DATE # Sometimes strict date headers cause issues if system time drifts, usually safe to omit or keep if strictly required.
    }

    if CLIENT_DATE:
        HEADERS["Date"] = CLIENT_DATE

    @staticmethod
    def validate():
        if not Config.COOKIE_DATA:
            print("Error: COOKIE_DATA must be set in the env.sample file.")
            sys.exit(1)
        if not Config.COURSE_LINK:
            print("Error: COURSE_LINK must be set in the env.sample file.")
            sys.exit(1)