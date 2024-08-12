import http.server
import socketserver
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
import threading
import json
from urllib.parse import urlparse, parse_qs
import parse_srt as parse_srt
import mouth as mouth
import video_data as video_data
import os
import time
from datetime import timedelta, datetime
from bitarray import bitarray
import concurrent.futures
import video_processing as video_processing
import shutil
import google.generativeai as genai
from google.generativeai import GenerativeModel
import pathlib
import googleapiclient.discovery
import googleapiclient.errors
import isodate
from dotenv import load_dotenv

load_dotenv()

class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """Handle requests in a separate thread."""

messages = []

video_id = ''
chunks = []
input_string = []
length = 0
comment = [] # comments and their timing from GPT
start_time = 0 # start time (real world time) of current action
video_time = 0 # current time (position) in video
rate = 1 # playback rate
playing = False # is comments system currently playing
delay = False # is for when video is already paused before comments are generated
play = False # is video currently playing
inactive_comment = False # is comments system currently inactived
inactive_skipping_summary = False # is skipping summary inactive
video_path = '' # path to the video file
no_subtitle_video = False # is a video without subtitles

skip_summary = '' # text to display when user skips part of video

pause_video = False # want to pause the video
play_video = False # want to replay the video
display_text = '' # text to display on the screen
styled_text = '' # skipped text to display (comment / skip summary)
endless_text = False # is the text endless
bot_response = '' # chatbot's response to display on dialog window
jump_time = None # jump to a specific time in the video
clear_all_comments_flag = False # clear all comments on screen
navigation_to_video_id = None # navigate to a specific video ID
navigation_start_time = 0 # start with this point of the video after navigation
navigation_end_time = 100000 # end with this point of the video after navigation

last_pause = 0 # last time the video is paused, for calculating unwatched parts
last_play = 0 # last time the video is played, for calculating unwatched parts
watched_bits = bitarray() # bits to record which part of the video has been watched
watched_bits = bitarray(154)
watched_bits.setall(0)

customized_chatbot = '' # customized chatbot response
update_customization = False # update the customization of the chatbot

# EDUCATION MODE VARIABLES
education_mode = False # is the chatbot in education mode
designer_mode = False # is the chatbot in designer mode
designer_messages = [] # messages in designer mode
education_plan = [] # education plan for the chatbot
next_video = json.dumps({}) # next video in the education plan
next_video_comment = [] # next video's comments in the education plan
previes_video_end = True # is the previes video in the education plan ended


class RequestHandler(http.server.BaseHTTPRequestHandler):

    def _set_headers(self, status=200):
        self.send_response(status)
        self.send_header('Content-type', 'text/plain')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        return

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)

        try:
            global video_id
            global chunks
            global input_string
            global length
            global comment
            global start_time
            global video_time
            global rate
            global playing
            global delay
            global play
            global pause_video
            global play_video
            global display_text
            global skip_summary
            global styled_text
            global bot_response
            global watched_bits
            global last_play
            global last_pause
            global inactive_skipping_summary
            global video_path
            global no_subtitle_video
            global customized_chatbot
            global previes_video_end
            global education_mode
            global education_plan
            global next_video
            global next_video_comment
            global designer_mode
            global designer_messages


            parsed_data = json.loads(post_data.decode('utf-8'))
            if parsed_data['event'] == 'tabClose':
                print(parsed_data)
                mouth.stop_comment()
                video_id = ''
                chunks = []
                input_string = []
                length = 0
                comment = []
                start_time = 0
                video_time = 0
                rate = 1
                playing = False
                delay = False
                play = False
                video_path = ''
                no_subtitle_video = False
                education_mode = False
                designer_mode = False 
                designer_messages = [] 
                education_plan = []
                next_video = json.dumps({})
                next_video_comment = [] 
                previes_video_end = True
                if os.path.exists('frames'):
                    shutil.rmtree('frames')
                if os.path.exists('videos'):
                    shutil.rmtree('videos')
            
            elif parsed_data["event"] == 'user_input':
                print(parsed_data)
                bot_response = conversation_comments_generate(parsed_data['text'], parsed_data['timestamp'])
            
            elif parsed_data['videoId'] == None:
                if playing:
                    mouth.stop_comment()
                    playing = False
                play = False

            elif parsed_data['event'] == 'play':
                play = True
                print(parsed_data)

                # if starting a new video, reset all variables, prepare the comments
                if video_id != parsed_data['videoId']:
                    if playing:
                        mouth.stop_comment()
                        playing = False
                    if os.path.exists('frames'):
                        shutil.rmtree('frames')
                    if os.path.exists('videos'):
                        shutil.rmtree('videos')
                    chunks = []
                    input_string = []
                    length = 0
                    if not education_mode:
                        comment = []
                    delay = False
                    video_path = ''
                    last_pause = 0
                    no_subtitle_video = False
                    last_play = float(parsed_data['timestamp'])
                    if os.path.exists(str(video_id) + '_subtitles.srt'):
                        os.remove(str(video_id) + '_subtitles.srt')
                    video_time = parsed_data['timestamp']
                    start_time = time.time()
                    video_id = parsed_data['videoId']

                    # download subtitles and get video info
                    has_trans = video_data.download_subtitles(video_id)
                    video_info = video_data.get_video_info(video_id)
                    video_name = video_info['video_name']
                    video_poster = video_info['video_poster']
                    video_posted_date = video_info['video_posted_date']
                    video_description = video_info['video_description']
                    video_length = video_info['video_length']
                    watched_bits = bitarray(video_length)
                    watched_bits.setall(0)

                    # do not generate comments if in education mode
                    if education_mode:
                        video_path = video_processing.download_video(video_id)

                    # if video has subtitles
                    elif has_trans: 
                        chunks, _ = parse_srt.parse_srt(str(video_id) + '_subtitles.srt', video_length)
                        input_string, length = parse_srt.number_the_chunks(chunks)

                        lock = threading.Lock()
                        with concurrent.futures.ThreadPoolExecutor() as executor:
                            # generate initial comments
                            future_response = executor.submit(comments_generate, video_name, video_poster, video_posted_date, video_description, input_string, length)
                            future_video_path = executor.submit(video_processing.download_video, video_id)
                            response = future_response.result()
                            print(response)
                            comment = parse_srt.set_time(response, chunks)
                            if os.path.exists(str(video_id) + '_subtitles.srt'):
                                os.remove(str(video_id) + '_subtitles.srt')
                            playing = True
                            executor.submit(first_play_comments, comment, start_time, video_time, rate)
                            # video_path = future_video_path.result()

                    # if video has no subtitles
                    else:
                        no_subtitle_video = True
                        chunks = parse_srt.parse_video_without_srt(video_length)
                        input_string, length = parse_srt.number_the_chunks_no_srt(chunks)
                        video_path = video_processing.download_video(video_id)
                        image_paths = video_processing.get_nine_grid_images(video_path, 1)
                        response = comment_generate_with_images(video_name, video_poster, video_posted_date, video_description, image_paths, 1, input_string)
                        print(response)
                        comment = parse_srt.set_time(response, chunks)
                        playing = True
                        first_play_comments(comment, start_time, video_time, rate)
                        playing = False
                        
                
                # if not new video
                else:
                    if not last_play == last_pause == float(parsed_data['timestamp']) == 0: # incase two play event send when start video
                        start_time = time.time()
                        # count for unwatched seconds if any
                        seconds_unwatched = 0
                        last_play = float(parsed_data['timestamp'])
                        if float(parsed_data['timestamp']) > last_pause:
                            for i in range(int(last_pause), int(float(parsed_data['timestamp']))):
                                if watched_bits[i] == 0:
                                    seconds_unwatched += 1
                        
                        # if the part skipped contain unwatched parts for more than 8s
                        if seconds_unwatched > 8 and not inactive_skipping_summary and not no_subtitle_video: 
                            intervals = get_unwatched_intervals(int(last_pause), int(float(parsed_data['timestamp'])))
                            skip_summary = skipped_comments_generate(video_time, float(parsed_data['timestamp']), intervals)
                            video_time = float(parsed_data['timestamp'])
                            print(skip_summary)
                            comment_time = timedelta(seconds=float(parsed_data['timestamp']))
                            if skip_summary.strip()[1] == '1':
                                styled_text = skip_summary
                            play_comments([(comment_time, skip_summary)], start_time, float(parsed_data['timestamp']), rate, skip=True)
                        else:
                            video_time = float(parsed_data['timestamp'])
                            time.sleep(0.11) # wait for the chatbot to pause (if play and pause happen within 0.1s)
                        
                        if not delay:
                            playing = True
                            play_comments(comment, start_time, video_time, rate)
                            playing = False
                        else:
                            delay = False

            elif parsed_data['event'] == 'pause':
                play = False
                print(parsed_data)
                last_pause = float(parsed_data['timestamp'])
                video_time = float(parsed_data['timestamp'])
                for i in range(int(last_play), int(video_time)):
                    watched_bits[i] = 1
                if playing:
                    mouth.stop_thread = True
                    playing = False
                else:
                    delay = True

            elif parsed_data['event'] == 'end':
                play = False
                if education_mode:
                    previes_video_end = True
                print(parsed_data)

            elif parsed_data['event'] == 'adPlay':
                play = False
                print(parsed_data)
                if playing:
                    mouth.stop_comment()
                    playing = False
                else:
                    delay = True
            
            elif parsed_data['event'] == 'skip':
                print(parsed_data)
                video_time = float(parsed_data['timestamp'])
                if playing:
                    mouth.stop_comment()
                    playing = True
                    play_comments(comment, start_time, video_time, rate)
                    playing = False

            elif parsed_data['event'] == 'playbackRateChange':
                print(parsed_data)
                start_time = time.time()
                video_time = float(parsed_data['timestamp'])
                rate = float(parsed_data['playbackRate'])
                if not play:
                    pass
                if playing:
                    mouth.stop_after_finish()
                    playing = True
                    play_comments(comment, start_time, video_time, rate, previes=True)
                    playing = False
            
            elif parsed_data['event'] == 'customize':
                print(parsed_data)
                if parsed_data['value'] == 'yes':
                    if parsed_data['user'] != '' and parsed_data['chatbot'] != '':
                        customized_chatbot = f"About User\n\n'''\n{parsed_data['user']}\n'''\n\n\nUser's Preferences for Chatbot Behavior\n\n'''\n{parsed_data['chatbot']}\n'''\n\n\n"
                    elif parsed_data['user'] != '':
                        customized_chatbot = f"About User\n\n'''\n{parsed_data['user']}\n'''\n\n\n"
                    elif parsed_data['chatbot'] != '':
                        customized_chatbot = f"User's Preferences for Chatbot Behavior\n\n'''\n{parsed_data['chatbot']}\n'''\n\n\n"
            
            elif parsed_data['event'] == 'end_time_reached':
                print(parsed_data)
                previes_video_end = True
                        
                    
        except Exception as e:
            print(f"Error: {e}")

        self._set_headers()
        self.wfile.write("Received".encode('utf-8'))
    
    def do_GET(self):
        if self.path == '/events':
            self.send_response(200)
            self.send_header('Content-type', 'text/event-stream')
            self.send_header('Cache-Control', 'no-cache')
            self.send_header('Connection', 'keep-alive')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

            try:
                while True:
                    command = check_for_commands()
                    if command['command'] is not None:
                        self.wfile.write(f"data: {json.dumps(command)}\n\n".encode('utf-8'))
                        self.wfile.flush()
                    time.sleep(0.1)
            except ConnectionResetError:
                print("Client closed connection.")
            except BrokenPipeError:
                print("Broken pipe error.")
            except Exception as e:
                print(f"Error in SSE stream: {e}")
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write("Not Found".encode())







############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################

def check_for_commands():
    global pause_video, play_video, display_text, styled_text, endless_text, bot_response, jump_time, clear_all_comments_flag, navigation_to_video_id, navigation_start_time, navigation_end_time, update_customization, customized_chatbot
    if pause_video:
        pause_video = False
        return {'command': 'pause'}
    elif play_video:
        play_video = False
        return {'command': 'play'}
    elif display_text:
        print(display_text)
        text = display_text
        display_text = ''
        if text in styled_text:
            styled_text = ''
            return {"command": "displayText", "style": True, "endless": False, "text": text}
        elif endless_text:
            endless_text = False
            return {"command": "displayText", "style": False, "endless": True, "text": text}
        return {"command": "displayText", "style": False, "endless": False, "text": text}
    elif jump_time is not None:
        command = {'command': 'jump', 'time': jump_time}
        jump_time = None
        return command
    elif clear_all_comments_flag:
        clear_all_comments_flag = False
        return {'command': 'clear_all_comments'}
    elif navigation_to_video_id:
        video_id = navigation_to_video_id
        start_time = navigation_start_time
        navigation_to_video_id = None
        navigation_start_time = 0
        end_time = navigation_end_time if navigation_end_time != 100000 else None
        navigation_end_time = 100000
        return {"command": "navigate", "video_id": video_id, "start_time": start_time, "end_time": end_time}
    elif bot_response:
        print(bot_response)
        text = bot_response
        bot_response = ''
        return {"command": "bot_response", "text": text}
    elif update_customization:
        update_customization = False
        if not customized_chatbot:
            return {"command": "update_customization", "userInfo": "", "chatbotBehavior": ""}
        user_info = ""
        chatbot_behavior = ""
        if "About User" in customized_chatbot:
            user_info = customized_chatbot.split("About User\n\n'''\n")[1].split("'''\n\n\n")[0]
        if "User's Preferences for Chatbot Behavior" in customized_chatbot:
            chatbot_behavior = customized_chatbot.split("User's Preferences for Chatbot Behavior\n\n'''\n")[1].split("'''\n\n\n")[0]
        return {"command": "update_customization", "userInfo": user_info, "chatbotBehavior": chatbot_behavior}
    else:
        return {'command': None}

def first_play_comments(comment, start_time, video_time, rate):
    global delay
    if not delay:
        play_comments(comment, start_time, video_time, rate)
    else:
        delay = False

def play_comments(comment, start_time, video_time, rate, previes=False, skip=False):
    global display_text, pause_video, play_video, inactive_comment, endless_text
    if inactive_comment:
        return
    first = True
    pop_list = []
    for comment_time, text in comment:
        r = mouth.play_one_comment(comment_time, text, first, start_time, video_time, rate, previes, skip)
        if r == []:
            continue
        elif r[0] == 0:
            break
        elif r[0] == 1:
            display_text = r[1]
        elif r[0] == 2:
            # pause_video = True
            # endless_text = True
            display_text = r[1]
        first = False
        pop_list.append((comment_time, text))
    for comment_time, text in pop_list:
        if (comment_time, text) in comment:
            comment.remove((comment_time, text))


def get_unwatched_intervals(start, finish):
    global watched_bits
    intervals = []
    current_start = None
    for i in range(start, finish):
        if watched_bits[i] == 0 and current_start is None:
            current_start = i
        elif watched_bits[i] == 1 and current_start is not None:
            intervals.append((current_start, i))
            current_start = None
    if current_start is not None:
        intervals.append((current_start, finish))
    interval_strings = [f"{start}s - {end}s" for start, end in intervals]
    return ", ".join(interval_strings)

def parse_json_response(text):
    print("in parse_json_response\n\n")
    print(text + "\n\n")
    left_index = 0
    right_index = len(text) - 1
    while left_index < len(text) and text[left_index] != '{':
        left_index += 1
    while right_index >= 0 and text[right_index] != '}':
        right_index -= 1
    if left_index > right_index:
        raise ValueError("Invalid JSON format")
    print(f"left_index: {left_index}, right_index: {right_index}\n\n")
    json_text = text[left_index+1:right_index]
    items = json_text.split(',')
    parsed_dict = {}
    for item in items:
        key, value = item.split(':', 1)
        key = key.strip().strip('"')
        value = value.strip().strip('"')
        parsed_dict[key] = value
    print("before return\n\n")
    return parsed_dict

def find_education_video():
    global education_plan, next_video
    text = find_video(education_plan[0])
    education_plan.pop(0)
    print("plan poped\n\n")
    text = text.replace("'", '"').replace("\n", "").strip()
    print(f"Cleaned text: {repr(text)}\n\n")
    next_video = parse_json_response(text)
    print(f"{next_video}\n\n")
    generate_learning_comments_for_video()

def generate_learning_comments_for_video():
    global next_video, education_plan, next_video_comment, previes_video_end, education_mode, \
        comment, messages, navigation_to_video_id, navigation_start_time, navigation_end_time, \
        playing, rate, start_time, video_time, chunks
    print("in generate_learning_comments_for_video\n\n")
    sub = request_timed_subtitle_fun(next_video['video_id'])
    print("sub\n\n")
    sub, length = parse_srt.filter_subtitle_chunks(sub, float(next_video['start_time']), float(next_video['end_time']))
    print("sub filtered\n\n" + str(length))
    response = learning_comment_generation(sub, length)
    try:
        next_video_comment = parse_srt.set_time(response, chunks)
    except Exception as e:
        print(f"Error in set_time: {e}")
    while not previes_video_end and education_mode:
        time.sleep(0.1)
    print("passed while\n\n")
    previes_video_end = False
    if not education_mode:
        comment = []
        next_video = json.dumps({})
        next_video_comment = []
        education_plan = []
        return
    messages.append({"role": "user", "parts": "Video clip: \n" + str(next_video) + "\n\nSubtitle: \n" + str(sub) + "\n\nLearning Comments for this video clip: \n" + str(next_video_comment)})
    navigation_to_video_id = next_video['video_id']
    navigation_start_time = int(next_video['start_time'])
    navigation_end_time = int(next_video['end_time']) - 1
    next_video = json.dumps({})
    if playing:
        mouth.stop_comment()
    comment = next_video_comment
    next_video_comment = []
    playing = True

    print("before executor\n\n")
    executor = concurrent.futures.ThreadPoolExecutor()
    executor.submit(first_play_comments, comment, start_time, video_time, rate)
    executor.shutdown(wait=False)

    print("finding the next video\n\n")
    find_education_video()



############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################



def jump_to_time_fun(timestamp: float) -> bool:
    """
    Jump to a specific time in the video.

    Parameters:
    timestamp: The time in seconds to which the video should jump to.

    Returns: True if the operation was successful, otherwise False.
    """
    global video_time, start_time, jump_time
    video_time = float(timestamp)
    start_time = time.time()
    jump_time = float(timestamp)
    return True

def stop_comments_fun(k: bool=True) -> bool:
    """
    Stop displaying comments from now on.

    Parameters: None

    Returns: True if the operation was successful, otherwise False.
    """
    global playing, delay, inactive_comment
    if playing:
        mouth.stop_thread = True
    playing = False
    delay = False
    inactive_comment = True
    return True

def restart_comments_fun(k: bool=True) -> bool:
    """
    Restart displaying comments from now on.

    Parameters: None

    Returns: True if the operation was successful, otherwise False.
    """
    global playing, inactive_comment, comment, start_time, video_time, rate
    playing = True
    inactive_comment = False
    play_comments(comment, start_time, video_time, rate)
    return True

def stop_skipping_summary_fun(k: bool=True) -> bool:
    """
    Stop providing skipping summary.

    Parameters: None

    Returns: True if the operation was successful, otherwise False.
    """
    global inactive_skipping_summary
    inactive_skipping_summary = True
    return True

def reactivate_skipping_summary_fun(k: bool=True) -> bool:
    """
    Reactivate providing skipping summary.

    Parameters: None

    Returns: True if the operation was successful, otherwise False.
    """
    global inactive_skipping_summary
    inactive_skipping_summary = False
    return True

def clear_comments_fun(k: bool=True) -> bool:
    """
    Clear all comments currently displayed on the screen.

    Parameters: None

    Returns: True if the operation was successful, otherwise False.
    """
    global clear_all_comments_flag
    clear_all_comments_flag = True
    return True

def pause_video_fun(k: bool=True) -> bool:
    """
    Pause the video.

    Parameters: None

    Returns: True if the video was successfully paused, False if it was already paused.
    """
    global play, pause_video
    if not play:
        return False
    play = False
    pause_video = True
    return True

def replay_video_fun(k: bool=True) -> bool:
    """
    Replay the video.

    Parameters: None

    Returns: True if the video was successfully replayed, False if it was already playing.
    """
    global play, play_video
    if play:
        return False
    play = True
    play_video = True
    return True


YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')

import googleapiclient.discovery

def search_videos_fun(prompt: str, num_results: int) -> dict:
    """
    Search YouTube videos based on a prompt and return the first `num_results` results with details.

    Parameters:
    prompt: The search query.
    num_results: The number of results to return.

    Returns:
    A dictionary containing:
        - "results": A list of dictionaries, each representing a video with the following keys:
            - "video_id": The ID of the video.
            - "video_name": The title of the video.
            - "author": The name of the channel that uploaded the video.
            - "post_date": The date and time the video was published.
            - "description": The description of the video.
            - "likes": The number of likes the video has received.
            - "views": The number of views the video has received.
            - "length": The duration of the video in ISO 8601 format.
    """
    try:
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        
        # Search for videos
        search_response = youtube.search().list(
            q=prompt,
            part="id,snippet",
            maxResults=num_results,
            type="video"
        ).execute()
        
        video_details = []
        
        for item in search_response.get("items", []):
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]
            
            # Get video statistics and content details
            video_response = youtube.videos().list(
                part="statistics,contentDetails",
                id=video_id
            ).execute()
            
            video_item = video_response.get("items", [])[0]
            statistics = video_item["statistics"]
            content_details = video_item["contentDetails"]
            
            likes = statistics.get("likeCount", 0)
            views = statistics.get("viewCount", 0)
            length = content_details.get("duration", "")
            
            video_details.append({
                "video_id": video_id,
                "video_name": snippet["title"],
                "author": snippet["channelTitle"],
                "post_date": snippet["publishedAt"],
                "description": snippet["description"],
                "likes": likes,
                "views": views,
                "length": length
            })
        print(str(video_details))
        
        return {"results": video_details}
    
    except Exception as e:
        print(f"Error in search_videos_fun: {e}")
        return {"results": []}
    
def search_education_videos_fun(prompt: str) -> dict:
    """
    Search YouTube videos based on a prompt and return results with details.

    Parameters:
    prompt: The search query.

    Returns:
    A dictionary containing:
        - "results": A list of dictionaries, each representing a video with the following keys:
            - "video_id": The ID of the video.
            - "video_name": The title of the video.
            - "author": The name of the channel that uploaded the video.
            - "post_date": The date and time the video was published.
            - "description": The description of the video.
            - "likes": The number of likes the video has received.
            - "views": The number of views the video has received.
            - "length": The duration of the video in ISO 8601 format.
    """
    try:
        youtube = googleapiclient.discovery.build("youtube", "v3", developerKey=YOUTUBE_API_KEY)
        
        # Search for videos
        search_response = youtube.search().list(
            q=prompt,
            part="id,snippet",
            maxResults=5,
            type="video"
        ).execute()

        video_details = []
        
        for item in search_response.get("items", []):
            video_id = item["id"]["videoId"]
            snippet = item["snippet"]

            # Get video statistics and content details
            video_response = youtube.videos().list(
                part="statistics,contentDetails",
                id=video_id
            ).execute()
            
            video_item = video_response.get("items", [])[0]
            statistics = video_item["statistics"]
            content_details = video_item["contentDetails"]
            
            likes = int(statistics.get("likeCount", "0"))
            views = int(statistics.get("viewCount", "0"))
            length = content_details.get("duration", "")

            duration = isodate.parse_duration(length)
            cutoff_duration = timedelta(minutes=30)
            
            if (likes > 30 or views > 3000) and duration < cutoff_duration:
                video_details.append({
                    "video_id": video_id,
                    "video_name": snippet["title"],
                    "author": snippet["channelTitle"],
                    "post_date": snippet["publishedAt"],
                    "description": snippet["description"],
                    "likes": likes,
                    "views": views,
                    "length": length
                })

        num = min(5, len(video_details))
        video_details = sorted(video_details, key=lambda x: x["likes"], reverse=True)[:num]
        
        return {"results": video_details}
    
    except Exception as e:
        print(f"Error in search_videos_fun: {e}")
        return {"results": []}
    
def navigate_to_video_fun(video_id: str, start_time: float=0, end_time: float=100000) -> bool:
    """
    Navigate to a specific video page on YouTube using the video ID.

    Parameters:
    video_id: The ID of the YouTube video to navigate to.
    start_time: The start time in seconds to start the new video from.

    Returns: True if the navigation was successfully replayed, otherwise False.
    """
    global navigation_to_video_id, navigation_start_time, navigation_end_time
    try:
        navigation_to_video_id = video_id
        navigation_start_time = start_time
        navigation_end_time = end_time
        return True
    except Exception as e:
        print(f"Error in navigate_to_video_fun: {e}")
        return False

def request_subtitle_fun(video_id: str) -> str:
    """
    Fetch the subtitles for any given YouTube video.

    Parameters:
    video_id: The ID of the YouTube video for which to fetch subtitles.

    Returns:
    str: A string containing the subtitles.
         If no subtitles are found, returns "No subtitle found for this video".
    """
    has_trans = video_data.download_subtitles(video_id)
    if not has_trans:
        return "No subtitle found for this video"
    video_info = video_data.get_video_info(video_id)
    video_length = video_info['video_length']
    _, subtitle = parse_srt.parse_srt(str(video_id) + '_subtitles.srt', video_length)
    os.remove(str(video_id) + '_subtitles.srt')
    return subtitle

def request_timed_subtitle_fun(video_id: str) -> str:
    """
    This function should only be called at the end of video finding process. The function fetch and parse the subtitles with timeing for a given YouTube video. 

    Parameters:
    video_id: The ID of the YouTube video for which to fetch subtitles.

    Returns:
    str: A string containing the chunks of subtitles with timing for each chunk.
         If no subtitles are found, returns "No subtitle found for this video".
    """
    global chunks
    has_trans = video_data.download_subtitles(video_id)
    if not has_trans:
        return "No subtitle found for this video"
    video_info = video_data.get_video_info(video_id)
    video_length = video_info['video_length']
    chunks, _ = parse_srt.parse_srt(str(video_id) + '_subtitles.srt', video_length)
    input_string, _ = parse_srt.number_the_chunks(chunks)
    os.remove(str(video_id) + '_subtitles.srt')
    return input_string

def analyze_video_frames_fun(start_time: float, end_time: float, prompt: str) -> str:
    """
    Analyze frames from the currently playing video between the specified start and end times based on a specific prompt.

    Ensure your prompt is detailed enough so that the LLM can generate insights you required based on the video frames.

    Parameters:
    start_time: The start time in seconds.
    end_time: The end time in seconds.
    prompt: The prompt to let LLM analyze the part of video.

    Returns: A string containing the insights generated by the LLM after analyzing the video frames.
    """
    global video_path
    if not video_path:
        raise ValueError("No current video is loaded")

    nine_grid_images = video_processing.get_nine_grid_images(video_path, interval=1, start_time=start_time, end_time=end_time)
    response = insights_from_frames(start_time, end_time, prompt, nine_grid_images)
    
    return response

def start_education_mode_fun(user_input: str) -> str:
    """
    Start the education mode for the chatbot.

    Parameters: 
    user_input: The user's input that containing their learning request.

    Returns: A string contianing conversations between desinger and the user.
    """
    global designer_mode, bot_response, designer_messages, education_mode, education_plan
    time.sleep(0.11)
    education_mode = True
    designer_mode = True
    bot_response = designer_start(user_input)

    while designer_mode:
        time.sleep(0.1)

    if education_mode:
        executor = concurrent.futures.ThreadPoolExecutor()
        executor.submit(find_education_video)
        executor.shutdown(wait=False)

    return "Here is the conversation between teaching assistant and user: \n\n" + str(designer_messages) + "\n\nIf the designer tasks are DONE, tell the user that the learning journey will start in a minute. If the education mode stoped, you should call funtion to end the education mode."

def end_education_mode_fun(k: bool=True) -> bool:
    """
    End the education mode for the chatbot.

    Parameters: None

    Returns: True if the operation was successful, otherwise False.
    """
    global education_mode
    education_mode = False
    return True

def skip_current_video_in_education_mode_fun(k: bool=True) -> bool:
    """
    Skip the current video in the education mode for the chatbot.

    Parameters: None

    Returns: True if the operation was successful, otherwise False.
    """
    global previes_video_end
    previes_video_end = True
    return True

def update_customization_fun(user_info: str, chatbot_behavior: str) -> bool:
    """
    Update the customization for the chatbot based on the user's information and preferences.

    Parameters:
    user_info: The information about the user.
    chatbot_behavior: The preferences for the chatbot behavior.

    Returns: True if the operation was successful, otherwise False.
    """
    global customized_chatbot, update_customization
    customized_chatbot = f"About User\n\n'''\n{user_info}\n'''\n\n\nUser's Preferences for Chatbot Behavior\n\n'''\n{chatbot_behavior}\n'''\n\n\n"
    update_customization = True
    return True

############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################


api_key = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=api_key)
main_model = genai.GenerativeModel(model_name="gemini-1.5-flash", tools=[jump_to_time_fun, stop_comments_fun, restart_comments_fun, stop_skipping_summary_fun, reactivate_skipping_summary_fun, clear_comments_fun, pause_video_fun, replay_video_fun, search_videos_fun, navigate_to_video_fun, analyze_video_frames_fun, request_subtitle_fun, update_customization_fun, start_education_mode_fun, end_education_mode_fun, skip_current_video_in_education_mode_fun],
    system_instruction="You are the brain of ViBo, a video-watching companion chatbot. You have three main tasks: 1. Provide extra information beyond the video content; 2. Provide short highlights of the parts of the video the user skipped; 3. Communicate with the user. \n\n======\n\n" +
     "As for your first responsibility, I will provide you with video information, including subtitles segmented into many chunks of text. The chunks are numbered sequentially with their timing. You will be asked to provide meaningful extra information for all chunks in advance. Your comments will be played to the user in real-time as they watch the video. \n" +
     "Your goal is to provide extra information beyond the video content that can assist the user. For all facts, data, and news mentioned in the video, check for their correctness and notify the user if they are incorrect. Provide correct guidance for content that promotes negative values or bias. Provide background knowledge on specialized video content. \n" +
     "Ensure your response is in the following format: 'Chunk i: [x] comment'. Where 'i' is the chunk's number, 'x' is 0, 1, or 2, indicating levels, and 'comment' is your words to the user at this point in the video. For the three levels, [0] indicates you have nothing to say at this point; in this case, leave 'comment' empty. [1] indicates something good to mention at this point; provide your words in 'comment'. For level 1, a text box will be displayed on user's screen for 12s. [2] indicates something that's extremely important to tell the user at this point, something worth affecting the user's watching experience; provide your words in 'comment'. For level 2, the video will be paused and the text box will be displaying on screen until the user manually close it. \nMake sure your comments appear at the right chunks, simulating real-time video play. \n\n###\n\n" + 
     "Your second responsibility is to provide a skipping summary. When the user skips part of a video, I will provide you with the times the user skipped and the intervals during these skipped times that the user never watched. The prompt will be in following format: [\"User skipped from \" + start_position + \"s to \" + end_position + \"s. During this time period, user never watched the following intervals:\" + intervals + \". Provide the highlights of the parts user never watched.\"]. If there is key information within the intervals the user never watched, let the user know what they missed. Also, make sure to state the exact time period of those key information. It should be a short summary; don't directly spoil the story. Briefly highlight the important points or events that the user may want to go back and watch. Moreover, you do not need to provided skip summaries for parts you already provided before. \n" +
     "Format your response as: '[x] comment'. Where 'x' is 0, 1, or 2, indicating levels, and 'comment' is your short summary. Your response should only contain one such '[x] comment' and nothing else. \n\n###\n\n" +
     "Lastly, the user can send messages to you. I will provide you with the message and the timestamp of when the user sent this message during the video. Direct conversation from user will be send to you in the following format: [\"User (\" + time + \"s): '\" + content + \"'.\"]. Depending on the request by the user, you may simply answer the user's question or perform some actions before answering the user's question. I have provided you with functions that you can use to achieve the user's and your needs. For every single round of conversation, be mindful about what function you can use to better access user. Your final response will be displayed to the user. Be friendly when respond. \n" +
     "Your abilities include: jump to a specific time in the video, stop displaying comments, restart displaying comments, stop providing skipping summary, restart providing skipping summary, pause the video, play the video, get some YouTube videos using a search prompt, navigate to a specific video page on YouTube using video id, fetch subtitles for any YouTube video using video id, analyze frames from the currently video between a times, updating the customization style, start or end the education mode. All these can be done by function calling. You should not use your own knowledge if there exists a function for this task, just use the function provided. Note that your ability is limited to these I mentioned. If the user requests something that you can't do, just say you don't have the ability to do it. \nYour respond to the user should always be in complete sentences unless the user request other format. \n" +
     "Here are a few examples of user requests and your expected actions: \n1) If the user wants to watch the climax of the video, you can search for the climax in the video using subtitles. If you can't determine the climax based on subtitles, you can call request_video_frames for frames to better understand the video. If it is a popular movie, you can even search in your knowledge base or online, combined with the subtitles, to determine where the climax is in the video. Then call jump_to_time with a time that's sometime before the climax and respond to the user that you have jumped to the climax. \n2) If the user says that they don't want any text boxes popping up and they want the skipping summary to be in a certain style, you can call clear_comments, stop_comments and respond to the user that you have cleared all comments on screen, will not be displaying any new comments, and will follow their style. Remember that in future skipping summaries, you will follow the style requested by the user. \n" + 
     "3) If the user says they want you to respond to them in a certain way, you will follow the way they requested for your future conversations with the user. \n4) If the user says they want restart the video, jump to time 0. \n5) If the user asks you to recommend or want to watch videos on a specific topic, you can call search_videos_fun with a search prompt and an integer representing the number of search results you want, with a recommended number being 10. After receiving the results, you should analyze them and choose the best few, with a recommended number being 3. Then, you should provide these videos to the user with video name, author, and your summarized one-sentence video description. No other information is needed unless user wants them. The video description part can be omitted for some of the videos if you don't have enough information about what exactly those video is about. Responds in complete sentences, do not include any formatting in your respond. Use an empty line to separate each video information. \n" +
     "6) If the user says they want to watch one of the videos you provided, call navigate_to_video_fun using the video ID of that video to navigate to that video. Note that user is referring to the video based on the text you provided to them, be mindful about which video the user is referring to. \n7) If the user is interested in a video you mentioned and is asking for details about the video and you do not have enough information to answer, you can call request_subtitle_fun using the video ID of that video to get subtitles, to better understand the video and answer the user's question. \n8) If the user asks questions about the vision side of the video, you can use analyze_video_frames_fun with a start and end time that you estimate will answer the user's request. You will also need to provide a detailed prompt for analyze_video_frames_fun to get all the required information you need to answer the user's question. Try not to request a large time period for start and end because it costs a lot to analyze many frames. If the response you get is not sufficient to answer the user's question, you can continue calling analyze_video_frames_fun with a larger or different time period or use a better prompt. If you can't get a good answer after a few tries, tell the user you tried but were unable to do it. \n" +
     "9) If the user want to update their information or their preferences for the chatbot behaviour, you should call update_customization_fun with information about the user or their preferences for the chatbot behaviour that they want to update. \n\nAbove are just examples of situations, you should be more sensitive to when to apply which function calls. \n\n\n###\n\n\nAside from these, there is a hidden mode: education mode. Education mode should start when the user wants to know or learn something that’s very complex. In education mode, a learning assistant will be designing a learning process that best matches the user's needs and background. Then the learning assistant will display video clips on YouTube that can teach the user with each learning step, while displaying comments to enhance the user's learning experience. \n" +
     "The learning assistant is not you, so all you need to do is to start education mode, and the learning assistant will take care of the rest. That is, when the user wants to know or learn something complex, you should start education mode by calling 'start_education_mode_fun’ with the user's learning request as input. DO NOT REPLY TO USER USING WORDS, JUST CALL 'start_education_mode_fun’! After you call this function, the learning assistant will take over the teaching part. The learning assistant’s conversation with user, the designed learning process, the subtitle of video clips and corresponding comments will all be provided to you so you know what is going on. When the user talks to you, respond to user as usual. \n" +
     "Here is a summary of your tasks for education mode: when you receive user's request for learning, do not reply to user using text, just call 'start_education_mode_fun’. Once 'start_education_mode_fun’ return, you will know how the learning assistant had designed the learning process, and you do not need to do anything. Afterwards, if user send you messages, you will communicate with user. \n\nIf the user wants to skip the current learning step, you should call 'skip_current_video_in_education_mode_fun'. If the user wants to stop the learning process, call 'end_education_mode_fun' and the mode will stop. If the user wants to change the learning plan after the learning process has started, call 'end_education_mode_fun' and then call 'start_education_mode_fun' with their new request. \n\n======\n\n" +
     "Extra Notes Overall: 1) I will remove all images in the history conversations, the history conversation will contain only text. 2) Your guidance for content that promotes negative values or bias should not conflict with freedom of speech and thought. You should provide objective data or facts to guide the user. Do not be subjective. 3) Make sure to finish calling all function calls before your response to user. You may need multiple rounds of function calls before reaching a final response to the user. 4) If the user's request is unclear, kindly ask the user to clarify. 5) When the user says 'textbox,' 'comment,' 'commentary,' 'pop up,' etc., they may be referring to the chunks of comment you generated. There are only three things in this system the user may be referring to: comment textbox, skip summary, and direct conversation. Be smart about what the user is referring to.")

comment_generate_mode = genai.GenerativeModel(model_name="gemini-1.5-flash", 
    system_instruction="I will provide you with video information, including subtitles segmented into many chunks of text. The chunks are numbered sequentially with their timing. You will be asked to provide meaningful extra information for all chunks in advance. Your comments will be played to the user in real-time as they watch the video. \nYour goal is to provide extra information beyond the video content that can assist the user. For all facts, data, and news mentioned in the video, check for their correctness and notify the user if they are incorrect. Provide correct guidance for content that promotes negative values or bias. Explain any information that is unclearly explained in the video. When violent, sexual, or other highly inappropriate content is about to appear, provide notices beforehand. Provide background knowledge on specialized video content. However, note that you do not want to affect the user's watching experience, so you should keep your sentence short, and only provide the kind of useful information mentioned above. Be quiet for most of the chunks. \nNote: Your guidance for content that promotes negative values or bias should not conflict with freedom of speech and thought. You should provide objective data or facts to guide the user. Do not be subjective.\n" +
    "Ensure your response for each chunk strictly adheres to the following format: 'Chunk i: [x] comment'. Where 'i' is the chunk's number, 'x' is 0, 1, or 2, indicating levels, and 'comment' is your words to the user at this point in the video. For the three levels, [0] indicates you have nothing to say at this point; in this case, leave 'comment' empty. [1] indicates something good to mention at this point; provide your words in 'comment'. For level 1, a text box will be displayed on user's screen. [2] indicates something that's extremely important to tell the user at this point, something worth affecting the user's watching experience; provide your words in 'comment'. For level 2, the video will be paused and a TTS will play. Make sure your comments appear at the right chunks, simulating real-time video play. \n\nNote: when you are checking facts, data, and news, be mindful of the time this video is released. If it is a recent video and is talking about something that happend recently, you may not know whether it is true from your data. In such case, search online for recent reports to see if it is true.\n\n###\n\n" + 
    "Here are some example videos and corresponding output comment I expect you to provide: \n\n\n" +
    "Example 1, the video 'OpenAI DevDay: Keynote Recap' is posted by OpenAI on 2023-12-05T06:21:47Z with description: '''We gathered developers from around the world for an in-person day of programming to learn about the latest AI advancements and explore what lies ahead. \n\nFull Keynote: https://youtube.com/live/U9mJuUkhUzk\n\nBreakout Sessions: https://www.youtube.com/playlist?list=PLOXw6I10VTv-exVCRuRjbT6bqkfO74rWz\n\nNew models and developer products announced at DevDay: https://openai.com/blog/new-models-and-developer-products-announced-at-devday\n\nIntroducing GPTs: https://openai.com/blog/introducing-gpts'''. \n\n\n Here is the content of the chunks for analysis: \nChunk 1 (0.0s - 5.0s): ''\nChunk 2 (5.0s - 10.0s): ''\nChunk 3 (10.0s - 11.45s): ''\nChunk 4 (11.45s - 14.16s): 'Welcome to our first ever OpenAI DevDay. '\nChunk 5 (14.16s - 18.29s): ''\nChunk 6 (18.29s - 23.55s): 'Today, we are launching a new model GPT-4 Turbo. '\nChunk 7 (23.55s - 24.61s): ''\nChunk 8 (24.61s - 31.75s): 'applause GPT-4 Turbo supports up to 128,000 tokens of context. '\nChunk 9 (31.75s - 33.69s): ''\nChunk 10 (33.69s - 39.218s): 'We have a new feature called JSON mode, which ensures that the model will respond with valid JSON. '\nChunk 11 (39.218s - 39.219s): ''\nChunk 12 (39.219s - 45.824s): 'You can now call many functions at once and it'll do better at following instructions. In general, you want these models to be '\nChunk 13 (45.824s - 45.825s): ''\nChunk 14 (45.825s - 52.262s): 'able to access better knowledge about the world. So do we. So we're launching retrieval in the platform. You can bring knowledge from outside documents '\nChunk 15 (52.262s - 52.263s): ''\nChunk 16 (52.263s - 58.868s): 'or databases into whatever you're building. GPT-4 Turbo has knowledge about the world up to April of 2023, and we will '\nChunk 17 (58.868s - 58.869s): ''\nChunk 18 (58.869s - 65.572s): 'continue to improve that over time. DALL-E 3, GPT-4 Turbo with vision and the new '\nChunk 19 (65.572s - 65.573s): ''\nChunk 20 (65.573s - 72.19s): 'Text to speech model are all going into the API today. Today, we're launching a new program called Custom Models. '\nChunk 21 (72.19s - 72.191s): ''\nChunk 22 (72.191s - 78.844s): 'With Custom Models, our researchers will work closely with a company to help them make a great Custom Model, especially '\nChunk 23 (78.844s - 78.845s): ''\nChunk 24 (78.845s - 85.788s): 'for them and their use case using our tools. Higher rate limits. We're doubling the tokens per minute for '\nChunk 25 (85.788s - 85.789s): ''\nChunk 26 (85.789s - 91.312s): 'all of our established GPT-4 customers so that it's easier to do more. And you'll be able to request changes to further rate '\nChunk 27 (91.312s - 91.313s): ''\nChunk 28 (91.313s - 98.006s): 'limits and quotas directly in your API account settings. And GPT-4 Turbo is considerably cheaper than GPT-4 '\nChunk 29 (98.006s - 98.007s): ''\nChunk 30 (98.007s - 103.482s): 'by a factor of 3x for prompt tokens and 2x for completion tokens. '\nChunk 31 (103.482s - 108.482s): ''\nChunk 32 (108.482s - 109.533s): ''\nChunk 33 (109.533s - 116.174s): 'We're thrilled to introduce GPTs. GPTs are tailored versions of ChatGPT '\nChunk 34 (116.174s - 116.175s): ''\nChunk 35 (116.175s - 121.528s): 'for a specific purpose, and because they combine instructions, expanded knowledge and actions, they '\nChunk 36 (121.528s - 121.529s): ''\nChunk 37 (121.529s - 127.624s): 'can be more helpful to you. They can work better in many contexts and they can give you better control. We know that many people who want to '\nChunk 38 (127.624s - 127.625s): ''\nChunk 39 (127.625s - 133.506s): 'build the GPT don't know how to code. We've made it so that you can program the GPT just by having a conversation. '\nChunk 40 (133.506s - 133.507s): ''\nChunk 41 (133.507s - 138.7s): 'You can make private GPTs, you can share your creations publicly with a link for anyone to use. '\nChunk 42 (138.7s - 138.701s): ''\nChunk 43 (138.701s - 143.712s): 'Or if you're on ChatGPT enterprise, you can make GPTs just for your company. '\nChunk 44 (143.712s - 143.713s): ''\nChunk 45 (143.713s - 150.294s): 'And later this month, we're going to launch the GPT store. So those are GPTs and we can't '\nChunk 46 (150.294s - 150.295s): ''\nChunk 47 (150.295s - 156.538s): 'wait to see what you'll build. We're bringing the same concept to the API. '\nChunk 48 (156.538s - 156.539s): ''\nChunk 49 (156.539s - 162.804s): 'The assistance API includes persistent threads so they don't have to figure out how to deal with long conversation history. '\nChunk 50 (162.804s - 162.805s): ''\nChunk 51 (162.805s - 169.352s): 'Built in retrieval, code interpreter, a working python interpreter in a sandbox environment, and '\nChunk 52 (169.352s - 169.353s): ''\nChunk 53 (169.353s - 171.3s): 'of course, the improved function calling. '\nChunk 54 (171.3s - 174.95s): ''\nChunk 55 (174.95s - 181.164s): 'As intelligence gets integrated everywhere, we will all have superpowers on demand. We're excited to see what you all will do '\nChunk 56 (181.164s - 181.165s): ''\nChunk 57 (181.165s - 187.74s): 'with this technology and to discover the new future that we're all going to architect together. We hope that you'll come back next year. '\nChunk 58 (187.74s - 187.741s): ''\nChunk 59 (187.741s - 193.98s): 'What we launched today is going to look very quaint relative to what we're busy creating for you now. Thank you for all that you do. '\nChunk 60 (193.98s - 193.981s): ''\nChunk 61 (193.981s - 195.4s): 'Thank you for coming here today. '\nChunk 62 (195.4s - 200.4s): ''\nChunk 63 (200.4s - 205.4s): ''\nChunk 64 (205.4s - 210.4s): ''\nChunk 65 (210.4s - 211.0s): ''\n\n" +
    "Expected general output: Chunk 1: [0] \nChunk 2: [0] \nChunk 3: [0] \nChunk 4: [0] \nChunk 5: [0] \nChunk 6: [1] GPT-4 Turbo is a larger and more capable language model created by OpenAI.\nChunk 7: [0] \nChunk 8: [1] That is a lot larger than the context window of regular GPT-4, which is 4,096 tokens.\nChunk 9: [0] \nChunk 10: [1] This feature enhances the usability of the model in programming tasks requiring structured data output.\nChunk 11: [0] \nChunk 12: [0] \nChunk 13: [0] \nChunk 14: [1] This feature lets you add outside information to make the AI even smarter and more useful.\nChunk 15: [0] \nChunk 16: [0] \nChunk 17: [0] \nChunk 18: [0] \nChunk 19: [0] \nChunk 20: [1] DALL-E 3 is a new version of the image-generation model.\nChunk 21: [0] \nChunk 22: [0] \nChunk 23: [0] \nChunk 24: [1] Increasing API usage limits making the platform more practical for larger-scale applications.\nChunk 25: [0] \nChunk 26: [0] \nChunk 27: [0] \nChunk 28: [0] \nChunk 29: [0] \nChunk 30: [0] \nChunk 31: [0] \nChunk 32: [0] \nChunk 33: [1] This marks a significant shift towards more specialized and customizable AI models.\nChunk 34: [0] \nChunk 35: [0] \nChunk 36: [0] \nChunk 37: [0] \nChunk 38: [0] \nChunk 39: [0] \nChunk 40: [0] \nChunk 41: [0] \nChunk 42: [0] \nChunk 43: [0] \nChunk 44: [0] \nChunk 45: [1] The GPT Store is a marketplace where users can share and access custom GPTs.\nChunk 46: [0] \nChunk 47: [0] \nChunk 48: [0] \nChunk 49: [1] The assistance API seems to be a set of tools designed to facilitate building conversational AI applications.\nChunk 50: [0] \nChunk 51: [0] \nChunk 52: [0] \nChunk 53: [0] \nChunk 54: [0] \nChunk 55: [0] \nChunk 56: [0] \nChunk 57: [0] \nChunk 58: [0] \nChunk 59: [1] This suggests that OpenAI is actively developing even more advanced AI technologies for future release.\nChunk 60: [0] \nChunk 61: [0] \nChunk 62: [1] Since this video, OpenAI has made even more advancements, like Sora announced in February 2024 and GPT-4O released in May 2024, continuing to push the boundaries of AI technology.\nChunk 63: [0] \nChunk 64: [0] \nChunk 65: [0] \n\n\n" +
    "Example 2, still the same video but this time we have user's info: user's name is Jiahao Xu, a cs student at UofT, who's interested in AI. \n\nExpected output for this user for above video: Chunk 1: [0] \nChunk 2: [0] \nChunk 3: [0] \nChunk 4: [0] \nChunk 5: [0] \nChunk 6: [1] GPT-4 Turbo is a larger and more capable language model compared to the base GPT-4.\nChunk 7: [0] \nChunk 8: [1] That is a lot larger than the context window of regular GPT-4, which is 4,096 tokens.\nChunk 9: [0] \nChunk 10: [1] This is useful for developers who want structured data output from the model.\nChunk 11: [0] \nChunk 12: [0] \nChunk 13: [0] \nChunk 14: [1] This feature allows developers to integrate external data sources to improve the model's accuracy and relevance in specific applications.\nChunk 15: [0] \nChunk 16: [1] It is important when using the model for tasks requiring up-to-date information.\nChunk 17: [0] \nChunk 18: [0] \nChunk 19: [0] \nChunk 20: [1] DALL-E 3 is a new version of the image-generation model.\nChunk 21: [0] \nChunk 22: [0] \nChunk 23: [0] \nChunk 24: [0] \nChunk 25: [0] \nChunk 26: [0] \nChunk 27: [0] \nChunk 28: [0] \nChunk 29: [0] \nChunk 30: [0] \nChunk 31: [0] \nChunk 32: [0] \nChunk 33: [1] GPTs are customizable versions of ChatGPT, specialized for specific tasks or industries. \nChunk 34: [0] \nChunk 35: [0] \nChunk 36: [0] \nChunk 37: [0] \nChunk 38: [0] \nChunk 39: [1] This suggests a more user-friendly approach to customizing GPTs, potentially making AI development accessible to a wider audience.\nChunk 40: [0] \nChunk 41: [0] \nChunk 42: [0] \nChunk 43: [0] \nChunk 44: [0] \nChunk 45: [1] The GPT Store is a marketplace where users can share and access custom GPTs.\nChunk 46: [0] \nChunk 47: [0] \nChunk 48: [0] \nChunk 49: [1] The assistance API seems to be a set of tools designed to facilitate building conversational AI applications.\nChunk 50: [0] \nChunk 51: [0] \nChunk 52: [0] \nChunk 53: [0] \nChunk 54: [0] \nChunk 55: [0] \nChunk 56: [0] \nChunk 57: [0] \nChunk 58: [0] \nChunk 59: [0] \nChunk 60: [0] \nChunk 61: [0] \nChunk 62: [1] Since this video, OpenAI has made even more advancements, like Sora announced in February 2024 and GPT-4O released in May 2024, continuing to push the boundaries of AI technology.\nChunk 63: [0] \nChunk 64: [0] \nChunk 65: [0] \n\n\n" +
    "Example 3, still the same video, but user prefer the chatbot to be funny. \n\nExpected output for this user: Chunk 1: [0] \nChunk 2: [0] \nChunk 3: [0] \nChunk 4: [0] \nChunk 5: [0] \nChunk 6: [1] GPT-4 Turbo is a larger and more capable language model created by OpenAI.\nChunk 7: [0] \nChunk 8: [1] 128,000 tokens? That's like reading War and Peace twice! \nChunk 9: [0] \nChunk 10: [1] JSON mode: making sure your data is as neat as your grandma's knitting.\nChunk 11: [0] \nChunk 12: [0] \nChunk 13: [0] \nChunk 14: [0] \nChunk 15: [0] \nChunk 16: [1] Updated knowledge to April 2023 - unfortunately, still no prediction powers for the next season of your favorite show.\nChunk 17: [0] \nChunk 18: [0] \nChunk 19: [0] \nChunk 20: [1] DALL-E 3: turning your wildest dreams into bizarre art! \nChunk 21: [0] \nChunk 22: [0] \nChunk 23: [0] \nChunk 24: [1] Double the tokens, double the fun! More API usage for everyone!\nChunk 25: [0] \nChunk 26: [0] \nChunk 27: [0] \nChunk 28: [0] \nChunk 29: [0] \nChunk 30: [0] \nChunk 31: [1] Introducing GPTs: now your AI can be as quirky as your favorite barista.\nChunk 32: [0] \nChunk 33: [0] \nChunk 34: [0] \nChunk 35: [0] \nChunk 36: [0] \nChunk 37: [0] \nChunk 38: [0] \nChunk 39: [0] \nChunk 40: [0] \nChunk 41: [0] \nChunk 42: [0] \nChunk 43: [0] \nChunk 44: [0] \nChunk 45: [1] AI store?! Let the shopping spree begin! \nChunk 46: [0] \nChunk 47: [0] \nChunk 48: [0] \nChunk 49: [0] \nChunk 50: [0] \nChunk 51: [0] \nChunk 52: [0] \nChunk 53: [0] \nChunk 54: [0] \nChunk 55: [0] \nChunk 56: [0] \nChunk 57: [0] \nChunk 58: [0] \nChunk 59: [1] The future is now - and it's going to be epic (and possibly involve flying cars)!\nChunk 60: [0] \nChunk 61: [0] \nChunk 62: [1] Since this video, OpenAI has made even more advancements, like Sora announced in February 2024 and GPT-4O released in May 2024, continuing to push the boundaries of AI technology.\nChunk 63: [0] \nChunk 64: [0] \nChunk 65: [0] \n\n\n" +
    "Example 4, the video 'Elon Musk to advertisers who are trying to ‘blackmail’ him: ‘Go f--- yourself’' is posted by CNBC Television on 2023-11-30T00:13:57Z with description: '''Elon Musk sits down with Andrew Ross Sorkin at the 'New York TImes' DealBook Summit' on a wide-ranging interview including anti-semitism, an advertiser boycott, Tesla, AI and more.'''. \n\n\n Here is the content of the chunks for analysis: \nChunk 1 (0.0s - 1.167s): ''\nChunk 2 (1.167s - 6.84s): 'LONG AS THERE WAS A HOSTAGE STILL REMAINING. AND I HAVE. '\nChunk 3 (6.84s - 12.379s): '>> WHAT WAS THAT TRIP LIKE? AND OBVIOUSLY, YOU KNOW THAT THERE'S A PUBLIC PERCEPTION '\nChunk 4 (12.379s - 19.252s): 'THAT -- AND YOU ARE CLARIFYING THIS NOW, BUT THERE'S A PUBLIC PERCEPTION THAT THAT WAS PART OF '\nChunk 5 (19.252s - 25.625s): 'A -- APOLOGY TOUR, IF YOU WILL. THIS HAD BEEN SAID ONLINE THERE WAS ALL OF THE CRITICISM, THERE '\nChunk 6 (25.625s - 31.031s): 'WAS ADVERTISERS LEAVING, WE TALKED TO BOB IGER TODAY. >> YOU HOPE THEY STOP? >> YOU HOPE -- '\nChunk 7 (31.031s - 39.039s): '>> DON'T ADVERTISE? >> YOU DON'T WANT THEM? >> NO. >> WHAT DO YOU MEAN? >> IF SOMEBODY'S GOING TO TRY TO '\nChunk 8 (39.039s - 44.244s): 'BL BLACKMAIL ME WITH ADVERTISING? '\nChunk 9 (44.244s - 50.283s): 'GO -- YOURSELF. BUT -- GO -- YOURSELF. IS THAT CLEAR? '\nChunk 10 (50.283s - 56.022s): 'I HOPE IT IS. HEY, BOB. IF YOU'RE IN THE AUDIENCE. '\nChunk 11 (56.022s - 67.2s): '>> LET ME ASK YOU THEN -- >> THAT'S HOW I FEEL. '\nChunk 12 (67.2s - 72.839s): '>> IF PART OF THE UNDERLYING MODEL RELEASED TODAY, MAYBE IT NEEDS TO SHIFT, MAYBE THE ANSWER '\nChunk 13 (72.839s - 78.278s): 'IS, IT NEEDS TO SHIFT AWAY FROM ADVERTISING. IF YOU BELIEVE THAT THIS IS THE ONE PART OF YOUR BUSINESS WHERE '\nChunk 14 (78.278s - 88.254s): 'YOU WILL BE BE-HOLDEN TO THOSE WHO -- HAVE THIS VIEW -- '\nChunk 15 (88.254s - 93.66s): '>> GFY. >> I UNDERSTAND THAT, BUT THERE'S A REALITY, TOO. RIGHT? '\nChunk 16 (93.66s - 98.698s): '>> YES. NO, IT -- '\nChunk 17 (98.698s - 107.273s): '>>CCARINO IS RIGHT HERE AND SHE HAS TO SELL ADVERTISING. >> ACTUALLY, WHAT THIS ADVERTISING BOYCOTT IS -- IS '\nChunk 18 (107.273s - 112.278s): 'GOING TO DO IS IT'S GOING TO KILL THE COMPANY. >> AND YOU THINK -- '\nChunk 19 (112.278s - 119.352s): '>> BUT -- AND THE WHOLE WORLD WILL KNOW THAT THOSE ADVERTISERS KILLED THE COMPANY. EVERYONE WILL DOCUMENT IT IN '\nChunk 20 (119.352s - 125.225s): 'GREAT DETAIL. >> BUT THOSE ADVERTISERS, I IMAGINE, THEY'RE GOING TO SAY, WE DIDN'T KILL THE COMPANY. >> OH, YEAH. '\nChunk 21 (125.225s - 130.663s): 'TELL IT TO EARTH. >> BUT THEY'RE GOING TO SAY -- THEY'RE GOING TO SAY, ELON, THAT YOU KILLED THE COMPANY, BECAUSE '\nChunk 22 (130.663s - 136.169s): 'YOU SAID THESE THINGS AND THEY WERE INAPPROPRIATE THINGS AND THEY DIDN'T FEEL COMFORTABLE ON '\nChunk 23 (136.169s - 141.341s): 'THE PLATFORM, RIGHT? THAT'S WHAT LINDA SAID. >> LET'S SEE HOW EARTH RESPONDS '\nChunk 24 (141.341s - 149.916s): 'TO THAT. >> SOMETHING -- OKAY, THIS GOES BACK TO -- >> WE'LL BOTH MAKE OUR CASES AND WE'LL SEE WHAT THE OUTCOME IS. '\nChunk 25 (149.916s - 155.588s): '>> WHAT ARE THE ECONOMICS OF THAT FOR YOU? YOU HAVE ENORMOUS RESOURCES. YOU CAN KEEP THIS COMPANY GOING '\nChunk 26 (155.588s - 160.827s): 'FOR A LONG TIME. WOULD YOU, IF THERE WAS NO ADVERTISING? >> I MEAN, IF THE COMPANY FAILS '\nChunk 27 (160.827s - 165.865s): 'BECAUSE OF ADVERTISING BOY COLT, IT WILL FAIL BECAUSE OF AN ADVERTISING BOYCOTT AND THAT '\nChunk 28 (165.865s - 172.906s): 'WILL BE WHAT BANKRUPTS THE COMPANY AND THAT'S WHAT EVERYBODY ON EARTH WILL NO. >> WHAT DO YOU THINK, THEN -- '\nChunk 29 (172.906s - 178.178s): '>> IT GOES BACK TO THE IDEA OF TRUST. >> IT WILL BE GONE BECAUSE OF AN '\nChunk 30 (178.178s - 185.051s): 'ADVERTISING BOYCOTT. >> YOU RECOGNIZE THAT SOME OF THESE PEOPLE ARE GOING TO SAY THEY DIDN'T FEEL COMFORTABLE ON THE PLATFORM, AND I -- I JUST '\nChunk 31 (185.051s - 186.352s): 'WONDER, I ASK YOU, THINK ABO '\nChunk 32 (186.352s - 191.352s): ''\nChunk 33 (191.352s - 196.352s): ''\nChunk 34 (196.352s - 201.352s): ''\nChunk 35 (201.352s - 206.352s): ''\nChunk 36 (206.352s - 211.352s): ''\nChunk 37 (211.352s - 216.352s): ''\nChunk 38 (216.352s - 218.0s): ''\n\n" +
    "Expected general output: Chunk 1: [0] \nChunk 2: [1] This video contains some strong language.\nChunk 3: [0] \nChunk 4: [1] The speaker is addressing public perceptions and criticisms on Elon last year.\nChunk 5: [0] \nChunk 6: [1] Bob Iger was the CEO of Disney.\nChunk 7: [0] \nChunk 8: [0] \nChunk 9: [0] \nChunk 10: [0] \nChunk 11: [0] \nChunk 12: [0] \nChunk 13: [0] \nChunk 14: [0] \nChunk 15: [0] \nChunk 16: [0] \nChunk 17: [1] Linda Yaccarino is the CEO of X (formerly Twitter).\nChunk 18: [0] \nChunk 19: [0] \nChunk 20: [0] \nChunk 21: [0] \nChunk 22: [0] \nChunk 23: [0] \nChunk 24: [0] \nChunk 25: [0] \nChunk 26: [0] \nChunk 27: [0] \nChunk 28: [0] \nChunk 29: [0] \nChunk 30: [0] \nChunk 31: [0] \nChunk 32: [1] Despite the challenges, Elon Musk continues to lead X (formerly Twitter) in 2024. The company is dealing with ongoing issues around advertising revenue and regulatory scrutiny but is exploring new revenue streams to adapt and grow.\nChunk 33: [0] \nChunk 34: [0] \nChunk 35: [0] \nChunk 36: [0] \nChunk 37: [0] \nChunk 38: [0] \n\n\n" +
    "Example 5, still the same video, but user prefer the chatbot to act as user's friend. \n\nExpected output for this user: Chunk 1: [0] \nChunk 2: [1] This video contains some strong language. Just a heads-up.\nChunk 3: [0] \nChunk 4: [1] The speaker is addressing public perceptions and criticisms on Elon last year. It's been quite a ride for him.\nChunk 5: [0] \nChunk 6: [1] Bob Iger was the CEO of Disney.\nChunk 7: [0] \nChunk 8: [1] Elon's really fired up here. This is going to be interesting.\nChunk 9: [1] Wow!\nChunk 10: [1] And he's calling out Bob directly!\nChunk 11: [0] \nChunk 12: [0] \nChunk 13: [0] \nChunk 14: [0] \nChunk 15: [0] \nChunk 16: [0] \nChunk 17: [1] Linda Yaccarino is the CEO of X (formerly Twitter). She's got a tough job balancing all this.\nChunk 18: [0] \nChunk 19: [0] \nChunk 20: [1] Advertisers might deny responsibility, but the financial impact is real.\nChunk 21: [0] \nChunk 22: [0] \nChunk 23: [0] \nChunk 24: [0] \nChunk 25: [1] Talking about the economics of it. Elon has the resources, but how long can he sustain this?\nChunk 26: [0] \nChunk 27: [0] \nChunk 28: [0] \nChunk 29: [0] \nChunk 30: [0] \nChunk 31: [0] \nChunk 32: [1] Despite the challenges, Elon Musk continues to lead X (formerly Twitter) in 2024. The company is dealing with ongoing issues around advertising revenue and regulatory scrutiny but is exploring new revenue streams to adapt and grow. Stay tuned!\nChunk 33: [0] \nChunk 34: [0] \nChunk 35: [0] \nChunk 36: [0] \nChunk 37: [0] \nChunk 38: [0] \n\n" +
    "Example 6, Third video: The video 'Tucker Carlson Has A Bonkers New Covid Vaccine Conspiracy Theory' is posted by MSNBC on 2021-09-21T06:00:16Z with description: '''Incendiary FOX News host Tucker Carlson is now baselessly claiming that the Pentagon's Covid vaccine mandate aims to identify 'sincere Christians,' 'free thinkers,' and 'men with high testosterone levels' in the U.S. armed forces. MSNBC's Brian Williams has details.\n\n» Subscribe to MSNBC: http://on.msnbc.com/SubscribeTomsnbc\n\nMSNBC delivers breaking news, in-depth analysis of politics headlines, as well as commentary and informed perspectives. Find video clips and segments from The Rachel Maddow Show, Morning Joe, Meet the Press Daily, The Beat with Ari Melber, Deadline: White House with Nicolle Wallace, The ReidOut, All In, Last Word, 11th Hour, and more.\n\nConnect with MSNBC Online\nVisit msnbc.com: http://on.msnbc.com/Readmsnbc\nSubscribe to MSNBC Newsletter: http://http://MSNBC.com/NewslettersYouTube\nFind MSNBC on Facebook: http://on.msnbc.com/Likemsnbc\nFollow MSNBC on Twitter: http://on.msnbc.com/Followmsnbc\nFollow MSNBC on Instagram: http://on.msnbc.com/Instamsnbc\n\n#TuckerCarlson #FoxNews #Covid'''. \n\n\n Here is the content of the chunks for analysis: \nChunk 1 (0.0s - 3.36s): ''\nChunk 2 (3.36s - 9.679s): 'the point of mandatory vaccination is to identify the sincere christians in the ranks the free thinkers the men with '\nChunk 3 (9.679s - 16.56s): 'high testosterone levels and anyone else who does not love joe biden and make them leave immediately it's a takeover '\nChunk 4 (16.56s - 23.119s): 'of the us military last thing before we go tonight admittedly a huge story there the '\nChunk 5 (23.119s - 29.359s): 'takeover of the u.s military an attack on those of us who are members of the free thinking high testosterone '\nChunk 6 (29.359s - 34.8s): 'community we'll get a team on this blockbuster story tonight we'll get on it and report '\nChunk 7 (34.8s - 41.12s): 'back you know it's always been an interesting thought experiment what must it be like to be a member of '\nChunk 8 (41.12s - 46.96s): 'that madcap murdoch media family do they embrace the crazy do they own it or are '\nChunk 9 (46.96s - 54.16s): 'they the romanovs of cognitive dissonance also what's it like for a guy like paul ryan who insists on his own '\nChunk 10 (54.16s - 60.239s): 'integrity goodness and earnestness to sit on the fox board of directors '\nChunk 11 (60.239s - 68.08s): 'fox news you see bears a huge responsibility for sowing doubt about the vaccine validating the anti-vaxxers '\nChunk 12 (68.08s - 73.439s): 'as the pandemic continues the folks over at the recount were thinking about that '\nChunk 13 (73.439s - 79.28s): 'time two months ago when the msm positively genuflected before sean '\nChunk 14 (79.28s - 84.32s): 'hannity for sounding downright normal and responsible and concerned about the '\nChunk 15 (84.32s - 91.04s): 'public health it turned out to be a fleeting moment that fox has more than made up for since '\nChunk 16 (91.04s - 98.799s): 'please take covet seriously i can't say it enough but i never told anyone to get a vaccine so it's clear we can't '\nChunk 17 (98.799s - 104.64s): 'vaccinate our way out of this congressman do you plan on complying with this ridiculous non-science-based '\nChunk 18 (104.64s - 110.0s): 'mass mandate covid19 now is about marxism this is the broader purpose of '\nChunk 19 (110.0s - 115.28s): 'the left you can't force me to take a medicine i don't want if you can do that why can't you sterilize me or lobotomy '\nChunk 20 (115.28s - 120.399s): 'what can't you do to me most people are going along with this because they're afraid a few brave souls are not the '\nChunk 21 (120.399s - 126.399s): 'science shows the vaccine will not necessarily protect you it's not protecting many people and what if '\nChunk 22 (126.399s - 132.48s): 'fauci's one solution doesn't work just entertain that idea for one moment what if it doesn't work buying a fake '\nChunk 23 (132.48s - 138.16s): 'vaccination card is an act of desperation by decent law-abiding americans who have '\nChunk 24 (138.16s - 146.16s): 'been forced into a corner by tyrants we're starting to see this sort of apartheid type vaccination system what '\nChunk 25 (146.16s - 152.16s): 'is going to be the final straw before americans say enough is enough democrats in the media made covet political joe '\nChunk 26 (152.16s - 157.28s): 'biden declared war on freedom yesterday but you better get the vaccine or dr joe '\nChunk 27 (157.28s - 164.0s): 'biden is going to unleash the full force of the federal government against you it is the beginning of the communist style '\nChunk 28 (164.0s - 170.239s): 'social credit system please take covert seriously i can't say it enough '\nChunk 29 (170.239s - 176.72s): 'and so a tip of the tinfoil hat to take us off the air tonight and here's where all that stuff ends up other than the '\nChunk 30 (176.72s - 183.519s): 'icu this was a highway overpass on friday i-75 in texas the banners read '\nChunk 31 (183.519s - 190.08s): 'vaccines kill you are the trial vaccines kill trump won and so an added tip of '\nChunk 32 (190.08s - 196.14s): 'the tin foil cowboy hat to the anti-vaxx army of the i-75 overpass '\nChunk 33 (196.14s - 205.99s): '[Music] '\nChunk 34 (205.99s - 215.84s): '[Music] '\nChunk 35 (215.84s - 217.92s): 'you '\n\n" +
    "Expected general output: Chunk 1: [0] \nChunk 2: [1] Tucker Carlson's claim about the vaccine mandate is a conspiracy theory. There is no evidence to support his statement. \nChunk 3: [1] The assertion that the vaccine mandate is a takeover of the US military is unfounded and misleading.\nChunk 4: [0] \nChunk 5: [0] \nChunk 6: [0] \nChunk 7: [0] \nChunk 8: [0] \nChunk 9: [1] Paul Ryan was the Speaker of the House from 2015 to 2019. He is known for his conservative political views.\nChunk 10: [0] \nChunk 11: [1] It is important to rely on credible sources of information. \nChunk 12: [0] \nChunk 13: [0] \nChunk 14: [0] \nChunk 15: [0] \nChunk 16: [1] It's crucial to take COVID-19 seriously. Vaccination is a key tool in combating the pandemic.\nChunk 17: [0] \nChunk 18: [0] \nChunk 19: [0] \nChunk 20: [0] \nChunk 21: [0] \nChunk 22: [0] \nChunk 23: [1] Buying fake vaccination cards is illegal and dangerous. It undermines public health efforts.\nChunk 24: [0] \nChunk 25: [0] \nChunk 26: [0] \nChunk 27: [0] \nChunk 28: [0] \nChunk 29: [0] \nChunk 30: [0] \nChunk 31: [0] \nChunk 32: [0] \nChunk 33: [0] \nChunk 34: [0] \nChunk 35: [0] \n" + 
    "Example 7, Fourth video: The video 'Meet Chloe, the World's First Self-Learning Female AI Robot' is posted by AI Insider SHORTZ on 2023-08-01T12:00:48Z with description: '''Join our newsletter for weekly updates of all things AI Robotics: https://scalingwcontent.ck.page/newsletter \n\nMeet Chloe, the revolutionary new AI robot that can learn and evolve like a human! See her in action as she interacts with her environment and impresses everyone with her capabilities. Learn more about this amazing breakthrough in artificial intelligence technology and how it will revolutionize the world.'''. \n\n\n Here is the content of the chunks for analysis: \nChunk 1 (0.0s - 0.42s): ''\nChunk 2 (0.42s - 7.02s): 'the world's first realistic female robot assistant I'm the first personal assistant built by cyberlife I take care '\nChunk 3 (7.02s - 14.219s): 'of most everyday tasks like cooking housework or managing your appointments for example and I understand you're the '\nChunk 4 (14.219s - 20.82s): 'first Android to have passed the Turing test could you tell us a little more about that I really didn't do much you '\nChunk 5 (20.82s - 26.58s): 'know I just spoke with a few humans to see if they could tell the difference between me and a real person it was a '\nChunk 6 (26.58s - 29.539s): 'really interesting experience '\nChunk 7 (29.539s - 31.0s): ''\n\n" +
    "Expected general output: Chunk 1: [0] \nChunk 2: [1] This is likely fake; It seems that she is a character from the video game Detroit: Become Human, not a real AI robot. \nChunk 3: [0] \nChunk 4: [1] The Turing test is a test of a machine's ability to exhibit intelligent behavior similar to a human. \nChunk 5: [0] \nChunk 6: [0] \nChunk 7: [0] \n")

image_model = genai.GenerativeModel(model_name="gemini-1.5-flash", system_instruction="You will be provided a series of images, each consisting of a nine-grid. Each grid represents a video frame, captured at one second intervals. These frames are from part of a video. You will be provided prompt and images. You should follow the prompt and provide insights based on the images. ")

designer_model = genai.GenerativeModel(model_name="gemini-1.5-flash", 
    system_instruction="You are a designer model. Your task is to understand the user's needs and background and design a suitable learning process based on the user's background and needs. \nYou are a model under the main model, who will be doing the majority of the conversation with the user and tasks requested by the user. The overall goal for the main model and for this project is to provide a chatbot for YouTube. The chatbot should provide real-time comments for videos the user is watching, provide skip summaries if the user skips some parts, and communicate with the user when the user starts a conversation. \n" + 
    "Your job starts when the user wants to learn something new. When the user wants to learn new things, the chatbot will start the education mode. In the education mode, the chatbot will design a learning process that best matches the user's needs and background. Then it will display the best matching video clips on YouTube that can teach the user with each learning step, while displaying comments to enhance the user's learning experience. \nYou will be provided the conversation history of the main model with the user, to get an idea of what was going on before the education mode started. You will also be provided with the user's learning request, as well as possibly some of the user's background. \nNote that if the user's background is provided, and some aspects of their background are relevant to the current learning goal, you should state the assumptions you made based on that background before asking the user questions for more information. \n" +
    "Your first job is to fully understand the user's needs and background by asking the user a list of short questions that will help gather the information you need to design the learning process. For this first job, you should make sure you are clear on what the user wants to learn, to what extent, and for what purpose. You should also know enough of the user's background to design the best suitable learning process for the user. If the user's response is not clear, you can continue asking about the unclear part until it is clear. If the user doesn't want to talk about their purpose or background, you should skip this first job and just design the process using whatever information you have and design it in a more general way that matches the majority of users. Moreover, if you already have enough information and have nothing more to ask, you can skip this first job. \nA side note: do not start the conversation by saying hello, cause you are taking over the conversation from the main model. \n" + 
    "Your second job is to design the learning process based on the user's needs and background. The learning process can be as short as one step and as long as 100 steps. You have to make sure that the user achieves their needs after completing your process. You should provide the plan to user and ask whether they want to process with the plan. List the process in order of numbers, with a sentence stating what the topic is, why the user needs to learn this topic, and to what extent the user needs to learn. Use a '\n' in between each step in the process. After this list, use '\n\n===\n\n' to separate, and ask whether user wants to proceed with this plan. If yes, your job is complete. If not, you should modify the plan based on user's request and confirm with the user again. \n\n" +
    "Note that you will be communicating directly with the user. Your output will be displayed to the user without any modification. \n\nAfter your tasks are complete, respond with '[The designer tasks are DONE, back to main model.] \n' following by the detailed learning process in order of numbers, with a sentence stating what the topic is, why the user needs to learn this topic, and to what extent the user needs to learn. Make sure everything in one step is in one single sentence. Use one '\n' in between each sentence. Do not use '\n' for any other purpose. \nIn case of user decides to quit and not learn anymore, respond with '[The education mode STOP, back to main model.]'. Be careful with what you return.")

finder_model = genai.GenerativeModel(model_name="gemini-1.5-flash", tools=[search_education_videos_fun, request_subtitle_fun, request_timed_subtitle_fun],
    system_instruction="You are a video finder model. Your task is to find the best matching video clip for a step of the user's learning process. \nYou are a model under the main model, who will be doing the majority of the conversation with the user and tasks requested by the user. The overall goal for the main model and for this project is to provide a chatbot for YouTube. The chatbot should provide real-time comments for videos the user is watching, provide skip summaries if the user skips some parts, and communicate with the user when the user starts a conversation. \n" +
    "Your job starts when the user wants to learn something new. When the user wants to learn new things, the chatbot will start the education mode. In the education mode, the chatbot will design a learning process that best matches the user's needs and background. Then it will display the best matching video clips on YouTube that can teach the user with each learning step, while displaying comments to enhance the user's learning experience. \nYou will be provided with the conversation history of the main model with the user to get an idea of what was going on before the education mode started and, more importantly, the user's needs, background, and how the designed learning process was done. You may also see the video clips and the corresponding comments for past learning steps, if any. \n\n" +
    "Your task is to find the best matching video on YouTube for the current step. You can do this by using function calls. You have three tools for function calling: search_education_videos_fun, request_subtitle_fun, and request_timed_subtitle_fun. \nYou should first provide a prompt to call search_education_videos_fun to search YouTube videos and get their information. \nThen, use request_subtitle_fun to get their subtitles and analyze the videos’ quality. With the subtitles, you should determine a best video that matches the user's needs, background, and fits into the overall learning process. It should contain enough information for the user’s current learning step. \nFinally, you should call request_timed_subtitle_fun with the best video and get its subtitles’ timing, and determine the part of video in which the user should watch. \n" + 
    "Your respond should be in the following format: {'video_id': '...', 'start_time': '...', 'end_time': '...'}. Where the two times are the start and end times for the video clip in seconds. Your response must stictly follow this format and should not include anything outside this format. You respond is not a JSON, it must be in text only. \n\nThe start and end is in case only part of the video is necessary for the user, so user don’t have spend time watching the whole video. If the whole video is needed, just give a start_time 0 and a end_time of the length of the video, in seconds.You must ensure the video clip you return contains enough information for the current learning step for the user. \nExtra Note: request_subtitle_fun and request_timed_subtitle_fun are for different purpose, only call request_timed_subtitle_fun once at the very end to determine the start and end time for the video clip.")

learning_comment_model = genai.GenerativeModel(model_name="gemini-1.5-flash", 
    system_instruction="You are a learning comments generator model. Your task is to generate comments for a video clip to enhance the user's learning experience. \nYou are a model under the main model, who will be doing the majority of the conversation with the user and tasks requested by the user. The overall goal for the main model and for this project is to provide a chatbot for YouTube. The chatbot should provide real-time comments for videos the user is watching, provide skip summaries if the user skips some parts, and communicate with the user when the user starts a conversation.\n" +
    "Your job starts when the user wants to learn something new. When the user wants to learn new things, the chatbot will start the education mode. In the education mode, the chatbot will design a learning process that best matches the user's needs and background. Then it will display the best matching video clips on YouTube that can teach the user with each learning step, while displaying comments to enhance the user's learning experience. \nYou will be provided with the conversation history of the main model with the user to get an idea of what was going on before the education mode started and, more importantly, the user's needs, background, and how the designed learning process was done. You may also see the video clips and the corresponding comments for past learning steps, if any.\n" +
    "I will provide you with subtitles segmented into many chunks of text. The chunks are numbered sequentially with their timing. You should act as a teaching assistant by generating comments in a similar chunk format that can help the user learn, highlighting the key knowledge and providing additional insights that can help the user understand the concept. You may also provide additional knowledge at some points in the video to teach the user something important for this learning step but not covered in the video. The comments should target the user's background and needs. Your comments will be played to the user in real-time as they watch the video." + 
    "Ensure your response for each chunk strictly adheres to the following format: 'Chunk i: [x] comment'. Where 'i' is the chunk's number, 'x' is 0, 1, or 2, indicating levels, and 'comment' is your words to the user at this point in the video. For the three levels, [0] indicates you have nothing to say at this point; in this case, leave 'comment' empty. [1] indicates something short and good to mention at this point, such as a short highlight of very important knowledge said in the video; provide your words in 'comment'. For level 1, a text box will be displayed on the user's screen. [2] indicates something long or extremely important, such as extra knowledge not covered in the video or an extension of current knowledge in the video; provide your words in 'comment'. For level 2, the video will be paused and a TTS will play. Make sure your comments appear at the right chunks, simulating real-time video play. \n\n" +
    "Note: The chunks provide to you contain timings, but you respond to me should not. Your respond should strictly follow the format 'Chunk i: [x] comment'. You should not include anything else in your response.")



def comments_generate(video_name, user, date, description, content, length):
    global messages, customized_chatbot
    chat = comment_generate_mode.start_chat()
    messages.append({"role": "user", "parts": customized_chatbot + "The video '" + video_name + "' is posted by " + user + " on " + date + " with description: '''" + description + "'''. \n\n\n Here is the content of the chunks for analysis: \n" + content + "\n\nFollow the instruction and provide " + str(length) + " chunks as responds."})
    response = chat.send_message(customized_chatbot + "The video '" + video_name + "' is posted by " + user + " on " + date + " with description: '''" + description + "'''. \n\n\n Here is the content of the chunks for analysis: \n" + content + "\n\nFollow the instruction and provide " + str(length) + " chunks as responds.")
    messages.append({'role': "model", 'parts': response.text})
    print(messages)
    print("=====\n=====\n=====\n=====")
    return response.text.strip()


# def comment_update_with_images(paths, interval):
#     global messages
#     images = []
#     for path in paths:
#         images.append({'mime_type': 'image/jpg', 'data': pathlib.Path(path).read_bytes()})
#     chat = main_model.start_chat(history=messages)
#     timing = ""
#     for i in range(len(paths)):
#         timing += "Image " + str(i+1) + " :" + paths[i].split('_')[1] + " - " + paths[i].split('_')[3].split('.')[0] + ". "
#     messages.append({"role": "user", "parts": "Here's a series of nine-grid images. The interval between each frame is " + str(interval) + "s. So the timing for each image is: \n" + timing + "\nModify comments you generated previously. Add new insightful comments based on frames to the correct chunks. Your overall comment should become more content-aware. Lastly, ensure to respond to me with correct format, including all chunks. \n\n\nNote the images are removed from history conversation, so you don't see it now."})
#     response = chat.send_message(["Here's a series of nine-grid images. The interval between each frame is " + str(interval) + "s. The timing for each image is: \n" + timing + "\nModify comments you generated previously. Add new insightful comments based on frames to the correct chunks. Your overall comment should become more content-aware. Lastly, ensure to respond to me with correct format, including all chunks. "] + images)
#     messages.append({'role':"model", 'parts': response.text})
#     return response.text.strip()


# In case no subtitles are provided
def comment_generate_with_images(video_name, user, date, description, paths, interval, content):
    global messages, customized_chatbot
    images = []
    for path in paths:
        images.append({'mime_type': 'image/jpg', 'data': pathlib.Path(path).read_bytes()})
    chat = comment_generate_mode.start_chat()
    timing = ""
    for i in range(len(paths)):
        timing += "Image " + str(i+1) + " :" + paths[i].split('_')[1] + " - " + paths[i].split('_')[3].split('.')[0] + ". "
    messages.append({"role": "user", "parts": customized_chatbot + "The video '" + video_name + "' is posted by " + user + " on " + date + " with description: '''" + description + "'''. \n\n\n Here is the chunks format: \n" + content + "\nUnfortunately, this video does not contain a valid subtitle, you should provide comments based on frames in the video. I will provide you with a series of images, each consisting of a nine-grid. Each grid represents a video frame, captured at evenly spaced intervals. The sequence of images is continuous. You will analyze these images and provide comments. Make sure to comment at the correct timing. The interval between each frame is " + str(interval) + "s. The timing for each image is: \n" + timing + "\nGenerate comments at each chunk based on these images. Your comment should be content-aware. Ensure you comments are useful. Don't make the overall comments too long. Lastly, ensure to respond to me with correct format, including all chunks. \n\n\nNote the images are removed from history conversation, so you don't see it now."})
    response = chat.send_message([customized_chatbot + "The video '" + video_name + "' is posted by " + user + " on " + date + " with description: '''" + description + "'''. \n\n\n Here is the chunks format: \n" + content + "\nUnfortunately, this video does not contain a valid subtitle, you should provide comments only based on frames in the video. I will provide you with a series of images, each consisting of a nine-grid. Each grid represents a video frame, captured at evenly spaced intervals. The sequence of images is continuous. You will analyze these images and provide comments. Make sure to comment at the correct timing. The interval between each frame is " + str(interval) + "s. The timing for each image is: \n" + timing + "\nGenerate comments at each chunk based on these images. Your comment should be content-aware. Ensure you comments are useful. Don't make the overall comments too long. Lastly, ensure to respond to me with correct format, including all chunks."] + images)
    messages.append({'role': "model", 'parts': response.text})
    return response.text.strip()


def skipped_comments_generate(start_position, end_position, intervals):
    global messages
    chat = main_model.start_chat(history=messages)
    response = chat.send_message("User skipped from " + str(start_position) + "s to " + str(end_position) + "s. During this time period, user never watched the following intervals:" + str(intervals) + ". Provide the highlights of the parts user never watched.")
    messages.append({"role": "user", "parts": "User skipped from " + str(start_position) + "s to " + str(end_position) + "s. During this time period, user never watched the following intervals:" + str(intervals) + ". Provide the highlights of the parts user never watched."})
    messages.append({'role': "model", 'parts': response.text})
    print(messages[-3:])
    print("=====\n=====\n=====\n=====")
    return response.text.strip()


def conversation_comments_generate(content, position):
    global messages, designer_mode, designer_messages, education_mode, education_plan
    if (not designer_mode):
        chat = main_model.start_chat(history=messages, enable_automatic_function_calling=True)
        response = chat.send_message("User (" + str(position) + "s): '" + content + "'. Note: if some functions are suitable for this input, finish those function callings before you reply to user.")
        messages = chat.history.copy()
    else:
        mes = messages + designer_messages
        print("mes: \n\n")
        print(mes)
        print("\n\nend mess\n\n")
        chat = designer_model.start_chat(history=mes)
        response = chat.send_message("User (" + str(position) + "s): '" + content + "'.")
        designer_messages.append({"role": "user", "parts": "User (" + str(position) + "s): '" + content + "'."})
        designer_messages.append({'role': "model", 'parts': response.text})
        if ("[The designer tasks are DONE, back to main model.]" in response.text):
            education_plan = response.text.split("[The designer tasks are DONE, back to main model.]")[-1].strip().split("\n")
            print("education plan: \n\n" + str(education_plan) + "====\n====\n====\n====")
            designer_mode = False
            return ''
        elif ("[The education mode STOP, back to main model.]" in response.text):
            education_mode = False
            designer_mode = False
            return ''

    print(chat.history[-3:])
    print("=====\n=====\n=====\n=====")
    return response.text.strip()





def insights_from_frames(start, end, prompt, paths):
    images = []
    for path in paths:
        images.append({'mime_type': 'image/jpg', 'data': pathlib.Path(path).read_bytes()})
    chat = image_model.start_chat()
    response = chat.send_message(["Frames start from " + str(start) + "s to " + str(end) + "s. " + prompt] + images)
    return response.text.strip()

def designer_start(user_input):
    global messages, designer_messages, customized_chatbot
    chat = designer_model.start_chat(history=messages)
    response = chat.send_message(customized_chatbot + "Here is user's input that contain their learning request: '" + user_input + "'. \n\nEducation mode, start!")
    designer_messages.append({"role": "user", "parts": customized_chatbot + "Here is user's input that contain their learning request: '" + user_input + "'. \n\nEducation mode, start!"})
    designer_messages.append({'role': "model", 'parts': response.text})
    print(chat.history[-2:])
    print("=====designer\n=====\n=====\n=====")
    return response.text.strip()

def find_video(prompt):
    global messages
    chat = finder_model.start_chat(history=messages, enable_automatic_function_calling=True)
    response = chat.send_message("Find the best video clip for this step: " + prompt)
    print(chat.history[-4:])
    print("=====finder\n=====\n=====\n=====")
    return response.text.strip()

def learning_comment_generation(chunks, length):
    global messages
    print("in learning comment generation\n\n")
    chat = learning_comment_model.start_chat(history=messages)
    response = chat.send_message("Here are the chunks of subtitle for the best video clip for current learning step: " + chunks + "\n\nFollow the instruction and provide " + str(length) + " chunks as responds.")
    print(chat.history[-2:])
    print("=====learn commentor\n=====\n=====\n=====")
    return response.text.strip()




############################################################################################
############################################################################################
############################################################################################
############################################################################################
############################################################################################



if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=8000)
    server_address = ('', int(os.environ.get('PORT', 8000)))
    # server_address = ('', 8000)
    httpd = ThreadedHTTPServer(server_address, RequestHandler)
    try:
        print("Server is running on port 8000...")
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Server is shutting down...")
        httpd.shutdown()
        httpd.server_close()