from gtts import gTTS
import os
import playsound
import time
from pydub import AudioSegment
from openai import OpenAI
from datetime import timedelta
import asyncio

audio_start_time = 0
duration = 0
stop_at = 0
played = []
current_comment_time = 0
current_text = ""

# pygame.mixer.init()

# def text_to_speech(text, lang='en', rate=1.1):
#     global audio_start_time, duration
#     if os.path.exists('output.mp3'):
#         os.remove('output.mp3')
#     tts = gTTS(text=text, lang=lang, slow=False)
#     filename = "output.mp3"
#     tts.save(filename)
#     audio = AudioSegment.from_file(filename)
#     new_audio = audio.speedup(playback_speed=rate)
#     new_audio = new_audio + 8
#     new_audio.export(filename, format="mp3")
#     duration = len(new_audio) / 1000.0
#     pygame.mixer.music.load(filename)
#     audio_start_time = time.time()
#     pygame.mixer.music.play()
#     return duration



stop_thread = False

def play_one_comment(comment_time, text, first, start_time, video_time, rate, previes=False, skip=False):
    global stop_thread
    text = text.strip()
    x = int(text[1])
    if x == 0:
        return []
    text = text[3:]
    current_time = (time.time() - start_time) * rate + video_time
    sleep_time = (comment_time.seconds + 5 - current_time) / rate
    if skip:
        if text.strip() != "":
            if x == 1:
                return [1, text]
            elif x == 2:
                # len = text_to_speech(text)
                # return [2, len]
                return [2, text]
    else:
        if first == True and sleep_time < -5/rate and video_time < 2: # at start of a video
            return []
        elif first == True and sleep_time < 2/rate and not previes: # jump to the middle of a video
            return []
        elif first == True and sleep_time < -0.3 and previes: # conitnue after previes sentence when rate is changed
            return []
        elif sleep_time > 0:
            a = False
            while sleep_time > 0:
                if stop_thread:
                    a = True
                    stop_thread = False
                    break
                time.sleep(0.1)
                sleep_time -= 0.1
            if a:
                return [0]
        if text.strip() != "":
            if x == 1:
                return [1, text]
            elif x == 2:
                # len = text_to_speech(text)
                # return [2, len]
                return [2, text]



def stop_comment():
    global audio_start_time, duration, stop_at, stop_thread, played, current_comment_time, current_text
    # pygame.mixer.music.stop()
    elapsed_time = time.time() - audio_start_time
    if elapsed_time < duration:
        stop_at = elapsed_time
        if (current_comment_time, current_text) in played:
            played.remove((current_comment_time, current_text))
    else:
        if os.path.exists('output.mp3'):
            os.remove('output.mp3')
    stop_thread = True

def stop_after_finish():
    global stop_thread
    stop_thread = True
    while stop_thread:
        time.sleep(0.05)

# def continue_play():
#     global stop_at, played, current_comment_time, current_text
#     if not os.path.exists('output.mp3'):
#         return []
#     audio = AudioSegment.from_file('output.mp3')
#     new_start_position = max(0, stop_at * 1000 - 300)
#     new_audio = audio[new_start_position:]
#     new_audio.export('output.mp3', format="mp3")
#     played.append((current_comment_time, current_text))
#     pygame.mixer.music.load('output.mp3')
#     pygame.mixer.music.play()
#     p = played
#     played = []
#     return p



if __name__ == "__main__":
    subtitles = [
        (timedelta(seconds=5), "Welcome to our video presentation."),
        (timedelta(seconds=10), "This is a demonstration of synchronized text-to-speech."),
        # (timedelta(seconds=20), "Thank you for watching."),
    ]
