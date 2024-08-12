import cv2
import os
from pytube import YouTube
import numpy as np
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips
from yt_dlp import YoutubeDL

# def download_video(video_id, output_dir='videos'):
#     # Ensure the output directory exists
#     if not os.path.exists(output_dir):
#         os.makedirs(output_dir)
    
#     # Construct the YouTube URL
#     youtube_url = f'https://www.youtube.com/watch?v={video_id}'
    
#     # Download the video with the highest resolution
#     yt = YouTube(youtube_url)
#     video_stream = yt.streams.filter(file_extension='mp4', res="240p").first()
#     audio_stream = yt.streams.filter(only_audio=True, file_extension='mp4').first()

    
#     if not video_stream:
#         raise Exception("No video stream available with the specified resolution and format")
    
#     # Download video stream
#     video_path = os.path.join(output_dir, f'{video_id}_video.mp4')
#     video_stream.download(output_path=output_dir, filename=f'{video_id}_video.mp4')
    
#     # Download audio stream if available
#     if audio_stream:
#         audio_path = os.path.join(output_dir, f'{video_id}_audio.mp4')
#         audio_stream.download(output_path=output_dir, filename=f'{video_id}_audio.mp4')
        
#         # Merge video and audio
#         video_clip = VideoFileClip(video_path)
#         audio_clip = AudioFileClip(audio_path)
#         final_clip = video_clip.set_audio(audio_clip)
        
#         final_path = os.path.join(output_dir, f'{video_id}.mp4')
#         final_clip.write_videofile(final_path, codec='libx264')
        
#         # Cleanup temporary files
#         os.remove(video_path)
#         os.remove(audio_path)
        
#         return final_path
#     else:
#         # If no audio stream, just return the video
#         return video_path


def download_video(video_id, output_dir='videos'):
    # Ensure the output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Construct the YouTube URL
    youtube_url = f'https://www.youtube.com/watch?v={video_id}'

    ydl_opts = {
        'format': 'bestvideo[height<=240]+bestaudio/best[height<=240]',
        'outtmpl': os.path.join(output_dir, f'{video_id}.%(ext)s'),
        'merge_output_format': 'mp4'
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([youtube_url])
            print("Download completed")

        # Merged video path
        final_path = os.path.join(output_dir, f'{video_id}.mp4')
        print(f"Final path: {final_path}")
        return final_path

    except Exception as e:
        print(f"Error: {e}")



def extract_video_segment(video_path, start_time, end_time):
    video = VideoFileClip(video_path).subclip(start_time, end_time)
    audio = AudioFileClip(video_path).subclip(start_time, end_time)
    final_clip = video.set_audio(audio)
    
    # Ensure the 'videos' directory exists
    if not os.path.exists('videos'):
        os.makedirs('videos')

    output_path = f"videos/{start_time}s_to_{end_time}s.mp4"
    final_clip.write_videofile(output_path, codec="libx264")
    
    return output_path


def capture_frames(video_path, interval=3):
    cap = cv2.VideoCapture(video_path)
    frame_rate = int(cap.get(cv2.CAP_PROP_FPS))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames // frame_rate
    
    frames = []
    for sec in range(0, duration, interval):
        cap.set(cv2.CAP_PROP_POS_MSEC, sec * 1000)
        success, frame = cap.read()
        if success:
            frames.append(frame)
        else:
            break

    cap.release()
    return frames

def create_nine_grid_image(frames, start_sec, end_sec, output_dir, max_resolution=(1024, 1024)):
    rows, cols = 3, 3
    grid_image = None

    black_frame = np.zeros_like(frames[0]) if frames else np.zeros((max_resolution[1]//rows, max_resolution[0]//cols, 3), dtype=np.uint8)

    if len(frames) < rows * cols:
        missing_frames = rows * cols - len(frames)
        frames.extend([black_frame] * missing_frames)

    for i in range(rows):
        row_images = frames[i*cols:(i+1)*cols]
        row_image = cv2.hconcat(row_images)
        if grid_image is None:
            grid_image = row_image
        else:
            grid_image = cv2.vconcat([grid_image, row_image])

    height, width = grid_image.shape[:2]
    max_height, max_width = max_resolution
    scaling_factor = min(max_width / width, max_height / height)
    # Apply scaling factor if it is less than 1 (to reduce the image size)
    if scaling_factor < 1:
        new_size = (int(width * scaling_factor), int(height * scaling_factor))
        grid_image = cv2.resize(grid_image, new_size, interpolation=cv2.INTER_AREA)

    image_name = f'from_{start_sec}s_to_{end_sec}s.jpg'
    image_path = os.path.join(output_dir, image_name)
    cv2.imwrite(image_path, grid_image)
    return image_path

def process_video(video_path, output_dir, interval=3, max_resolution=(1024, 1024)):
    frames = capture_frames(video_path, interval)
    images = []
    
    num_images = (len(frames) + 8) // 9 

    for i in range(num_images):
        start_sec = i * 9 * interval
        end_sec = min((i + 1) * 9 * interval - interval, (len(frames) - 1) * interval)
        grid_frames = frames[i * 9: (i + 1) * 9]
        image_path = create_nine_grid_image(grid_frames, start_sec, end_sec, output_dir, max_resolution)
        images.append(image_path)

    return images

def get_nine_grid_images(video_path, interval=3, max_resolution=(1024, 1024), start_time=None, end_time=None):
    try:
        # create a directory to store the output images
        output_dir = 'frames'
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

        if start_time is not None:
            video = VideoFileClip(video_path).subclip(start_time, end_time)
            if not os.path.exists('videos'):
                os.makedirs('videos')
            output_path = f"videos/f{start_time}s_to_{end_time}s.mp4"
            video.write_videofile(output_path, codec="libx264")
            video_path = output_path

        image_paths = process_video(video_path, output_dir, interval, max_resolution)
        
        if start_time is not None:
            os.remove(video_path)
        
        print(f'Generated images: {image_paths}')
        return image_paths
    except Exception as e:
        print(f'Error: {str(e)}')
        return []
    


if __name__ == '__main__':
    video_path = download_video("oX7dEZfBUvg")
    # get_nine_grid_images("videos/80ttCfQCc_c.mp4", interval=2, max_resolution=(1024, 1024))