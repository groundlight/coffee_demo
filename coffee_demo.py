
'''

Groundlight demo app to trigger a notification when the coffee machine is not rinsed after use

set GROUNDLIGHT_API_TOKEN to your API token in the environment

'''



import cv2
import io
import time
from imgcat import imgcat
from groundlight import Groundlight

gl = Groundlight() # assumes API key is set by environment variable GROUNDLIGHT_API_TOKEN
rtsp_url = f'rtsp://admin:admin@10.44.3.34/cam/realmonitor?channel=1&subtype=0'

#helper functions

def post_coffee_status(s):
    print(s)

def get_rtsp_image(rtsp_url, x1=0, y1=0, x2=0, y2=0):
    
    #print(f'pulling frame from {rtsp_url}')
        
    cap = cv2.VideoCapture(rtsp_url)

    if cap.isOpened():
        ret, frame = cap.read()
        if x1+x2+y1+y2 > 0:
            frame = frame[y1:y2, x1:x2]
        if ret:
            is_success, buffer = cv2.imencode(".jpg", frame)
            return io.BytesIO(buffer)
        else:
            print('failed to read from stream!')
            return None
    cap.release()

def confident_image_query(detector, image, threshold=0.5, timeout=10):
    '''
    query detector and wait for confidence above threshold, return None if timeout
    '''
    iq = gl.submit_image_query(detector, image)
    elapsed = 0
    retry_interval = 0.5
    #print(f'{iq=}')
    while iq.result.confidence < threshold:
        time.sleep(retry_interval)
        elapsed += retry_interval
        iq = gl.get_image_query(id=iq.id)
        #print(f'{iq.result=}')
        if iq.result.confidence is None:
            break
    if (iq.result.confidence is None) or (iq.result.confidence >= threshold):
        return iq.result.label
    else:
        return None

# set a list of desired detectors
desired_detectors = { 'coffee_present' : 'are coffee grounds in the round filter area (not just residual dirt)', \
                      'is_rinsing' : 'does the display show "Rinsing"', \
                      'is_brewing' : 'does the display show "Brewing"' \
                        }
detectors = {}

# find the desired detectors if they exist
try:
    available_detectors = gl.list_detectors()
except ApiError as e:
    print(f'Error: {e}')
    exit(-1)

for det in available_detectors.results:
    if det.name in desired_detectors:
        detectors[det.name] = det
        print(f'found detector for : {det.name}')

# create new detectors as necessary
for det_name in desired_detectors.keys():
    if det_name not in detectors:
        detectors[det_name] = gl.create_detector(det_name, desired_detectors[det_name])
        print(f'created detector for : {det_name}')

print(f'configured {len(detectors)} detectors : ')
for det in detectors.values():
    print(f'{det.id} : {det.name} / {det.query}')
    print(det)

# wait for some reasonable number of labels before the detector is confident

state = 'idle'
print(f'assuming machine is idle to start!')

while True:

    if state == 'idle':
        post_coffee_status(f'waiting for coffee grounds to be added')
        while True:
            result = confident_image_query(detectors['coffee_present'].id, get_rtsp_image(rtsp_url), threshold=0.8, timeout=10)
            if (result is not None) and (result == 'PASS'):
                break
        state = 'grounds_added'
        possible_brew_start = time.time()

    if state == 'grounds_added':
        post_coffee_status(f'grounds added, waiting for brew start')
        while True:
            result = confident_image_query(detectors['is_brewing'].id, get_rtsp_image(rtsp_url, x1=920, y1=1200, x2=1790, y2=1600), threshold=0.8, timeout=10)
            if (result is not None) and (result == 'PASS'):
                brew_start = time.time()
                state = 'brewing'
                break
            if (time.time() - possible_brew_start) > 120:
                post_coffee_status(f'no brew cycle detected, maybe someone left grounds in the machine?')
                state = 'error'
                break

    if state == 'brewing':
        print(f'waiting for grounds to clear')
        while True:
            result = confident_image_query(detectors['coffee_present'].id, get_rtsp_image(rtsp_url), threshold=0.8, timeout=10)
            if (result is not None) and (result == 'FAIL'):
                state = 'waiting_for_rinse'
                break
            if (time.time() - brew_start) > 200:
                post_coffee_status(f'looks like we still have grounds, stop watching this and rinse the machine!')
                state = 'error'
                break

    if state == 'waiting_for_rinse':
        print(f'waiting for rinse')
        while True:
            result = confident_image_query(detectors['is_rinsing'].id, get_rtsp_image(rtsp_url, x1=920, y1=1200, x2=1790, y2=1600), threshold=0.8, timeout=10)
            if (result is not None) and (result == 'PASS'):
                print(f'great job. you remembered to rinse the machine!')
                state = 'idle'
                break
            if (time.time() - brew_start) > 200:
                post_coffee_status(f'almost there!  just rinse the machine and we can start again!')
                state = 'error'
                break
    
    if state == 'error':
        post_coffee_status(f'error state, waiting for a little while to see if things clear up')
        while True:
            result = confident_image_query(detectors['coffee_present'].id, get_rtsp_image(rtsp_url), threshold=0.8, timeout=10)
            if (result is not None) and (result == 'FAIL'):
                state = 'idle'
                break

