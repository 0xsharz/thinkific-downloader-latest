import os
import sys
import time
import requests
import yt_dlp
from tqdm import tqdm
from config import Config
from utlis import (
    setup_logging,
    get_robust_session,
    sanitize_filename,
    create_directory,
    save_text_file,
    extract_wistia_id_from_page,
    get_wistia_bin_url
)

# Initialize Logger
logger = setup_logging(Config.LOG_FILE)

# Initialize Session
session = get_robust_session()


def fetch_course_data(url: str) -> dict:
    """Fetches the main course syllabus."""
    logger.info(f"Fetching course syllabus from: {url}")
    try:
        response = session.get(url, headers=Config.HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.critical(f"Error fetching course data: {e}")
        logger.critical("Check your COOKIE_DATA and CLIENT_DATE in env.sample")
        sys.exit(1)


def fetch_lesson_details(contentable_id: int) -> dict:
    """STEP 2: API Call to get lesson details."""
    base_url = "https://courses.thorteaches.com"
    api_url = f"{base_url}/api/course_player/v2/lessons/{contentable_id}"

    try:
        resp = session.get(api_url, headers=Config.HEADERS)
        if resp.status_code == 401:
            logger.critical("401 Unauthorized. Your cookie has expired.")
            sys.exit(1)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching lesson API ({contentable_id}): {e}")
        return None


def download_with_ytdlp(url: str, output_path: str, filename: str):
    """
    Uses yt-dlp to download the file and forces .mp4 extension.
    """
    if not filename.lower().endswith('.mp4'):
        filename += ".mp4"

    final_path = os.path.join(output_path, filename)

    if os.path.exists(final_path):
        logger.info(f"Video already exists: {filename}")
        return

    logger.info(f"Downloading video via yt-dlp: {filename}")

    ydl_opts = {
        'outtmpl': os.path.join(output_path, filename),
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        # 'progress_hooks': [lambda d: ...], # Could hook tqdm here, but yt-dlp default is okay
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        logger.info("Download complete.")
    except Exception as e:
        logger.error(f"yt-dlp failed: {e}")
        logger.warning("Trying fallback download...")
        download_file_requests(url, output_path, filename)


def download_file_requests(url: str, output_path: str, filename: str):
    """Fallback / Standard file downloader using requests with tqdm progress bar."""
    final_path = os.path.join(output_path, filename)
    if os.path.exists(final_path):
        logger.info(f"File already exists: {filename}")
        return

    logger.info(f"Downloading: {filename}")

    try:
        # Stream response to allow progress bar
        with session.get(url, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            block_size = 8192

            with open(final_path, 'wb') as f, tqdm(
                    total=total_size, unit='iB', unit_scale=True, desc=filename[:30]
            ) as t:
                for chunk in r.iter_content(chunk_size=block_size):
                    t.update(len(chunk))
                    f.write(chunk)

        logger.info("Download complete.")
    except Exception as e:
        logger.error(f"Download failed: {e}")
        # Clean up partial file
        if os.path.exists(final_path):
            os.remove(final_path)


def process_lesson(lesson_summary: dict, output_dir: str, index: int):
    """Orchestrates the 4-step flow for each lesson."""

    # 1. Sanitize Lesson Name
    raw_name = lesson_summary.get('name', 'Unknown Lesson')
    lesson_name = sanitize_filename(raw_name)

    lesson_prefix = f"{index:02d}_-_"
    full_lesson_name = lesson_prefix + lesson_name

    contentable_id = lesson_summary.get('contentable_id')
    if not contentable_id:
        return

    # --- Contentable Type Check ---
    contentable_type = lesson_summary.get('contentable_type', '')

    if contentable_type != 'Lesson':
        flag_filename = f"{full_lesson_name}_Enough_thinking.txt"
        save_text_file(os.path.join(output_dir, flag_filename), "")
        logger.info(f"Skipped (type is '{contentable_type}'): {full_lesson_name}")
        return

    logger.info(f"Processing: {full_lesson_name}")

    # STEP 2: Get Lesson Details
    lesson_data = fetch_lesson_details(contentable_id)
    if not lesson_data: return

    # --- VIDEO PROCESSING ---
    video_url_player = lesson_data.get('lesson', {}).get('video_url')

    if video_url_player:
        # STEP 3: View Source to find Wistia ID
        wistia_id = extract_wistia_id_from_page(video_url_player, session, Config.HEADERS)

        if wistia_id:
            # STEP 4: Get .bin URL
            bin_url, resolution = get_wistia_bin_url(wistia_id, session, Config.QUALITY)

            if bin_url:
                download_with_ytdlp(bin_url, output_dir, full_lesson_name)
            else:
                logger.warning(f"No suitable video found for quality: {Config.QUALITY}")
        else:
            logger.error("Could not scrape Wistia ID from player page.")

    # --- ATTACHMENTS ---
    download_files = lesson_data.get('download_files', []) + lesson_data.get('attachments', [])
    for file_item in download_files:
        original_fname = file_item.get('file_name') or file_item.get('label') or 'attachment'
        f_url = file_item.get('download_url')

        if f_url:
            # Preserve extension
            if '.' in original_fname:
                stem = original_fname.rsplit('.', 1)[0]
                ext = '.' + original_fname.rsplit('.', 1)[1]
            else:
                stem = original_fname
                ext = ''
                if not ext:
                    url_ext = f_url.split('?')[0].split('.')[-1]
                    if len(url_ext) < 5: ext = f".{url_ext}"

            stem = sanitize_filename(stem)
            final_fname = f"{full_lesson_name}_{stem}{ext}"

            logger.info(f"Found attachment: {final_fname}")
            download_file_requests(f_url, output_dir, final_fname)

    # --- HTML ---
    html_text = lesson_data.get('lesson', {}).get('html_text')
    if html_text:
        save_text_file(os.path.join(output_dir, f"{full_lesson_name}.html"), html_text)

    # Small delay to be polite to the server
    time.sleep(1)


def main():
    Config.validate()

    # 1. Fetch Course Syllabus
    data = fetch_course_data(Config.COURSE_LINK)

    raw_course_name = data.get('course', {}).get('name', 'Course')
    course_name = sanitize_filename(raw_course_name)
    logger.info(f"=== {course_name} ===")

    base_output_dir = os.path.join(os.getcwd(), 'Downloads', course_name)
    create_directory(base_output_dir)

    # 2. Map Contents
    all_contents = data.get('contents', []) + data.get('lessons', [])
    contents_map = {item['id']: item for item in all_contents}

    # 3. Process Chapters
    chapters = data.get('chapters', [])
    for i, chapter in enumerate(chapters, 1):
        raw_chapter_name = chapter.get('name', f'Chapter {i}')
        chapter_name = sanitize_filename(raw_chapter_name)

        chapter_dir_name = f"{i:02d}_-_ {chapter_name}"
        chapter_path = os.path.join(base_output_dir, chapter_dir_name)
        create_directory(chapter_path)

        logger.info(f"Chapter {i}: {chapter_name}")

        content_ids = chapter.get('content_ids', [])
        for j, content_id in enumerate(content_ids, 1):
            lesson = contents_map.get(content_id)
            if lesson:
                process_lesson(lesson, chapter_path, j)

    logger.info("Download Complete")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Script interrupted by user.")
        sys.exit(0)
    except Exception as e:
        logger.critical(f"Unexpected crash: {e}", exc_info=True)
        sys.exit(1)