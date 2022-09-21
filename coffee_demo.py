
'''

Groundlight demo app to trigger a notification when the coffee machine is not rinsed after use

set GROUNDLIGHT_API_TOKEN to your API token in the environment

'''

def confident_image_query(detector, image, threshold=0.5, timeout=10):
    '''
    query detector and wait for confidence above threshold, return None if timeout
    '''
    iq = gl.submit_image_query(detector, image)
    elapsed = 0
    retry_interval = 0.5
    print(f'{iq=}')
    while iq.result.confidence < threshold:
        time.sleep(retry_interval)
        elapsed += retry_interval
        iq = gl.get_image_query(id=iq.id)
        print(f'{iq.result=}')
        if iq.result.confidence is None:
            break
    if (iq.result.confidence is None) or (iq.result.confidence >= threshold):
        return iq.result.label
    else:
        return None

import cv2
import io
import time
from imgcat import imgcat
from groundlight import Groundlight


gl = Groundlight()

# set a list of desired detectors
desired_detectors = { 'filter_clear' : 'is the round filter area clear of coffee grounds?', \
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
        detectors[det_name] = gl.create_detector(det_name, desired_detectors[det])
        print(f'created detector for : {det_name}')

print(f'configured {len(detectors)} detectors : ')
for det in detectors.values():
    print(f'{det.id} : {det.name} / {det.query}')


# test it
rtsp_url = f'rtsp://admin:admin@10.44.3.34/cam/realmonitor?channel=1&subtype=0'
print(f'pulling frame from {rtsp_url}')
    
cap = cv2.VideoCapture(rtsp_url)

if cap.isOpened():
    ret, frame = cap.read()
    if ret:
        imgcat(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    else:
        print('failed to read from stream!')
cap.release()

print(f'triggering query for filter_clear')
is_success, buffer = cv2.imencode(".jpg", frame)
jpg = io.BytesIO(buffer)
result = confident_image_query(detectors['filter_clear'].id, jpg, threshold=0.99, timeout=10)

print(f'received {result} for filter_clear')




