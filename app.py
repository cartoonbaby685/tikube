# import os, glob, sqlite3, ffmpeg
# from yt_dlp import YoutubeDL
# from groq import Groq
# from google.oauth2.credentials import Credentials
# from googleapiclient.discovery import build
# from googleapiclient.http import MediaFileUpload

# TIKTOK_PROFILE_URL = os.getenv("TIKTOK_PROFILE_URL")

# # 1. DOWNLOAD TIKTOK & DE-DUPLICATE
# def fetch_video():
#     conn = sqlite3.connect('videos.db')
#     cursor = conn.cursor()
#     cursor.execute("CREATE TABLE IF NOT EXISTS posted (id TEXT PRIMARY KEY)")
    
#     ydl_opts = {'extract_flat': True, 'quiet': True}
#     with YoutubeDL(ydl_opts) as ydl:
#         info = ydl.extract_info(TIKTOK_PROFILE_URL, download=False)
#         for entry in info.get('entries', []):
#             vid_id = entry['id']
#             # Check DB to prevent downloading duplicates
#             if not cursor.execute("SELECT 1 FROM posted WHERE id=?", (vid_id,)).fetchone():
#                 print(f"Downloading new video ID: {vid_id}")
#                 dl_opts = {'outtmpl': 'input.mp4'}
#                 YoutubeDL(dl_opts).download([entry['url']])
                
#                 cursor.execute("INSERT INTO posted VALUES (?)", (vid_id,))
#                 conn.commit()
#                 return entry.get('title', '')
#     return None

# # 2. TRIM TO 58s & OVERLAY AUDIO
# def edit_video():
#     probe = ffmpeg.probe('input.mp4')
#     duration = float(probe['format']['duration'])
#     max_duration = 58.0 if duration > 60 else duration

#     music_files = glob.glob('music/*.mp3')
#     audio_track = music_files[0] if music_files else None

#     video = ffmpeg.input('input.mp4', t=max_duration)
    
#     if audio_track:
#         audio = ffmpeg.input(audio_track, t=max_duration)
#         ffmpeg.output(video.video, audio.audio, 'final_short.mp4').run(overwrite_output=True)
#     else:
#         # Strip audio if no custom track is provided
#         ffmpeg.output(video.video, 'final_short.mp4', an=None).run(overwrite_output=True)

# # 3. GENERATE SEO METADATA USING GROQ API
# def generate_metadata(caption):
#     # Initializes using GROQ_API_KEY environment variable
#     client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    
#     system_prompt = (
#         "You are an expert YouTube Shorts algorithm specialist. "
#         "Create viral, high-CTR titles and descriptions based on video captions."
#     )
#     user_prompt = f"""
#     Create YouTube Shorts metadata for this TikTok video caption: '{caption}'.
    
#     Strict Rules:
#     1. Title must be catchy, engaging, under 90 characters, and include 1 emoji.
#     2. Description must be concise and end with relevant hashtags including #Shorts.
    
#     Your output MUST follow this exact format:
#     TITLE: <your title here>
#     DESCRIPTION: <your description here>
#     """
    
#     completion = client.chat.completions.create(
#         model="llama-3.3-70b-versatile",
#         messages=[
#             {"role": "system", "content": system_prompt},
#             {"role": "user", "content": user_prompt}
#         ],
#         temperature=0.7
#     )
    
#     response_text = completion.choices[0].message.content
    
#     # Parse title and description
#     title = response_text.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()[:95]
#     description = response_text.split("DESCRIPTION:")[1].strip()
    
#     return title, description

# # 4. UPLOAD TO YOUTUBE
# def upload_to_youtube(title, description):
#     creds = Credentials(
#         token=None,
#         refresh_token=os.getenv("YT_REFRESH_TOKEN"),
#         token_uri="https://oauth2.googleapis.com/token",
#         client_id=os.getenv("YT_CLIENT_ID"),
#         client_secret=os.getenv("YT_CLIENT_SECRET")
#     )
#     youtube = build('youtube', 'v3', credentials=creds)
    
#     body = {
#         'snippet': {'title': title, 'description': description, 'categoryId': '22'},
#         'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}
#     }
    
#     media = MediaFileUpload('final_short.mp4', chunksize=-1, resumable=True)
#     youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
#     print("Video successfully published to YouTube Shorts!")

# if __name__ == "__main__":
#     caption = fetch_video()
#     if caption is not None:
#         edit_video()
#         title, description = generate_metadata(caption)
#         print(f"Generated Title: {title}")
#         print(f"Generated Description:\n{description}")
#         upload_to_youtube(title, description)
#     else:
#         print("No new videos found to process.")

import os, sqlite3, ffmpeg
from yt_dlp import YoutubeDL
from groq import Groq
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

TIKTOK_PROFILE_URL = os.getenv("TIKTOK_PROFILE_URL")

# 1. DOWNLOAD TIKTOK & DE-DUPLICATE
def fetch_video():
    conn = sqlite3.connect('videos.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS posted (id TEXT PRIMARY KEY)")
    
    ydl_opts = {'extract_flat': True, 'quiet': True}
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(TIKTOK_PROFILE_URL, download=False)
        for entry in info.get('entries', []):
            vid_id = entry['id']
            if not cursor.execute("SELECT 1 FROM posted WHERE id=?", (vid_id,)).fetchone():
                print(f"Downloading new video ID: {vid_id}")
                dl_opts = {'outtmpl': 'input.mp4'}
                YoutubeDL(dl_opts).download([entry['url']])
                
                cursor.execute("INSERT INTO posted VALUES (?)", (vid_id,))
                conn.commit()
                return entry.get('title', '')
    return None

# 2. EDIT VIDEO & RETAIN ORIGINAL AUDIO (FFMPEG)
def edit_video():
    probe = ffmpeg.probe('input.mp4')
    duration = float(probe['format']['duration'])
    max_duration = 58.0 if duration > 60 else duration

    input_file = ffmpeg.input('input.mp4', t=max_duration)

    # A. Visual Transformation Filter Chain
    # - 3% Crop
    # - Scale to 1080x1920
    # - Contrast 1.04, Brightness 0.01
    # - Draw Bottom Banner "Follow for daily cartoon"
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

    # B. Retain Original Audio Stream directly
    audio = input_file.audio

    # C. Render Final Output
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
    title = res.split("TITLE:")[1].split("DESCRIPTION:")[0].strip()[:95]
    description = res.split("DESCRIPTION:")[1].strip()
    
    # Add Disclaimer to Description
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
    youtube = build('youtube', 'v3', credentials=creds)
    
    body = {
    'snippet': {
        'title': title, 
        'description': description, 
        'categoryId': '1'  # 1 = Film & Animation
    },
    'status': {
        'privacyStatus': 'public', 
        'selfDeclaredMadeForKids': True
    }
}
    
    media = MediaFileUpload('final_short.mp4', chunksize=-1, resumable=True)
    youtube.videos().insert(part='snippet,status', body=body, media_body=media).execute()
    print("Video successfully published to YouTube Shorts!")

if __name__ == "__main__":
    caption = fetch_video()
    if caption is not None:
        print("1. Processing Video Editing (Retaining original audio)...")
        edit_video()
        
        print("2. Generating Baby Cartoon YouTube SEO Metadata...")
        title, description = generate_metadata(caption)
        print(f"Generated Title: {title}")
        
        print("3. Uploading to YouTube...")
        upload_to_youtube(title, description)
    else:
        print("No new videos found to process.")
