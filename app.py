import os
import cv2
import numpy as np
import sqlite3
from datetime import datetime, timedelta
import pickle
import threading
import time
import base64

from flask import Flask, render_template, Response, jsonify, request, redirect, url_for, session
from sklearn.preprocessing import LabelEncoder
from keras_facenet import FaceNet
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# =========================
# Flask App Config
# =========================
app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# =========================
# Initialize Database
# =========================
def init_db():
    conn = sqlite3.connect('attendance.db')
    c = conn.cursor()

    # Employees Table
    c.execute('''CREATE TABLE IF NOT EXISTS employees (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    department TEXT,
                    position TEXT,
                    photo_path TEXT
                )''')

    # Attendance Table
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    employee_id INTEGER,
                    timestamp DATETIME,
                    FOREIGN KEY(employee_id) REFERENCES employees(id)
                )''')

    # Users Table (Admin Login)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT
                )''')

    # Create default admin if not exists
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                  ('admin', generate_password_hash('admin123')))

    conn.commit()
    conn.close()

init_db()

# =========================
# Face Recognition Setup
# =========================
def initialize_face_recognition():
    facenet = FaceNet()
    faces_embeddings = np.load("models/faces_embeddings_done_4classes.npz")
    Y = faces_embeddings['arr_1']
    encoder = LabelEncoder()
    encoder.fit(Y)
    haarcascade = cv2.CascadeClassifier("models/haarcascade_frontalface_default.xml")
    model = pickle.load(open("models/svm_model_160x160.pkl", 'rb'))
    return facenet, encoder, haarcascade, model

facenet, encoder, haarcascade, model = initialize_face_recognition()

# =========================
# Globals
# =========================
camera_active = False
camera_thread = None
cap = None
latest_frame = None
frame_lock = threading.Lock()
last_detection = {}
COOLDOWN_TIME = timedelta(minutes=5)
CONFIDENCE_THRESHOLD = 1.0

# =========================
# Database Functions
# =========================
def get_db_connection():
    conn = sqlite3.connect('attendance.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_attendance_data(date=None):
    conn = get_db_connection()
    query = '''
        SELECT a.id, e.name, e.department, a.timestamp 
        FROM attendance a
        JOIN employees e ON a.employee_id = e.id
    '''
    params = ()
    if date:
        query += ' WHERE DATE(a.timestamp) = ?'
        params = (date,)
    query += ' ORDER BY a.timestamp DESC'
    attendance = conn.execute(query, params).fetchall()
    conn.close()
    return attendance

def get_todays_attendance_count():
    today = datetime.now().strftime('%Y-%m-%d')
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(*) FROM attendance WHERE DATE(timestamp) = ?', (today,)).fetchone()[0]
    conn.close()
    return count

def get_unique_employee_count():
    conn = get_db_connection()
    count = conn.execute('SELECT COUNT(DISTINCT employee_id) FROM attendance').fetchone()[0]
    conn.close()
    return count

def get_employee_by_name(name):
    conn = get_db_connection()
    employee = conn.execute('SELECT * FROM employees WHERE name = ?', (name,)).fetchone()
    conn.close()
    return employee

def record_attendance(employee_name):
    """Record attendance if cooldown passed."""
    employee = get_employee_by_name(employee_name)
    if not employee:
        return False
    current_time = datetime.now()
    if employee_name in last_detection and current_time - last_detection[employee_name] <= COOLDOWN_TIME:
        return False  # Skip duplicate entry within cooldown
    conn = get_db_connection()
    conn.execute('INSERT INTO attendance (employee_id, timestamp) VALUES (?, ?)',
                 (employee['id'], current_time.strftime('%Y-%m-%d %H:%M:%S')))
    conn.commit()
    conn.close()
    last_detection[employee_name] = current_time
    print(f"[INFO] Attendance recorded: {employee_name} at {current_time}")
    return True

# =========================
# Camera Processing Thread
# =========================
def camera_thread_function():
    global cap, latest_frame, camera_active

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("[ERROR] Could not open camera.")
        camera_active = False
        return

    while camera_active:
        ret, frame = cap.read()
        if not ret:
            break

        display_frame = frame.copy()
        rgb_img = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        gray_img = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = haarcascade.detectMultiScale(gray_img, 1.3, 5)

        for (x, y, w, h) in faces:
            img = rgb_img[y:y+h, x:x+w]
            img = cv2.resize(img, (160, 160))
            img = np.expand_dims(img, axis=0)
            embedding = facenet.embeddings(img)
            scores = model.decision_function(embedding)
            max_score = np.max(scores)

            if max_score > CONFIDENCE_THRESHOLD:
                predicted_label = model.predict(embedding)
                name = encoder.inverse_transform(predicted_label)[0]
                record_attendance(name)
                cv2.rectangle(display_frame, (x, y), (x+w, y+h), (0, 255, 0), 2)
                cv2.putText(display_frame, f"{name} ({max_score:.2f})", (x, y-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)

        with frame_lock:
            _, buffer = cv2.imencode('.jpg', display_frame)
            latest_frame = base64.b64encode(buffer).decode('utf-8')

        time.sleep(0.05)

    if cap:
        cap.release()
    with frame_lock:
        latest_frame = None

# =========================
# Authentication
# =========================
def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return view(**kwargs)
    return wrapped_view

# =========================
# Routes
# =========================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username, password = request.form['username'], request.form['password']
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user['password'], password):
            session['user_id'], session['username'] = user['id'], user['username']
            return redirect(url_for('dashboard'))
        return render_template('login.html', error='Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'user_id' in session else url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('index.html')

@app.route('/start_camera', methods=['POST'])
@login_required
def start_camera():
    global camera_active, camera_thread
    if not camera_active:
        camera_active = True
        camera_thread = threading.Thread(target=camera_thread_function, daemon=True)
        camera_thread.start()
        return jsonify({"status": "camera started"})
    return jsonify({"status": "camera already running"})

@app.route('/stop_camera', methods=['POST'])
@login_required
def stop_camera():
    global camera_active
    camera_active = False
    return jsonify({"status": "camera stopped"})

@app.route('/get_frame')
@login_required
def get_frame():
    with frame_lock:
        return jsonify({"frame": latest_frame if latest_frame else None})

@app.route('/attendance_data')
@login_required
def attendance_data():
    date = request.args.get('date')
    attendance = get_attendance_data(date)
    return jsonify([dict(row) for row in attendance])

@app.route('/download_attendance')
@login_required
def download_attendance():
    date = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    attendance = get_attendance_data(date)
    from io import StringIO
    import csv
    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(['ID', 'Name', 'Department', 'Timestamp'])
    for record in attendance:
        cw.writerow([record['id'], record['name'], record['department'], record['timestamp']])
    return Response(si.getvalue(), mimetype="text/csv",
                    headers={"Content-disposition": f"attachment; filename=attendance_{date}.csv"})

@app.route('/stats')
@login_required
def get_stats():
    return jsonify({
        "total_employees": get_unique_employee_count(),
        "today_attendance": get_todays_attendance_count(),
        "status": "Active" if camera_active else "Inactive"
    })

@app.route('/employees')
@login_required
def employees():
    conn = get_db_connection()
    employees = conn.execute('SELECT * FROM employees ORDER BY name').fetchall()
    conn.close()
    return render_template('employees.html', employees=employees)

# =========================
# Run App
# =========================
if __name__ == '__main__':
    app.run(debug=True, threaded=True)
