import re
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import SRTFormatter
import requests
import os
from dotenv import load_dotenv

load_dotenv()

def download_subtitles(video_id):
    try:
        # Fetch the subtitles using the video ID
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = transcript_list.find_transcript(['en'])

        # Initialize the SRT formatter
        formatter = SRTFormatter()
        
        # Format the transcript as SRT
        srt = formatter.format_transcript(transcript.fetch())
        
        # Save the SRT formatted subtitles to a file
        with open(f"{video_id}_subtitles.srt", "w", encoding="utf-8") as file:
            file.write(srt)
        
        print(f"Subtitles for video ID '{video_id}' have been saved.")
        return True
    
    except Exception as e:
        print(f"An error occurred: {e}")
        return False



api_key = os.getenv('YOUTUBE_API_KEY')

def get_video_info(video_id):
    url = f"https://www.googleapis.com/youtube/v3/videos?id={video_id}&part=snippet,contentDetails&key={api_key}"
    response = requests.get(url)
    video_info = response.json()
    
    if 'items' in video_info and len(video_info['items']) > 0:
        video_details = video_info['items'][0]
        video_name = video_details['snippet']['title']
        video_description = video_details['snippet']['description']
        video_posted_date = video_details['snippet']['publishedAt']
        video_poster = video_details['snippet']['channelTitle']
        video_length = video_details['contentDetails']['duration']

        match = re.search(r"PT(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?P<seconds>\d+)S", video_length)
        hours = int(match.group('hours') or 0) * 3600 
        minutes = int(match.group('minutes') or 0) * 60 
        seconds = int(match.group('seconds') or 0)
        total_seconds = hours + minutes + seconds
        
        return {
            "video_name": video_name,
            "video_description": video_description,
            "video_posted_date": video_posted_date,
            "video_poster": video_poster,
            "video_length": total_seconds
        }
    else:
        return None
    
def search_youtube(query, max_results=10):
    search_url = f"https://www.googleapis.com/youtube/v3/search"
    params = {
        'part': 'snippet',
        'q': query,
        'type': 'video',
        'maxResults': max_results,
        'key': api_key
    }
    response = requests.get(search_url, params=params)
    return response.json()


if __name__ == "__main__":
    video_id = 'B0sNa1i_GWY'
    # download_subtitles(video_id)
    info = get_video_info(video_id)
    print(info)


# h02ti0Bl6zk   openai
# U_M_uvDChJQ   interview
# Qht28m7b13U&t=10s   chain rule
