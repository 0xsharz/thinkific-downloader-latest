# Thinkific Course Downloader

A Python script to automate the downloading of course videos and attachments from Thinkific-based learning platforms.

## 📋 Prerequisites

* Python 3.8+
* `ffmpeg` (Required for video processing)

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/0xsharz/thinkific-downloader-latest.git
    cd thinkific-downloader
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## ⚙️ Configuration

1.  Create a file named `.env` in the root directory.
2.  Add the following details (you must be enrolled in the course):

    ```ini
    # URL of the course syllabus (e.g., https://courses.example.com/api/course_player/v2/courses/course-slug )
    COURSE_LINK=

    # Your login cookie from the browser
    COOKIE_DATA=

    # Optional: Video Quality (720p, 1080p). Defaults to 720p.
    VIDEO_DOWNLOAD_QUALITY=720p
    ```

### How to get your Cookie Data:
1.  Log in to the course website.
2.  Open Developer Tools (**F12**) and go to the **Network** tab.
3.  Refresh the page.
4.  Click the first request in the list.
5.  Scroll to **Request Headers** and copy the value of `Cookie`.

## ▶️ Usage

Run the script to start downloading:

```bash
python main.py
