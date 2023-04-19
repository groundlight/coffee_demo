"""
Groundlight demo app to trigger a notification when the coffee machine is not rinsed after use

set GROUNDLIGHT_API_TOKEN to your API token in the environment
"""

import io
import json
import os
import sys
import time

from groundlight import Groundlight
from imgcat import imgcat
import cv2
import requests

gl = (
    Groundlight()
)  # assumes API key is set by environment variable GROUNDLIGHT_API_TOKEN
rtsp_url = os.environ.get("RTSP_URL")
slack_url = os.environ.get("SLACK_URL")

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
        post_slack_message(msg)


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
        raise Exception(response.status_code, response.text)


def get_rtsp_image(rtsp_url:str, x1:int=0, y1:int=0, x2:int=0, y2:int=0):
    """Fetches an image from an RTSP stream, crops it, compresses as JPEG,
    and returns it as a BytesIO object"""
    cap = cv2.VideoCapture(rtsp_url)

    if cap.isOpened():
        ret, frame = cap.read()
        if x1 + x2 + y1 + y2 > 0:
            frame = frame[y1:y2, x1:x2]

        # Swap the color channels to BGR
        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        if ret:
            is_success, buffer = cv2.imencode(".jpg", frame)
            imgcat(frame)
            return io.BytesIO(buffer)
        else:
            print("failed to read from stream!")
            return None
    cap.release()


def confident_image_query(detector, image, threshold=0.5, timeout=10):
    """
    query detector and wait for confidence above threshold, return None if timeout
    """
    start_time = time.time()
    iq = gl.submit_image_query(detector, image, wait=60)

    if iq.result.confidence is None:
        print(
            f"HUMAN CONFIDENT  after {(time.time()-start_time):.2f}s {(100):.1f}%/{threshold*100}% {iq.result.label} {iq.id=}"
        )
    elif iq.result.confidence >= threshold:
        print(
            f"ML    CONFIDENT  after {(time.time()-start_time):.2f}s {(iq.result.confidence*100):.1f}%/{threshold*100}% {iq.result.label} {iq.id=}"
        )
    else:
        print(
            f"  NOT CONFIDENT  after {(time.time()-start_time):.2f}s {(iq.result.confidence*100):.1f}%/{threshold*100}% {iq.result.label} {iq.id=}"
        )

    if (iq.result.confidence is None) or (iq.result.confidence >= threshold):
        return iq.result.label
    else:
        return None


def find_or_create_detector(desired_detectors):
    detectors = {}

    # find the desired detectors if they exist
    try:
        available_detectors = gl.list_detectors()
    except ApiError as e:
        print(f"Error: {e}")
        exit(-1)

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
    "is_rinsing": 'does the display show "Rinsing"',
    "is_brewing": 'does the display show "Brewing"',
}

detectors = find_or_create_detector(desired_detectors)

print(f"configured {len(detectors)} detectors : ")
for det in detectors.values():
    print(f"{det.id} : {det.name} / {det.query}")
    print(det)

# wait for some reasonable number of labels before the detector is confident

state = "idle"
print(f"assuming machine is idle to start!")

while True:
    if state == "idle":
        post_status(f"waiting for coffee grounds to be added")
        while True:
            query_time = time.time()
            result = confident_image_query(
                detectors["coffee_present"].id,
                get_rtsp_image(rtsp_url),
                threshold=0.75,
                timeout=10,
            )
            if (result is not None) and (result == "PASS"):
                state = "grounds_added"
                possible_brew_start = time.time()
                break
            required_delay = query_time + 10 - time.time()
            time.sleep(max(required_delay, 0))

    if state == "grounds_added":
        post_status(f"grounds added, waiting for brew start")
        while True:
            result = confident_image_query(
                detectors["is_brewing"].id,
                get_rtsp_image(rtsp_url, x1=920, y1=1200, x2=1790, y2=1600),
                threshold=0.8,
                timeout=10,
            )
            if (result is not None) and (result == "PASS"):
                brew_start = time.time()
                state = "brewing"
                break
            if (time.time() - possible_brew_start) > 120:
                post_status(
                    f"no brew cycle detected, maybe someone left grounds in the machine?"
                )
                state = "error"
                break

    if state == "brewing":
        print(f"now brewing. waiting for grounds to clear")
        while True:
            result = confident_image_query(
                detectors["coffee_present"].id,
                get_rtsp_image(rtsp_url),
                threshold=0.75,
                timeout=10,
            )
            if (result is not None) and (result == "FAIL"):
                state = "waiting_for_rinse"
                break
            if (time.time() - brew_start) > 200:
                post_status(
                    f"looks like we still have grounds, stop watching this and rinse the machine!"
                )
                state = "error"
                break

    if state == "waiting_for_rinse":
        print(f"finished brewing. waiting for rinse")
        while True:
            result = confident_image_query(
                detectors["is_rinsing"].id,
                get_rtsp_image(rtsp_url, x1=920, y1=1200, x2=1790, y2=1600),
                threshold=0.8,
                timeout=10,
            )
            if (result is not None) and (result == "PASS"):
                post_status(f"great job. someone remembered to rinse the machine!")
                state = "idle"
                break
            if (time.time() - brew_start) > 200:
                post_status(
                    f"almost there!  just rinse the machine and we can start again!"
                )
                state = "error"
                break

    if state == "error":
        post_status(
            "error state, waiting for a little while to see if things clear up"
        )
        while True:
            result = confident_image_query(
                detectors["coffee_present"].id,
                get_rtsp_image(rtsp_url),
                threshold=0.75,
                timeout=10,
            )
            if (result is not None) and (result == "FAIL"):
                state = "idle"
                break
