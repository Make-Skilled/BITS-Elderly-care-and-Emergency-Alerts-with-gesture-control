# Elderly Care and Emergency Alerts with Gesture Control
A comprehensive healthcare monitoring system that combines hardware sensors with a web-based dashboard for elderly care monitoring.
## Features
- Real-time vital signs monitoring (heart rate, SpO2, temperature)- Gesture-based emergency alerts using flex sensors
- Web dashboard for caregivers and medical staff- Patient management system
- Alert history and reporting
## Hardware Requirements
- ESP32 development board- MAX30105 Pulse Oximeter sensor
- DS18B20 Temperature sensor- 4x Flex sensors
- LCD display (I2C interface)- Connecting wires and breadboard
## Software Setup
1. Install Python requirements:
   ```bash   pip install -r requirements.txt
   ```
2. Initialize the database:   ```bash
   python init_db.py   ```
3. Configure ThingSpeak:
   - Create a ThingSpeak account   - Create a new channel with 7 fields
   - Update the channel ID and API key in the ESP32 code and app.py
4. Upload Arduino code:   - Upload `arduino flex sensor code.ino` to Arduino board
   - Upload `finalcode.ino` to ESP32 board
5. Start the Flask application:   ```bash
   python app.py   ```
6. Access the web interface at `http://localhost:5000`
## System Architecture
- Arduino: Handles flex sensors and LCD display
- ESP32: Manages vital sign sensors and ThingSpeak communication- Flask Web App: Provides user interface and data visualization
- ThingSpeak: Acts as IoT data bridge
## License





























# BITS-Elderly-care-and-Emergency-Alerts-with-gesture-control
