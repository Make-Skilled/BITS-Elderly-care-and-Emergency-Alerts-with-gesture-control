from flask import Flask, request, jsonify, render_template, redirect, session, url_for, flash, send_file, make_response
import sqlite3
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import csv
import io
import os
import requests
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from io import BytesIO
import time

THINGSPEAK_CHANNEL_ID = "2571433"
THINGSPEAK_READ_API_URL = f"https://api.thingspeak.com/channels/{THINGSPEAK_CHANNEL_ID}/feeds.json"

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

# Initialize the database
conn = sqlite3.connect('health_data.db', check_same_thread=False)
cursor = conn.cursor()

# Create tables
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT,
                    name TEXT,
                    age INTEGER,
                    gender TEXT,
                    contact TEXT
                )''')

cursor.execute('''CREATE TABLE IF NOT EXISTS health_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    temperature REAL,
                    heart_rate INTEGER,
                    spo2 INTEGER,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )''')

cursor.execute('''CREATE TABLE IF NOT EXISTS recommendations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    recommendation TEXT,
                    severity TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )''')
conn.commit()

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

class User(UserMixin):
    def __init__(self, id, username, name=None, age=None, gender=None, contact=None):
        self.id = id
        self.username = username
        self.name = name
        self.age = age
        self.gender = gender
        self.contact = contact

@login_manager.user_loader
def load_user(user_id):
    cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
    user = cursor.fetchone()
    if user:
        return User(user[0], user[1], user[3], user[4], user[5], user[6])
    return None

def store_health_data(user_id, data):
    cursor.execute('''INSERT INTO health_data (user_id, temperature, heart_rate, spo2)
                     VALUES (?, ?, ?, ?)''',
                  (user_id, data['temperature'], data['heart_rate'], data['spo2']))
    conn.commit()
    analyze_and_store_recommendations(user_id, data)

def analyze_and_store_recommendations(user_id, data):
    recommendations = []
    severity = "normal"

    # Temperature analysis
    if data['temperature'] > 37.8:
        recommendations.append("High temperature detected. Please rest and monitor. If persistent, consult a healthcare provider.")
        severity = "high"
    elif data['temperature'] < 35.0:
        recommendations.append("Low temperature detected. Keep warm and monitor.")
        severity = "high"

    # Heart rate analysis
    if data['heart_rate'] > 100:
        recommendations.append("Elevated heart rate. Take rest and practice deep breathing.")
        severity = "medium"
    elif data['heart_rate'] < 60:
        recommendations.append("Low heart rate. If you feel dizzy, consult a healthcare provider.")
        severity = "medium"

    # SpO2 analysis
    if data['spo2'] < 95:
        recommendations.append("Low oxygen saturation. Practice deep breathing exercises. If below 90%, seek medical attention.")
        severity = "high"

    # Store recommendations
    for rec in recommendations:
        cursor.execute('''INSERT INTO recommendations (user_id, recommendation, severity)
                         VALUES (?, ?, ?)''', (user_id, rec, severity))
    conn.commit()

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        name = request.form.get('name')
        age = request.form.get('age')
        gender = request.form.get('gender')
        contact = request.form.get('contact')
        
        # Changed from scrypt to sha256
        hashed_password = generate_password_hash(password, method='sha256')
        try:
            cursor.execute('''INSERT INTO users (username, password, name, age, gender, contact)
                            VALUES (?, ?, ?, ?, ?, ?)''',
                         (username, hashed_password, name, age, gender, contact))
            conn.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists!', 'error')
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        cursor.execute('SELECT * FROM users WHERE username = ?', (username,))
        user = cursor.fetchone()
        if user and check_password_hash(user[2], password):
            user_obj = User(user[0], user[1], user[3], user[4], user[5], user[6])
            login_user(user_obj)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password!', 'error')
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Fetch ThingSpeak data
    sensor_data = fetch_thingspeak_data()
    
    # Get recommendations based on ThingSpeak data
    thingspeak_recommendations = analyze_thingspeak_data(sensor_data)
    
    # Fetch recent health data from database
    cursor.execute('''SELECT * FROM health_data 
                     WHERE user_id = ? 
                     ORDER BY timestamp DESC LIMIT 10''', (current_user.id,))
    health_data = cursor.fetchall()
    
    # Fetch recent recommendations from database
    cursor.execute('''SELECT * FROM recommendations 
                     WHERE user_id = ? 
                     ORDER BY timestamp DESC LIMIT 5''', (current_user.id,))
    db_recommendations = cursor.fetchall()
    
    # Combine both types of recommendations
    all_recommendations = thingspeak_recommendations + [
        {
            'message': rec[2],
            'severity': rec[3],
            'type': 'health',
            'timestamp': rec[4]
        } for rec in db_recommendations
    ]
    
    return render_template('dashboard.html', 
                         user=current_user,
                         health_data=health_data,
                         recommendations=all_recommendations,
                         sensor_data=sensor_data)

@app.route('/profile')
@login_required
def profile():
    return render_template('profile.html', user=current_user)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
def home():
    return render_template('landing.html')

@app.route('/api/health-data', methods=['POST'])
def receive_health_data():
    try:
        data = request.get_json()
        print(data)
        
        if not data:
            return jsonify({"error": "No data received"}), 400
            
        # Validate required fields
        required_fields = ['temperature', 'heart_rate', 'spo2']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing {field} in data"}), 400
        
        # Validate data values
        try:
            temp = float(data['temperature'])
            hr = int(data['heart_rate'])
            spo2 = int(data['spo2'])
            
            # Check for reasonable ranges
            if not (20 <= temp <= 45):  # Temperature in Celsius
                return jsonify({"error": "Temperature out of valid range"}), 400
            if not (0 <= hr <= 220):    # Heart rate in bpm
                return jsonify({"error": "Heart rate out of valid range"}), 400
            if not (0 <= spo2 <= 100):  # SpO2 in percentage
                return jsonify({"error": "SpO2 out of valid range"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid data format"}), 400
        
        # For Arduino data, use a default user if not authenticated
        if current_user.is_authenticated:
            user_id = current_user.id
        else:
            # Get the first user from the database as default
            cursor.execute('SELECT id FROM users LIMIT 1')
            result = cursor.fetchone()
            if result:
                user_id = result[0]
            else:
                return jsonify({"error": "No users in database"}), 500
        
        # Store the health data
        store_health_data(user_id, data)
        
        return jsonify({
            "message": "Data received successfully",
            "data": {
                "temperature": temp,
                "heart_rate": hr,
                "spo2": spo2,
                "user_id": user_id
            }
        }), 200
        
    except Exception as e:
        print(f"Error processing data: {str(e)}")
        return jsonify({"error": "Error processing data"}), 500

@app.route('/download-data')
@login_required
def download_data():
    try:
        # Create a string buffer to write CSV data
        si = io.StringIO()
        cw = csv.writer(si)
        
        # Write headers
        cw.writerow(['Date', 'Time', 'Temperature (°C)', 'Heart Rate (BPM)', 'SpO2 (%)', 'Recommendations'])
        
        # Fetch user's health data with recommendations
        cursor.execute('''
            SELECT hd.timestamp, hd.temperature, hd.heart_rate, hd.spo2, 
                   GROUP_CONCAT(r.recommendation) as recommendations
            FROM health_data hd
            LEFT JOIN recommendations r ON hd.user_id = r.user_id 
                AND date(hd.timestamp) = date(r.timestamp)
            WHERE hd.user_id = ?
            GROUP BY hd.id
            ORDER BY hd.timestamp DESC
        ''', (current_user.id,))
        
        data = cursor.fetchall()
        
        # Write data rows
        for row in data:
            timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
            date = timestamp.strftime('%Y-%m-%d')
            time = timestamp.strftime('%H:%M:%S')
            recommendations = row[4] if row[4] else 'No recommendations'
            
            cw.writerow([
                date,
                time,
                f"{row[1]:.1f}",  # Temperature with 1 decimal place
                row[2],           # Heart rate
                row[3],           # SpO2
                recommendations
            ])
        
        # Create the response
        output = si.getvalue()
        si.close()
        
        # Generate filename with timestamp
        filename = f"health_data_{current_user.username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Create response with CSV data
        response = send_file(
            io.BytesIO(output.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
        return response
        
    except Exception as e:
        print(f"Error generating CSV: {str(e)}")
        flash('Error generating CSV file', 'error')
        return redirect(url_for('dashboard'))

@app.route('/download-report/<start_date>/<end_date>')
@login_required
def download_report(start_date, end_date):
    try:
        # Create a string buffer to write CSV data
        si = io.StringIO()
        cw = csv.writer(si)
        
        # Write headers
        cw.writerow(['Report Period', f'From {start_date} to {end_date}'])
        cw.writerow([])  # Empty row for spacing
        cw.writerow(['User Information'])
        cw.writerow(['Name', current_user.name])
        cw.writerow(['Age', current_user.age])
        cw.writerow(['Gender', current_user.gender])
        cw.writerow([])  # Empty row for spacing
        
        # Write health data headers
        cw.writerow(['Date', 'Time', 'Temperature (°C)', 'Heart Rate (BPM)', 'SpO2 (%)', 'Recommendations'])
        
        # Fetch data for the specified date range
        cursor.execute('''
            SELECT hd.timestamp, hd.temperature, hd.heart_rate, hd.spo2, 
                   GROUP_CONCAT(r.recommendation) as recommendations
            FROM health_data hd
            LEFT JOIN recommendations r ON hd.user_id = r.user_id 
                AND date(hd.timestamp) = date(r.timestamp)
            WHERE hd.user_id = ?
                AND date(hd.timestamp) BETWEEN ? AND ?
            GROUP BY hd.id
            ORDER BY hd.timestamp DESC
        ''', (current_user.id, start_date, end_date))
        
        data = cursor.fetchall()
        
        # Calculate statistics
        temps = [row[1] for row in data]
        heart_rates = [row[2] for row in data]
        spo2s = [row[3] for row in data]
        
        # Write data rows
        for row in data:
            timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
            date = timestamp.strftime('%Y-%m-%d')
            time = timestamp.strftime('%H:%M:%S')
            recommendations = row[4] if row[4] else 'No recommendations'
            
            cw.writerow([
                date,
                time,
                f"{row[1]:.1f}",
                row[2],
                row[3],
                recommendations
            ])
        
        # Add statistics section
        cw.writerow([])  # Empty row for spacing
        cw.writerow(['Statistics'])
        if temps:
            cw.writerow(['Average Temperature', f"{sum(temps)/len(temps):.1f}°C"])
            cw.writerow(['Min Temperature', f"{min(temps):.1f}°C"])
            cw.writerow(['Max Temperature', f"{max(temps):.1f}°C"])
        if heart_rates:
            cw.writerow(['Average Heart Rate', f"{sum(heart_rates)/len(heart_rates):.0f} BPM"])
            cw.writerow(['Min Heart Rate', f"{min(heart_rates)} BPM"])
            cw.writerow(['Max Heart Rate', f"{max(heart_rates)} BPM"])
        if spo2s:
            cw.writerow(['Average SpO2', f"{sum(spo2s)/len(spo2s):.0f}%"])
            cw.writerow(['Min SpO2', f"{min(spo2s)}%"])
            cw.writerow(['Max SpO2', f"{max(spo2s)}%"])
        
        # Create the response
        output = si.getvalue()
        si.close()
        
        # Generate filename
        filename = f"health_report_{current_user.username}_{start_date}_to_{end_date}.csv"
        
        # Create response with CSV data
        response = send_file(
            io.BytesIO(output.encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=filename
        )
        
        return response
        
    except Exception as e:
        print(f"Error generating report: {str(e)}")
        flash('Error generating report', 'error')
        return redirect(url_for('dashboard'))

@app.route('/download-report-pdf/<start_date>/<end_date>')
@login_required
def download_report_pdf(start_date, end_date):
    try:
        # Create a BytesIO buffer for the PDF
        buffer = BytesIO()
        
        # Create the PDF object using ReportLab
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30)
        styles = getSampleStyleSheet()
        elements = []

        # Add title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            alignment=1  # Center alignment
        )
        elements.append(Paragraph("Health Report", title_style))
        elements.append(Spacer(1, 20))

        # Add report period
        period_style = ParagraphStyle(
            'Period',
            parent=styles['Heading2'],
            fontSize=14,
            alignment=1  # Center alignment
        )
        elements.append(Paragraph(f"Report Period: {start_date} to {end_date}", period_style))
        elements.append(Spacer(1, 20))

        # Add user information
        elements.append(Paragraph("User Information", styles["Heading2"]))
        user_data = [
            ["Name:", current_user.name],
            ["Age:", str(current_user.age)],
            ["Gender:", current_user.gender]
        ]
        user_table = Table(user_data, colWidths=[100, 400])
        user_table.setStyle(TableStyle([
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 0), (-1, -1), 12),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 12),
            ('GRID', (0, 0), (-1, -1), 1, colors.grey),
            ('BACKGROUND', (0, 0), (0, -1), colors.lightgrey),
        ]))
        elements.append(user_table)
        elements.append(Spacer(1, 20))

        # Fetch health data for the specified date range
        cursor.execute('''
            SELECT hd.timestamp, hd.temperature, hd.heart_rate, hd.spo2, 
                   GROUP_CONCAT(r.recommendation) as recommendations
            FROM health_data hd
            LEFT JOIN recommendations r ON hd.user_id = r.user_id 
                AND date(hd.timestamp) = date(r.timestamp)
            WHERE hd.user_id = ? 
                AND date(hd.timestamp) BETWEEN ? AND ?
            GROUP BY hd.id
            ORDER BY hd.timestamp DESC
        ''', (current_user.id, start_date, end_date))
        
        data = cursor.fetchall()

        # Add health data table
        elements.append(Paragraph("Health Data", styles["Heading2"]))
        if data:
            # Prepare table data
            table_data = [['Date', 'Time', 'Temperature (°C)', 'Heart Rate (BPM)', 'SpO2 (%)']]
            
            for row in data:
                timestamp = datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S')
                table_data.append([
                    timestamp.strftime('%Y-%m-%d'),
                    timestamp.strftime('%H:%M:%S'),
                    f"{row[1]:.1f}",
                    str(row[2]),
                    str(row[3])
                ])

            # Create and style the table
            health_table = Table(table_data, repeatRows=1)
            health_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
                ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 1), (-1, -1), 10),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(health_table)
            elements.append(Spacer(1, 20))

            # Calculate and add statistics
            temps = [row[1] for row in data]
            heart_rates = [row[2] for row in data]
            spo2s = [row[3] for row in data]

            elements.append(Paragraph("Statistics", styles["Heading2"]))
            stats_data = [
                ['Metric', 'Average', 'Minimum', 'Maximum'],
                ['Temperature', f"{sum(temps)/len(temps):.1f}°C", f"{min(temps):.1f}°C", f"{max(temps):.1f}°C"],
                ['Heart Rate', f"{sum(heart_rates)/len(heart_rates):.0f} BPM", f"{min(heart_rates)} BPM", f"{max(heart_rates)} BPM"],
                ['SpO2', f"{sum(spo2s)/len(spo2s):.0f}%", f"{min(spo2s)}%", f"{max(spo2s)}%"]
            ]
            
            stats_table = Table(stats_data, repeatRows=1)
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ]))
            elements.append(stats_table)

            # Add recommendations section
            elements.append(Spacer(1, 20))
            elements.append(Paragraph("Recommendations", styles["Heading2"]))
            for row in data:
                if row[4]:  # If recommendations exist
                    rec_text = row[4].replace(',', '\n• ')
                    elements.append(Paragraph(f"Date: {datetime.strptime(row[0], '%Y-%m-%d %H:%M:%S').strftime('%Y-%m-%d %H:%M:%S')}", styles["Normal"]))
                    elements.append(Paragraph(f"• {rec_text}", styles["Normal"]))
                    elements.append(Spacer(1, 10))
        else:
            elements.append(Paragraph("No health data available for the selected period.", styles["Normal"]))

        # Add current ThingSpeak data and recommendations
        sensor_data = fetch_thingspeak_data()
        if sensor_data:
            elements.append(Paragraph("Current Sensor Readings", styles["Heading2"]))
            sensor_table_data = [
                ["Metric", "Value"],
                ["Temperature", f"{sensor_data.get('temperature', '--')}°C"],
                ["Heart Rate", f"{sensor_data.get('heart_rate', '--')} BPM"],
                ["SpO2", f"{sensor_data.get('spo2', '--')}%"],
                ["Help Sensor", "Active" if sensor_data.get('flex1', 0) > 900 else "Inactive"],
                ["Water Sensor", "Detected" if sensor_data.get('flex2', 0) > 900 else "Not Detected"]
            ]
            
            sensor_table = Table(sensor_table_data)
            sensor_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(sensor_table)
            elements.append(Spacer(1, 20))

            # Add current recommendations
            current_recommendations = analyze_thingspeak_data(sensor_data)
            if current_recommendations:
                elements.append(Paragraph("Current Recommendations", styles["Heading2"]))
                for rec in current_recommendations:
                    severity_color = colors.red if rec['severity'] == 'high' else colors.orange
                    p = Paragraph(
                        f"• {rec['message']}",
                        ParagraphStyle(
                            'RecommendationStyle',
                            parent=styles['Normal'],
                            textColor=severity_color,
                            spaceAfter=10
                        )
                    )
                    elements.append(p)
                elements.append(Spacer(1, 20))

        # Generate PDF
        doc.build(elements)
        
        # Get the value of the BytesIO buffer
        pdf = buffer.getvalue()
        buffer.close()
        
        # Generate filename
        filename = f"health_report_{current_user.username}_{start_date}_to_{end_date}.pdf"
        
        # Create the response
        response = make_response(pdf)
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename={filename}'
        
        return response
        
    except Exception as e:
        print(f"Error generating PDF report: {str(e)}")
        flash('Error generating PDF report', 'error')
        return redirect(url_for('dashboard'))

def fetch_thingspeak_data():
    try:
        response = requests.get(THINGSPEAK_READ_API_URL)
        if response.status_code == 200:
            data = response.json()
            if 'feeds' in data and len(data['feeds']) > 0:
                latest_feed = data['feeds'][-1]
                return {
                    'flex1': int(latest_feed['field1']),
                    'flex2': int(latest_feed['field2']),
                    'flex3': int(latest_feed['field3']),
                    'flex4': int(latest_feed['field4']),
                    'temperature': float(latest_feed['field5']),
                    'heart_rate': int(latest_feed['field6']),
                    'spo2': int(latest_feed['field7'])
                }
    except Exception as e:
        print(f"Error fetching ThingSpeak data: {str(e)}")
    return None

def analyze_thingspeak_data(sensor_data):
    recommendations = []
    
    if not sensor_data:
        return []

    # Flex sensor analysis (Help detection)
    if sensor_data.get('flex1', 0) > 900:  # Threshold for help gesture
        recommendations.append({
            'message': "Help gesture detected! Please check on the user immediately.",
            'severity': 'high',
            'type': 'emergency'
        })

    # Water detection
    if sensor_data.get('flex2', 0) > 900:  # Threshold for water detection
        recommendations.append({
            'message': "Water detected! Check for potential spills or flooding.",
            'severity': 'high',
            'type': 'emergency'
        })

    # Temperature analysis
    temp = sensor_data.get('temperature')
    if temp:
        if temp > 37.8:
            recommendations.append({
                'message': f"High temperature detected ({temp:.1f}°C). Please rest and monitor. If persistent, consult a healthcare provider.",
                'severity': 'high',
                'type': 'health'
            })
        elif temp < 35.0:
            recommendations.append({
                'message': f"Low temperature detected ({temp:.1f}°C). Keep warm and monitor.",
                'severity': 'high',
                'type': 'health'
            })

    # Heart rate analysis
    hr = sensor_data.get('heart_rate')
    if hr:
        if hr > 100:
            recommendations.append({
                'message': f"Elevated heart rate ({hr} BPM). Take rest and practice deep breathing.",
                'severity': 'medium',
                'type': 'health'
            })
        elif hr < 60:
            recommendations.append({
                'message': f"Low heart rate ({hr} BPM). If you feel dizzy, consult a healthcare provider.",
                'severity': 'medium',
                'type': 'health'
            })

    # SpO2 analysis
    spo2 = sensor_data.get('spo2')
    if spo2:
        if spo2 < 95:
            recommendations.append({
                'message': f"Low oxygen saturation ({spo2}%). Practice deep breathing exercises. If below 90%, seek medical attention.",
                'severity': 'high',
                'type': 'health'
            })

    return recommendations

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000) 
