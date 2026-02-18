import numpy as np
import pickle
import os
import random
import string
import sys
from flask import Flask, request, jsonify, render_template, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import smtplib
import ssl
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'default-dev-key') 
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy()
login_manager = LoginManager()

# Global Model Variables
encoder = None
scaler = None
model = None

def init_extensions(app):
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'

def load_ml_models():
    global encoder, scaler, model
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base_dir, 'encoder.pkl'), 'rb') as f:
            encoder = pickle.load(f)
        with open(os.path.join(base_dir, 'scaler.pkl'), 'rb') as f:
            scaler = pickle.load(f)
        with open(os.path.join(base_dir, 'model.pkl'), 'rb') as f:
            model = pickle.load(f)
        print("DEBUG: ML Models loaded successfully", flush=True)
    except Exception as e:
        print(f"Error loading model files: {e}", flush=True)

# Database Configuration
base_dir = os.path.dirname(os.path.abspath(__file__))
db_relative_path = os.environ.get('DATABASE_URL', 'sqlite:///users.db')

if db_relative_path.startswith('sqlite:///'):
    db_file = db_relative_path.replace('sqlite:///', '')
    abs_db_path = os.path.abspath(os.path.join(base_dir, db_file)).replace('\\', '/')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{abs_db_path}'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_relative_path

init_extensions(app)
load_ml_models()

with app.app_context():
    print(f"DEBUG: Initializing database at {app.config['SQLALCHEMY_DATABASE_URI']}", flush=True)
    db.create_all()
    print("DEBUG: Database successfully initialized", flush=True)

# --- Models ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    is_verified = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Helpers ---
def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def send_otp_email(to_email, otp):
    sender_email = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    
    if not sender_email or not password:
        print("Email credentials not found in environment variables. OTP not sent via email.")
        return False

    msg = EmailMessage()
    msg.set_content(f"Your OTP for Energy Consumption App verification is: {otp}")
    msg['Subject'] = 'Your OTP Code'
    msg['From'] = sender_email
    msg['To'] = to_email

    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
            server.login(sender_email, password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# --- Context Processor ---
@app.context_processor
def inject_user():
    return dict(user=current_user)

# --- Routes ---

@app.route('/test')
def test():
    return "Test Route Working"

@app.route('/')
@login_required
def home():
    print("LOG: Home route accessed", flush=True)
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    print(f"LOG: Login route accessed via {request.method}", flush=True)
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash('Invalid email or password', 'error')
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    print(f"LOG: Register route accessed via {request.method}", flush=True)
    if current_user.is_authenticated:
        return redirect(url_for('home'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        if User.query.filter_by(email=email).first():
            flash('Email already exists', 'error')
            return redirect(url_for('register'))
            
        new_user = User(email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        
        # OTP Logic
        otp = generate_otp()
        session['otp'] = otp
        session['pending_user_id'] = new_user.id
        
        # Send Email
        if send_otp_email(email, otp):
            flash(f'OTP sent to {email}', 'info')
        else:
            flash(f'Failed to send OTP to {email}. Check console/logs.', 'error')
            # For debugging purposes, still print to console if email fails or not configured
            print(f"\n{'='*30}\nOTP for {email}: {otp}\n{'='*30}\n", file=sys.stderr)
        
        return redirect(url_for('verify_otp'))
        
    return render_template('register.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if 'pending_user_id' not in session:
        return redirect(url_for('register'))
        
    if request.method == 'POST':
        user_otp = request.form.get('otp')
        generated_otp = session.get('otp')
        
        if user_otp == generated_otp:
            user = User.query.get(session['pending_user_id'])
            user.is_verified = True
            db.session.commit()
            
            login_user(user)
            session.pop('otp', None)
            session.pop('pending_user_id', None)
            return redirect(url_for('home'))
        else:
            flash('Invalid OTP', 'error')
            
    return render_template('otp.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- Prediction Route (Unchanged Logic, added auth) ---
@app.route('/predict', methods=['POST'])
@login_required
def predict():
    try:
        # Load models if not loaded (or keep global)
        # For simplicity, assuming globals exist or reloading here
        # But we need to make sure imports are correct at top
        
        data = request.json
        
        building_type = float(data['building_type'])
        square_footage = float(data['square_footage'])
        number_of_occupants = float(data['number_of_occupants'])
        appliances_used = float(data['appliances_used'])
        average_temperature = float(data['average_temperature'])
        day_of_week = data['day_of_week']
        
        day_encoded = encoder.transform([day_of_week])[0]
        
        features = np.array([[
            building_type,
            square_footage,
            number_of_occupants,
            appliances_used,
            average_temperature,
            day_encoded
        ]])
        
        scaled_features = scaler.transform(features)
        prediction = model.predict(scaled_features)
        
        return jsonify({
            'prediction': float(prediction[0]),
            'status': 'success'
        })

    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)
