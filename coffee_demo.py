"""
Groundlight demo app to trigger a notification when the coffee machine is not rinsed after use

set GROUNDLIGHT_API_TOKEN to your API token in the environment
"""

import io
import json
import os
import sys
import time
import traceback
from typing import Optional

from groundlight import Groundlight
from imgcat import imgcat
import cv2
import requests
from gtts import gTTS

gl = Groundlight()  # API key should be in environment variable
rtsp_url = os.environ.get("RTSP_URL")
slack_url = os.environ.get("SLACK_URL")

delay_between_checks = 60  # seconds
num_checks_before_notification = 3
audio_line = "The coffee machine needs rinsing"
audio_file = audio_line.replace(" ", "_")
gTTS(audio_line).save(f"audio/{audio_file}.mp3")


if not rtsp_url:
    print("please set RTSP_URL environment variable")
    exit(-1)

if not slack_url:
    print(
        "WARNING: no slack URL configured, status messages will only be printed to console"
    )

# helper functions


def post_status(msg: str):
    """Posts a status message to slack if configured, or else just prints it"""
    print(msg)
    if slack_url:
        try:
            post_slack_message(msg)
        except Exception:
            traceback.print_exc()
            print("failed to post to slack, continuing...")


def play_sound(filename: str):
    """Plays a sound file"""
    print(f"Playing sound file {filename} for system {sys.platform}")
    if sys.platform == "darwin":
        os.system(f"afplay {filename}")
    elif sys.platform == "linux":
        os.system(f"mpg321 {filename}")
    elif sys.platform == "win32":
        os.system(f"start {filename}")
    else:
        print(f"don't know how to play sound on {sys.platform}")


def post_slack_message(msg: str):
    """Posts a message to slack"""

    slack_data = {
        "username": "CoffeeBot",
        "icon_emoji": ":coffee:",
        "channel": "#coffeestatus",
        "attachments": [
            {
                "color": "#9733EE",
                "fields": [
                    {
                        "title": "Coffee Status",
                        "value": msg,
                        "short": "false",
                    }
                ],
            }
        ],
    }
    byte_length = str(sys.getsizeof(slack_data))
    headers = {"Content-Type": "application/json", "Content-Length": byte_length}
    response = requests.post(slack_url, data=json.dumps(slack_data), headers=headers)
    if response.status_code != 200:
        raise RuntimeError(response.status_code, response.text)


def get_rtsp_image(
    rtsp_url: str, x1: int = 0, y1: int = 0, x2: int = 0, y2: int = 0
) -> Optional[io.BytesIO]:
    """Fetches an image from an RTSP stream, crops it, compresses as JPEG,
    and returns it as a BytesIO object"""
    cap = cv2.VideoCapture(rtsp_url)

    try:
        if cap.isOpened():
            ret, frame = cap.read()
            # Crop the frame
            print(f"Original image size: {frame.shape[0]}x{frame.shape[1]}")
            if x1 + x2 + y1 + y2 > 0:
                frame = frame[y1:y2, x1:x2]
                print(f"Post-crop image size: {frame.shape[0]}x{frame.shape[1]}")
            else:
                print("No crop requested")

            if ret:
                is_success, buffer = cv2.imencode(".jpg", frame)
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                imgcat(frame_rgb)
                return io.BytesIO(buffer)
            else:
                print("failed to read from stream!")
                return None
    finally:
        if cap:
            cap.release()


def map_result(iq, threshold: float) -> str:
    """Interprets the result of an image query and returns a string
    representing the answer, or "UNSURE" if the confidence is below the threshold.
    Maps old-style PASS/FAIL labels to YES/NO if needed.
    """
    if (iq.result.confidence is not None) and (iq.result.confidence < threshold):
        answer = "UNSURE"
    else:
        answer = iq.result.label

    ANSWER_MAP = {
        "PASS": "YES",
        "FAIL": "NO",
    }
    if answer in ANSWER_MAP:
        answer = ANSWER_MAP[answer]
    return answer


def confident_image_query(detector, image, threshold=0.5, timeout=10) -> Optional[str]:
    """
    query detector and wait for confidence above threshold, return None on problem
    """
    start_time = time.time()
    try:
        iq = gl.submit_image_query(detector, image, wait=timeout)
    except Exception:
        traceback.print_exc()
        time.sleep(10)  # make sure we don't get stuck in a fast loop
        return None

    elapsed = time.time() - start_time

    if iq.result.confidence is None:
        print(
            f"HUMAN CONFIDENT  after {elapsed:.2f}s {(100):.1f}%/{threshold*100}% {iq.result.label} {iq.id=}"
        )
    elif iq.result.confidence >= threshold:
        print(
            f"ML    CONFIDENT  after {elapsed:.2f}s {(iq.result.confidence*100):.1f}%/{threshold*100}% {iq.result.label} {iq.id=}"
        )
    else:
        print(
            f"  NOT CONFIDENT  after {elapsed:.2f}s {(iq.result.confidence*100):.1f}%/{threshold*100}% {iq.result.label} {iq.id=}"
        )

    return map_result(iq, threshold)


def find_or_create_detector(desired_detectors: dict) -> dict:
    """finds or creates the desired detectors and returns them in a dict,
    keyed by detector name"""
    detectors = {}

    # find the desired detectors if they exist
    available_detectors = gl.list_detectors()

    for det in available_detectors.results:
        if det.name in desired_detectors:
            detectors[det.name] = det
            print(f"found detector for : {det.name}")

    # create new detectors as necessary
    for det_name in desired_detectors.keys():
        if det_name not in detectors:
            detectors[det_name] = gl.create_detector(
                det_name, desired_detectors[det_name]
            )
            print(f"created detector for : {det_name}")

    return detectors


# set a list of desired detectors
desired_detectors = {
    "coffee_present": "are coffee grounds in the round filter area (not just residual dirt)",
}

detectors = find_or_create_detector(desired_detectors)

print(f"configured {len(detectors)} detectors : ")
for det in detectors.values():
    print(f"{det.id} : {det.name} / {det.query}")
    print(det)

count_coffee_present = 0

while True:
    try:
        img = get_rtsp_image(rtsp_url, x1=1200, x2=1800, y1=400, y2=1000)
    except Exception:
        traceback.print_exc()
        print("Failed to capture image")
        time.sleep(delay_between_checks)
        continue

    result = confident_image_query(
        detectors["coffee_present"].id,
        img,
        threshold=0.75,
        timeout=90,
    )
    if result == "YES":
        count_coffee_present += 1
        print(f"Coffee present ({count_coffee_present} times in a row)")
        if count_coffee_present >= num_checks_before_notification:
            play_sound(f"audio/{audio_file}.mp3")
            post_status(f"Coffee maker needs rinsing!")
    else:
        count_coffee_present = 0
        print("No coffee present")

    time.sleep(delay_between_checks)
