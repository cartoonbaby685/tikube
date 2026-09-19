import sys
import os
import sqlite3
import traceback
import ffmpeg
from yt_dlp import YoutubeDL
from groq import Groq
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TIKTOK_PROFILE_URL = os.getenv("TIKTOK_PROFILE_URL")

def fetch_video():
    print(f"Starting fetch_video()...", flush=True)
    if not TIKTOK_PROFILE_URL:
        print("ERROR: TIKTOK_PROFILE_URL environment variable is missing or empty!", flush=True)
        return None

    conn = sqlite3.connect('videos.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS posted (id TEXT PRIMARY KEY)")
    
    ydl_opts = {
        'extract_flat': True,
        'quiet': False,
        'no_warnings': False,
        'impersonate': 'chrome',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
    }

    if os.path.exists('cookies.txt'):
        print("Using cookies.txt for authentication...", flush=True)
        ydl_opts['cookiefile'] = 'cookies.txt'
    else:
        print("WARNING: cookies.txt not found. TikTok may block this request on GitHub Actions.", flush=True)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            print(f"Attempting to fetch profile: {TIKTOK_PROFILE_URL}", flush=True)
            info = ydl.extract_info(TIKTOK_PROFILE_URL, download=False)
            
            if not info:
                print("Extraction returned None.", flush=True)
                conn.close()
                return None

            entries = list(info.get('entries', []))
            print(f"Found {len(entries)} entries in feed.", flush=True)

            if not entries:
                print("No entries returned. TikTok blocked the request or account is empty.", flush=True)
                conn.close()
                return None

            for entry in entries:
                if not entry:
                    continue
                
                vid_id = entry.get('id')
                if not vid_id:
                    continue
                
                # Check database
                cursor.execute("SELECT 1 FROM posted WHERE id=?", (vid_id,))
                if cursor.fetchone():
                    print(f"Video {vid_id} already posted. Skipping...", flush=True)
                    continue

                print(f"Downloading new video ID: {vid_id}", flush=True)
                video_url = entry.get('url') or entry.get('webpage_url') or f"https://www.tiktok.com/@/video/{vid_id}"
                
                dl_opts = {
                    'outtmpl': 'input.mp4',
                    'impersonate': 'chrome',
                }
                if os.path.exists('cookies.txt'):
                    dl_opts['cookiefile'] = 'cookies.txt'

                YoutubeDL(dl_opts).download([video_url])
                
                cursor.execute("INSERT INTO posted VALUES (?)", (vid_id,))
                conn.commit()
                conn.close()
                return entry.get('title', '')

    except Exception as e:
        print(f"\n--- EXTRACTION ERROR: {e} ---", flush=True)
        traceback.print_exc()
        conn.close()
        return None

    conn.close()
    print("All existing videos have already been posted.", flush=True)
    return None


# 2. EDIT VIDEO & RETAIN ORIGINAL AUDIO (FFMPEG)
def edit_video():
    probe = ffmpeg.probe('input.mp4')
    duration = float(probe['format']['duration'])
    max_duration = 58.0 if duration > 60 else duration

    input_file = ffmpeg.input('input.mp4', t=max_duration)

    video = (
        input_file.video
        .crop('iw*0.03', 'ih*0.03', 'iw*0.94', 'ih*0.94')
        .filter('scale', 1080, 1920)
        .filter('eq', contrast=1.04, brightness=0.01)
        .drawtext(
            text="Follow for daily cartoon",
            x='(w-text_w)/2',
            y='h-120',
            fontsize=42,
            fontcolor='white',
            box=1,
            boxcolor='black@0.6',
            boxborderw=15
        )
    )

    audio = input_file.audio
    ffmpeg.output(video, audio, 'final_short.mp4', acodec='aac', vcodec='libx264').run(overwrite_output=True)

# 3. GENERATE YOUTUBE SEO METADATA FOR BABY CARTOON (GROQ)
def generate_metadata(caption):
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
    prompt = f"""
    Create YouTube Shorts metadata based on this video caption: '{caption}'.
    Niche: This channel is specifically about Baby Cartoons. Keep this context in mind.
    
    STRICT RULES FOR TITLE:
    1. Title MUST be very short, using strictly 2 to 4 words total.
    2. Must be catchy for a baby cartoon audience.
    3. Include these exact hashtags at the end of the title: #shorts #funny #babycartoon
    4. Total length of TITLE (including hashtags) MUST be strictly under 95 characters.
    
    FORMAT:
    TITLE: <2-4 word title> #shorts #funny #babycartoon
    DESCRIPTION: <engaging description for baby cartoon video with relevant hashtags>
    """
    
    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}]
    )
    
    res = completion.choices[0].message.content
    
    # Safe splitting in case LLM outputs unexpected headers
    try:
        title = res.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()[:95]
        description = res.split("DESCRIPTION:")[1].strip()
    except IndexError:
        print("Warning: LLM formatting did not match expected structure. Using fallback formatting.")
        title = "Cute Baby Cartoon #shorts #funny #babycartoon"
        description = res.strip()
    
    disclaimer = "\n\n---\nDisclaimer: Short entertaining baby cartoon video clips edited for audience enjoyment under Fair Use."
    return title, description + disclaimer

# 4. UPLOAD TO YOUTUBE

def upload_to_youtube(title, description):
    creds = Credentials(
        token=None,
        refresh_token=os.getenv("YT_REFRESH_TOKEN"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("YT_CLIENT_ID"),
        client_secret=os.getenv("YT_CLIENT_SECRET")
    )
    
    # Force a token refresh if token is expired or missing
    if not creds.valid:
        creds.refresh(Request())
        
    youtube = build('youtube', 'v3', credentials=creds)
    
    body = {
        'snippet': {
            'title': title, 
            'description': description, 
            'categoryId': '1'  # 1 = Film & Animation
        },
        'status': {
            'privacyStatus': 'public', 
            'selfDeclaredMadeForKids': False
        }
    }
    
    media = MediaFileUpload('final_short.mp4', chunksize=-1, resumable=True)
    youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    print("Video successfully published to YouTube Shorts!")
