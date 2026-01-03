import os
import sys
import time
import requests
import json
import base64
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
        logger.critical("Check your COOKIE_DATA and CLIENT_DATE in .env")
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


def fetch_quiz_details(quiz_id: int) -> dict:
    """Fetches quiz data from the API."""
    base_url = "https://courses.thorteaches.com"
    api_url = f"{base_url}/api/course_player/v2/quizzes/{quiz_id}"

    try:
        resp = session.get(api_url, headers=Config.HEADERS)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"Error fetching quiz API ({quiz_id}): {e}")
        return None


def generate_quiz_html(lesson_name, questions):
    """Generates an interactive HTML string for the quiz."""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{lesson_name}</title>
        <style>
            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; background-color: #f4f4f9; }}
            h1 {{ color: #2c3e50; border-bottom: 2px solid #3498db; padding-bottom: 10px; }}
            .question-card {{ background: #fff; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); padding: 20px; margin-bottom: 25px; }}
            .question-text {{ font-weight: 600; font-size: 1.1em; margin-bottom: 15px; color: #2c3e50; }}
            .options {{ list-style-type: none; padding: 0; }}
            .option {{ background: #f8f9fa; border: 1px solid #dee2e6; padding: 10px 15px; margin-bottom: 8px; border-radius: 4px; cursor: pointer; transition: background 0.2s; }}
            .option:hover {{ background: #e9ecef; }}
            .option.selected {{ border-color: #3498db; background: #ebf5fb; }}
            .option.correct {{ background-color: #d4edda; border-color: #c3e6cb; color: #155724; }}
            .option.wrong {{ background-color: #f8d7da; border-color: #f5c6cb; color: #721c24; }}
            .feedback-section {{ margin-top: 15px; padding: 15px; border-radius: 4px; display: none; }}
            .explanation {{ background-color: #e2e3e5; border-left: 4px solid #3498db; padding: 10px; margin-top: 10px; font-size: 0.95em; }}
            .btn-reveal {{ background-color: #3498db; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-size: 0.9em; margin-top: 10px; }}
            .btn-reveal:hover {{ background-color: #2980b9; }}
        </style>
    </head>
    <body>
        <h1>{lesson_name}</h1>
    """

    for idx, q in enumerate(questions, 1):
        html_content += f"""
        <div class="question-card" id="q{idx}">
            <div class="question-text">{idx}. {q['prompt']}</div>
            <ul class="options">
        """
        for choice in q['choices']:
            is_correct_str = "true" if choice['is_correct'] else "false"
            html_content += f"""<li class="option" onclick="checkAnswer(this, {is_correct_str})">{choice['text']}</li>"""

        html_content += f"""
            </ul>
            <button class="btn-reveal" onclick="toggleExplanation(this)">Show Answer & Explanation</button>
            <div class="feedback-section">
                <div class="explanation"><strong>Explanation:</strong><br>{q['explanation']}</div>
            </div>
        </div>
        """

    html_content += """
        <script>
            function checkAnswer(element, isCorrect) {
                let siblings = element.parentElement.children;
                for(let i=0; i<siblings.length; i++) {
                    siblings[i].classList.remove('selected', 'correct', 'wrong');
                }
                if(isCorrect) { element.classList.add('correct'); } 
                else { element.classList.add('wrong'); }
            }
            function toggleExplanation(btn) {
                let card = btn.parentElement;
                let feedback = card.querySelector('.feedback-section');
                if (feedback.style.display === 'block') {
                    feedback.style.display = 'none';
                    btn.textContent = 'Show Answer & Explanation';
                } else {
                    feedback.style.display = 'block';
                    btn.textContent = 'Hide Answer & Explanation';
                }
            }
        </script>
    </body>
    </html>
    """
    return html_content


def process_quiz(quiz_id, output_dir, full_lesson_name):
    """Orchestrates fetching and generating quiz HTML."""
    logger.info(f"Processing Quiz: {full_lesson_name}")

    data = fetch_quiz_details(quiz_id)
    if not data: return

    try:
        questions_map = {q['id']: q for q in data.get('questions', [])}
        choices_map = {c['id']: c for c in data.get('choices', [])}
        question_ids = data.get('quiz', {}).get('question_ids', [])

        processed_questions = []

        for q_id in question_ids:
            q_data = questions_map.get(q_id)
            if not q_data: continue

            prompt = q_data.get('prompt', '')
            explanation = q_data.get('text_explanation', 'No explanation provided.')
            choice_ids = q_data.get('choice_ids', [])

            q_choices = []
            for c_id in choice_ids:
                c_data = choices_map.get(c_id)
                if not c_data: continue

                # Decode 'credited'
                credited_enc = c_data.get('credited', '')
                is_correct = False
                try:
                    decoded = base64.b64decode(credited_enc).decode('utf-8').lower()
                    if 'true' in decoded: is_correct = True
                except Exception:
                    pass

                q_choices.append({'text': c_data.get('text', ''), 'is_correct': is_correct})

            processed_questions.append({'prompt': prompt, 'explanation': explanation, 'choices': q_choices})

        html_content = generate_quiz_html(full_lesson_name, processed_questions)
        save_text_file(os.path.join(output_dir, f"{full_lesson_name}.html"), html_content)
        logger.info(f"Quiz saved.")

    except Exception as e:
        logger.error(f"Failed to process quiz {full_lesson_name}: {e}")


def download_with_ytdlp(url: str, output_path: str, filename: str):
    """Uses yt-dlp to download video. RESUMABLE (checks size)."""
    if not filename.lower().endswith('.mp4'):
        filename += ".mp4"

    final_path = os.path.join(output_path, filename)

    # --- RESUMABLE CHECK (Feature 1) ---
    if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
        logger.info(f"Skipping (Already exists): {filename}")
        return

    logger.info(f"Downloading video: {filename}")

    ydl_opts = {
        'outtmpl': os.path.join(output_path, filename),
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
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
    """Fallback / Standard downloader. RESUMABLE (checks size)."""
    final_path = os.path.join(output_path, filename)

    # --- RESUMABLE CHECK (Feature 1) ---
    if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
        logger.info(f"Skipping (Already exists): {filename}")
        return

    logger.info(f"Downloading: {filename}")

    try:
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
        if os.path.exists(final_path): os.remove(final_path)


def ask_user_for_chapters(chapters: list) -> list:
    """Asks user to select chapters (Feature 2)."""
    print("\n" + "=" * 40 + "\n       AVAILABLE CHAPTERS\n" + "=" * 40)
    for i, chapter in enumerate(chapters, 1):
        c_name = chapter.get('name', f"Chapter {i}").strip()
        print(f" [{i}] {c_name}")

    print("=" * 40)
    print("Enter chapter numbers (e.g., 'all', '1,3,5', '1-5')")
    selection = input("\nSelect Chapters > ").strip()

    if not selection or selection.lower() == 'all':
        return list(range(1, len(chapters) + 1))

    selected_indices = set()
    try:
        parts = selection.split(',')
        for part in parts:
            part = part.strip()
            if '-' in part:
                start, end = map(int, part.split('-'))
                selected_indices.update(range(start, end + 1))
            else:
                if part.isdigit(): selected_indices.add(int(part))
    except ValueError:
        logger.error("Invalid input. Defaulting to ALL chapters.")
        return list(range(1, len(chapters) + 1))

    return sorted(list(selected_indices))


def process_lesson(lesson_summary: dict, output_dir: str, index: int):
    """Orchestrates the flow for each lesson."""

    raw_name = lesson_summary.get('name', 'Unknown Lesson')
    lesson_name = sanitize_filename(raw_name)
    full_lesson_name = f"{index:02d}_-_ {lesson_name}"

    contentable_id = lesson_summary.get('contentable_id')
    if not contentable_id: return

    contentable_type = lesson_summary.get('contentable_type', '')

    # 1. QUIZ HANDLING
    if contentable_type == 'Quiz':
        process_quiz(contentable_id, output_dir, full_lesson_name)
        return

    # 2. STANDARD LESSON PROCESSING (Video/Text/Assignments)
    logger.info(f"Processing: {full_lesson_name}")

    lesson_data = fetch_lesson_details(contentable_id)
    if not lesson_data: return

    # A. Video
    video_url_player = lesson_data.get('lesson', {}).get('video_url')
    if video_url_player:
        wistia_id = extract_wistia_id_from_page(video_url_player, session, Config.HEADERS)
        if wistia_id:
            bin_url, resolution = get_wistia_bin_url(wistia_id, session, Config.QUALITY)
            if bin_url:
                download_with_ytdlp(bin_url, output_dir, full_lesson_name)
            else:
                logger.warning(f"No video found for {Config.QUALITY}")
        else:
            logger.error("Could not scrape Wistia ID.")

    # B. Attachments
    download_files = lesson_data.get('download_files', []) + lesson_data.get('attachments', [])
    for file_item in download_files:
        original_fname = file_item.get('file_name') or file_item.get('label') or 'attachment'
        f_url = file_item.get('download_url')

        if f_url:
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

    # C. HTML Text
    html_text = lesson_data.get('lesson', {}).get('html_text')
    if html_text:
        save_text_file(os.path.join(output_dir, f"{full_lesson_name}.html"), html_text)

    time.sleep(1)


def main():
    Config.validate()

    # 1. Fetch Course
    data = fetch_course_data(Config.COURSE_LINK)
    raw_course_name = data.get('course', {}).get('name', 'Course')
    course_name = sanitize_filename(raw_course_name)
    logger.info(f"=== {course_name} ===")

    base_output_dir = os.path.join(os.getcwd(), 'Downloads', course_name)
    create_directory(base_output_dir)

    all_contents = data.get('contents', []) + data.get('lessons', [])
    contents_map = {item['id']: item for item in all_contents}

    # 2. CHAPTER SELECTION (Feature 2)
    chapters = data.get('chapters', [])
    selected_indices = ask_user_for_chapters(chapters)

    # 3. Process
    for i, chapter in enumerate(chapters, 1):
        if i not in selected_indices: continue

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

