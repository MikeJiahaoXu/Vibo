from datetime import timedelta
import re

def srt_time_to_timedelta(time_str):
    """Convert SRT time format to a timedelta object."""
    hours, minutes, seconds, milliseconds = map(int, time_str.replace(',', ':').split(':'))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds, milliseconds=milliseconds)

def parse_srt(filename, length_of_video):
    """Parse an SRT file and return chunks of text every 5 seconds."""
    with open(filename, 'r', encoding='utf-8') as file:
        lines = file.readlines()
    
    chunks = []
    current_chunk = []
    complete_sentences = ""
    start_time = None
    start = "00:00:00,000"
    end = "00:00:00,000"
    start_time = 0
    end_time = 0
    chunk_start_time = timedelta(seconds=0)
    video_length = timedelta(seconds=length_of_video)

    for line in lines:
        line = line.strip()
        if '-->' in line:
            end_time = srt_time_to_timedelta(end)
            start, end = line.split(' --> ')
            start_time = srt_time_to_timedelta(start)
            at_beginning = False

            # Handle gaps at the beginning
            if not chunks and start_time > timedelta(seconds=0):
                at_beginning = True
                gap_start = timedelta(seconds=0)
                while gap_start < start_time:
                    gap_end = min(gap_start + timedelta(seconds=5), start_time)
                    chunks.append(("", (gap_start, gap_end)))
                    gap_start = gap_end

            if not current_chunk:
                # This is the start
                chunk_start_time = start_time
            elif end_time - chunk_start_time > timedelta(seconds=5) or start_time - end_time > timedelta(seconds=3):
                # save the current chunk
                chunks.append((''.join(current_chunk), (chunk_start_time, end_time)))
                current_chunk = []
                chunk_start_time = start_time

            # Handle gaps between chunks
            if not current_chunk and start_time > end_time and not at_beginning:
                gap_start = end_time
                while gap_start < start_time:
                    gap_end = min(gap_start + timedelta(seconds=5), start_time)
                    chunks.append(("", (gap_start, gap_end)))
                    gap_start = gap_end

        elif line.isdigit():
            continue
        elif line:
            line += ' '
            current_chunk.append(line)
            complete_sentences += line

    end_time = srt_time_to_timedelta(end)

    if current_chunk:
        # Add the last chunk if there is any
        chunks.append((''.join(current_chunk), (chunk_start_time, end_time)))

    # in case "[music]" for too long
    new_chunks = []
    for text, (start, end) in chunks:
        duration = end - start
        if duration > timedelta(seconds=12):
            num_splits = (duration // timedelta(seconds=12)) + 1
            split_duration = duration / num_splits
            for i in range(num_splits):
                split_start = start + i * split_duration
                split_end = min(split_start + split_duration, end)
                new_chunks.append((text, (split_start, split_end)))
        else:
            new_chunks.append((text, (start, end)))

    if end_time < video_length:
        gap_start = end_time
        while gap_start < video_length:
            gap_end = min(gap_start + timedelta(seconds=5), video_length)
            new_chunks.append(("", (gap_start, gap_end)))
            gap_start = gap_end
    
    return new_chunks, complete_sentences

def number_the_chunks(chunks):
    """Number the chunks of text."""
    numbered_chunks = []
    for i, chunk in enumerate(chunks):
        start = chunk[1][0].total_seconds()
        end = chunk[1][1].total_seconds()
        numbered_chunks.append(f"Chunk {i+1} ({start}s - {end}s): '{chunk[0]}'")
    length = len(numbered_chunks)

    return '\n'.join(numbered_chunks), length

def set_time(input_string, chunks):
    """Extract the chunks from the input string and set it a time."""
    pattern = re.compile(r"Chunk (\d+):(.*?)(?=\n*Chunk \d+:|$)", re.DOTALL)
    matches = pattern.findall(input_string)
    result = []
    for i in range(len(chunks)):
        result.append((chunks[i][1][0], matches[i][1]))
    return result

def parse_video_without_srt(length_of_video):
    """Divide the video into 5-second chunks based on the length of the video."""
    chunks = []
    video_length = timedelta(seconds=length_of_video)
    chunk_start_time = timedelta(seconds=0)
    
    while chunk_start_time < video_length:
        chunk_end_time = min(chunk_start_time + timedelta(seconds=5), video_length)
        chunks.append(("", (chunk_start_time, chunk_end_time)))
        chunk_start_time = chunk_end_time

    return chunks

def number_the_chunks_no_srt(chunks):
    """Number the chunks of text for video without subtitles."""
    numbered_chunks = []
    for i, chunk in enumerate(chunks):
        start = chunk[1][0].total_seconds()
        end = chunk[1][1].total_seconds()
        numbered_chunks.append(f"Chunk {i+1} ({start}s - {end}s): ''")
    length = len(numbered_chunks)

    return '\n'.join(numbered_chunks), length

def filter_subtitle_chunks(text: str, start_time: float, end_time: float) -> str:
    # Regular expression to match each chunk
    chunk_pattern = re.compile(r"Chunk \d+ \(([\d.]+)s - ([\d.]+)s\): '([^']*)'")
    
    filtered_chunks = []
    
    # Find all matches in the text
    for match in chunk_pattern.finditer(text):
        chunk_start = float(match.group(1))
        chunk_end = float(match.group(2))
        chunk_text = match.group(3)
        
        # Check if the chunk falls within the specified time period
        if (chunk_start >= start_time and chunk_start <= end_time) or \
           (chunk_end >= start_time and chunk_end <= end_time) or \
           (chunk_start <= start_time and chunk_end >= end_time):
            filtered_chunks.append(f"Chunk {len(filtered_chunks) + 1} ({chunk_start}s - {chunk_end}s): '{chunk_text}'")
    
    # Join the filtered chunks into a single string
    return "\n".join(filtered_chunks), len(filtered_chunks)


if __name__ == "__main__":
    srt_filename = 'UjmaxCyJBc4_subtitles.srt'
    chunks, complete_sentence = parse_srt(srt_filename, 90)
    print(chunks)
    # print(number_the_chunks(chunks))
    # print(complete_sentence)
    # print(set_time(input, chunks))

# h02ti0Bl6zk   openai
# U_M_uvDChJQ   interview
# Qht28m7b13U&t=10s   chain rule