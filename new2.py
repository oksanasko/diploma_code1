import time
import cv2
import os
import ctypes
from ultralytics import YOLO
from flask import Flask, request, render_template_string
from flask_socketio import SocketIO
import firebase_admin
from firebase_admin import credentials, messaging
from threading import Thread


cred = credentials.Certificate("C:\\Users\\user\\Desktop\\унік\\диплом\\newfolder\\key\\notification-206e8-firebase-adminsdk-fbsvc-11950fc866.json")
firebase_admin.initialize_app(cred)
device_token = "cSE7kv2gRaGBOODluWi4R2:APA91bH405wRsWgbzo-IpYqCOy6YhTdhW9OfOqcJLqqfYjuOOhR27M1N1JuQKc6dnpG6HBXvtw7WoWlagn7q3_K6DAqP-sB4BEAfJO1ss7bDdX7NT5avbQs"

# Global variable to keep the thread reference
global detection_thread
detection_thread = None

def sendPushSingleDevice(title, msg, registration_token, dataObject=None):
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=msg
        ),
        data=dataObject,
        token=registration_token,
    )
    try:
        response = messaging.send(message)
        print("Successfully sent message:", response)
    except Exception as e:
        print(f"Error sending message: {e}")


#sendPushSingleDevice("Single Hello", "Message for one device!", device_token)

app = Flask(__name__)
#socketio = SocketIO(app)
#socketio = SocketIO(app, cors_allowed_origins="*")  # Add CORS support
# 
socketio = SocketIO(app, 
                   cors_allowed_origins="*",
                   async_mode='threading',
                   logger=True,
                   engineio_logger=True)

model = YOLO('new\\best.pt')

# Configuration
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# HTML template for file upload
UPLOAD_HTML = """
<!doctype html>
<html>
<head><title>Video Upload</title>
<style>
        body {
            font-family: Arial, sans-serif;
            text-align: center;
            margin-top: 50px;
            }
        #button {
            display: inline-block;
            padding: 15px 30px;
            margin: 20px;
            font-size: 20px;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
            color: white;
            background-color: #4CAF50;
            border: none;
            border-radius: 5px;
        }
        #button:hover {background-color: #45a049;}
    </style>
</head>
<body>
    <h1>Upload Video for Object Detection</h1>
    <form method="post" enctype="multipart/form-data">
        <input id="button" type="file" name="video" accept="video/*" required >
        <button id="button" type="submit"> Process Video </button>
    </form>
</body>
</html>
"""

LIVE_HTML = """
<!doctype html>
<html>
<head>
  <title>Live Detection</title>
  <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
  <style>
    body {
      font-family: Arial, sans-serif;
      text-align: center;
      margin-top: 50px;
    }
    #status {
      font-size: 24px;
      padding: 20px;
      background-color: #f0f0f0;
      border-radius: 5px;
      display: inline-block;
    }
    #move_camera {
      font-size: 45px;
      padding: 20px;
      background-color: #f0f0f0;
      border-radius: 5px;
      display: inline-block;
    }
  </style>
</head>
<body>
  <h1>Live Detection</h1>
  <div id="status">Connecting to detection server...</div>
  <br /> 
  <div id="text"> Where to move the camera to track the dog </div>
  <div id="move_camera"> ✦ </div>
  
  <script>
  
    // Explicitly connect to the server
    const socket = io({
        transports: ['websocket'], // Force WebSocket transport
        reconnectionAttempts: 5,   // Limit reconnection attempts
        reconnectionDelay: 1000,   // Delay between attempts
        timeout: 20000            // Connection timeout
    });
    
    // Connection status handlers
    socket.on('connect', () => {
        console.log('Connected with ID:', socket.id);
        document.getElementById('status').textContent = 'Connected!';
    });
    
    socket.on('disconnect', (reason) => {
        console.log('Disconnected:', reason);
        if (reason === 'io server disconnect') {
        // Server intentionally disconnected, try to reconnect
        socket.connect();
        }
        document.getElementById('status').textContent = `Disconnected: ${reason}`;
    });

    socket.on('connect_error', (error) => {
        console.error('Connection Error:', error);
        document.getElementById('status').textContent = `Connection Error: ${error.message}`;
    });
    
    // Handle detection messages
    socket.on('status', data => {
      console.log('Received status:', data);
      const statusElement = document.getElementById('status');
      statusElement.textContent = ` Distance status: ${data.message}  |||  Position status: ${data.message2} - ${data.message3}`;
      
      // Add some visual feedback based on status
      if (data.message.toLowerCase().includes('close')) {
        statusElement.style.backgroundColor = '#ffcccc';
      } else if (data.message.toLowerCase().includes('far')) {
        statusElement.style.backgroundColor = '#ccffcc';
      } else {
        statusElement.style.backgroundColor = '#f0f0f0';
      }

      const moveElement = document.getElementById('move_camera');

      // Convert to lowercase once for efficiency
      const vertDir = data.message3?.toLowerCase() || '';
      const horizDir = data.message2?.toLowerCase() || '';

      // Determine arrow (corrected directions)
      if (vertDir.includes('top') && horizDir.includes('right')) {
          moveElement.textContent = ' ↗ ';  // Correct NE arrow
      } else if (vertDir.includes('top') && horizDir.includes('left')) {
          moveElement.textContent = ' ↖ ';  // Correct NW arrow
      } else if (vertDir.includes('bottom') && horizDir.includes('right')) {
          moveElement.textContent = ' ↘ ';  // Correct SE arrow
      } else if (vertDir.includes('bottom') && horizDir.includes('left')) {
          moveElement.textContent = ' ↙ ';  // Correct SW arrow
      } else if (vertDir.includes('top')) {
          moveElement.textContent = '  ↑ ';  // Up only
      } else if (vertDir.includes('bottom')) {
          moveElement.textContent = ' ↓ ';  // Down only
      } else if (horizDir.includes('right')) {
         moveElement.textContent = ' → ';  // Right only
      } else if (horizDir.includes('left')) {
          moveElement.textContent = ' ← ';  // Left only
      } else {
          moveElement.textContent = ' ✦ ';  // Default/no movement
      }
    });
  </script>
</body>
</html>
"""

@app.route('/')
def home():
    return """
    <!doctype html>
    <html>
    <head><title>Object Detection</title>
    <style>
    body {
            font-family: Arial, sans-serif;
            text-align: center;
            margin-top: 50px;
        }
        .button {
            display: inline-block;
            padding: 15px 30px;
            margin: 20px;
            font-size: 20px;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
            color: white;
            background-color: #4CAF50;
            border: none;
            border-radius: 5px;
        }
        .button:hover {background-color: #45a049;}
    </style>
    </head>
    <body style="text-align: center;">
        <h1>Object Detection System</h1>
        <a href="/video" class="button">Process Video File</a>
        <a href="/camera" class="button">Live Camera Detection</a>
    </body>
    </html>
    """

@app.route('/socketio-health')
def socketio_health():
    return {'status': 'ok', 'clients': len(socketio.server.manager.get_participants('/', None))}

@app.route("/hello")
def hello():
    sendPushSingleDevice("Single Hello", "Message for one device!", device_token)
    return "hello"

global detection_running 
detection_running = False  # To prevent multiple threads from starting

@app.route("/camera")
def camera_page():
    global detection_thread, detection_running
    if not detection_running:
        detection_running = True
        detection_thread = Thread(target=model_camera)
        detection_thread.daemon = True  # the thread will exit when the main process does
        try:
            detection_thread.start()
        except Exception as e:
            print(f"Error starting thread: {e}")
            detection_running = False
            return "Error starting detection", 500
    
    return render_template_string(LIVE_HTML)

def model_camera():

    TARGET_CLASS = "sad"
    DETECTION_THRESHOLD = 5
    NOTIFICATION_DELAY = 60  # minute

    CLOSE_HEIGHT_THRESHOLD = 0.5   # 50% of frame height
    TOO_CLOSE_THRESHOLD = 0.9      # 90%
    FAR_HEIGHT_THRESHOLD = 0.3     # 30%

    notification_sent = False
    last_notification_time = 0
    detection_count = 0

    cap = cv2.VideoCapture(0)
    
    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            results = model.predict(frame, conf=0.45)

            # frame dimensions  (after first frame read)
            frame_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            distance_status = "No objects detected"
            
            if results and results[0].boxes:
                for box in results[0].boxes:
                #  box height
                    x1, y1, x2, y2 = map(int, box.xyxy[0]) # x1 left and x2 right || y1, y2 top and bottom
                    box_height = y2 - y1
                    relative_height = box_height / frame_height

                    left_zone = frame_width // 3
                    right_zone = 2 * (frame_width // 3)
                    top_zone = frame_height // 3
                    bottom_zone = 2 * (frame_height // 3)

                    #box_center_x = (x1 + x2) // 2

                    if x2 < left_zone: # if right side in the left
                        position = "left"
                        print(f" position = left")
                    elif x1 > right_zone: # if left side in the right
                        position = "right"
                        print(f"position = right")
                    else:
                        position = "centre"
                        print(f"position = centre")  

                    if y2 < top_zone: # if bottom side in the top
                        position2 = "top"
                        print(f" position2 = top")
                    elif y1 > bottom_zone: # if top side in the bottom
                        position2 = "bottom"
                        print(f"position2 = bottom")
                    else:
                        position2 = "centre"
                        print(f"position2 = centre")  

                    if relative_height > TOO_CLOSE_THRESHOLD:
                        print(f" TOO CLOSE! Might go out of frame.")
                        distance_status = "too Close"
                    elif relative_height > CLOSE_HEIGHT_THRESHOLD:
                        print(f" is CLOSE (relative height: {relative_height:.2%})")
                        distance_status = "Close"
                    elif relative_height <= FAR_HEIGHT_THRESHOLD:
                        print(f"is FAR (relative height: {relative_height:.2%})")
                        distance_status = "Far"
                    else:
                        print(f"is at MEDIUM distance (relative height: {relative_height:.2%})")
                        distance_status = "Normal"
                    # This sends it to the browser
                    # Emit9ng the status through SocketIO
                    socketio.emit('status', {
                        'message': distance_status,
                        'message2': position,
                        'message3': position2,
                        'timestamp': time.time()
                    }, namespace='/')
            
            # Checking for the target class in the detected objects
            detected = False
            if results and results[0].boxes:
                for box in results[0].boxes:
                    class_id = model.names[int(box.cls[0])]
                    if class_id == TARGET_CLASS:
                        detected = True
                        break 
            
            current_time = time.time()

            if detected and not notification_sent:
                detection_count += 1
                print(f"{TARGET_CLASS} detected {detection_count} times.")
                if detection_count >= DETECTION_THRESHOLD:
                    sendPushSingleDevice(
                        f"Detection Alert!",
                        f"A {TARGET_CLASS} dog has been detected!",
                        device_token
                    )
                    notification_sent = True
                    last_notification_time = current_time
                    detection_count = 0 # Reseting the detection count after sending an image notification

            if notification_sent and (current_time - last_notification_time >= NOTIFICATION_DELAY):
                notification_sent = False
                print(f"Notification delay over. Ready to send again on {TARGET_CLASS} detection.")

            # Visualizing results
            annotated_frame = results[0].plot()
            cv2.imshow('Live Camera Detection', annotated_frame)

            # Bring the window to the front (Windows specific)             TURN OFF FOR PRT SC or it wont let you
            if os.name == 'nt':  # Check if the OS is Windows
                hwnd = ctypes.windll.user32.FindWindowW(None, 'Live Camera Detection')
                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            if cv2.getWindowProperty('Live Camera Detection', cv2.WND_PROP_VISIBLE) < 1:
                break

    finally:
        global detection_running 
        detection_running = False 
        cap.release()
        cv2.destroyAllWindows()
    
    #return  render_template_string(Live_HTML)



@app.route('/video', methods=['GET', 'POST'])
def video_processor():
    if request.method == 'GET':
        return render_template_string(UPLOAD_HTML)
    
    if 'video' not in request.files:
        return "No file part", 400
    
    file = request.files['video']
    if file.filename == '':
        return "No selected file", 400
    
    video_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(video_path)

    screen_width = 1132
    screen_height = 818

    # frame by frame processing
    cap = cv2.VideoCapture(video_path)

    detections = []

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # predict for simple detection (no tracking between frames)
            results = model.predict(frame, conf=0.3)
            current_time = round(cap.get(cv2.CAP_PROP_POS_MSEC) / 1000, 2)

            for box in results[0].boxes:
                class_name = model.names[int(box.cls[0])]
                detections.append((current_time, class_name))
          

            annotated_frame = results[0].plot()
            # Calculating resize ratio
            height, width = annotated_frame.shape[:2]
            scale = min(0.9 * screen_width / width, 0.9 * screen_height / height, 1.0)
            
            # Resizing if needed, cos way to big
            if scale < 1.0:
                new_width = int(width * scale)
                new_height = int(height * scale)
                annotated_frame = cv2.resize(annotated_frame, (new_width, new_height))

            cv2.imshow(f'Detection: {file.filename}', annotated_frame)
            cv2.namedWindow(f'Detection: {file.filename}', cv2.WINDOW_NORMAL)

            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            if cv2.getWindowProperty(f'Detection: {file.filename}', cv2.WND_PROP_VISIBLE) < 1:
                break

    finally:
        cap.release()
        cv2.destroyAllWindows()
        os.remove(video_path)  # Cleaning up uploaded file

    # 
    # results = model.predict(source=video_path, show=True, conf=0.3)
    # cv2.destroyAllWindows()  # Ensure windows are closed

    html = f"""
    <h2>Detection Summary</h2>
    <div style="font-size: 20px;"> Processed: {file.filename} </div> 
    <br/> 
    <a style="font-size: 20px;" href="/" > back to the home page </a>
    <ol style="font-family: monospace;">
    {   "".join([
        f'<li><span style="display: inline-block; width: 80px;">{time}s</span>{cls}</li>'
        for time, cls in detections
    ])}
    </ol>
    """

    # html = f"""
    # <h2>Detection Summary</h2>
    # <div style="font-size: 20px;"> Processed: {file.filename} </div> 
    # <br/> 
    # <a style="font-size: 20px;" href="/" > back to the home page </a>
    # <ol>
    #  {"".join(f"<li>{time}s: {cls}</li>" for time, cls in detections)}
    # </ol>
    # """
    
    return html

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)


