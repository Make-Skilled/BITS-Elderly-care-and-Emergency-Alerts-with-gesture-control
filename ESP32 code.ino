#define BLYNK_TEMPLATE_ID "TMPL3fyDH50Cv"
#define BLYNK_TEMPLATE_NAME "MPU"
#define BLYNK_AUTH_TOKEN "v9j2UivcJ2QtaPl4a0OAjnx3vUtWDyyp"

#include <Wire.h>
#include "MAX30105.h"
#include "heartRate.h"
#include "spo2_algorithm.h"
#include <OneWire.h>
#include <DallasTemperature.h>
#include <BlynkSimpleEsp32.h>

// MAX30105 Pulse Oximeter
MAX30105 particleSensor;
const byte RATE_SIZE = 4;
byte rates[RATE_SIZE];
byte rateSpot = 0;
long lastBeat = 0;
float beatsPerMinute;
int beatAvg;
uint32_t irBuffer[100];
uint32_t redBuffer[100];
int bufferLength = 100;
int32_t spo2;
int8_t validSPO2;
int32_t heartRate;
int8_t validHeartRate;
// DS18B20 Temperature Sensor
#define ONE_WIRE_BUS 4
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature sensors(&oneWire);

void setup() {
  Serial.begin(115200);  // Initialize serial communication with ESP32
  Serial.println("Initializing sensors...");
  Blynk.begin(BLYNK_AUTH_TOKEN, "Act", "Madhumakeskilled");

  // Initialize MAX30105 Pulse Oximeter
  if (!particleSensor.begin(Wire, I2C_SPEED_FAST)) {
    Serial.println("MAX30105 sensor not found. Check wiring!");
    while (1);
  }
  particleSensor.setup();
  particleSensor.setPulseAmplitudeRed(0x1F);
  particleSensor.setPulseAmplitudeIR(0x1F);
  Serial.println("MAX30105 Pulse Oximeter Initialized");

  // Initialize DS18B20 Temperature Sensor
  sensors.begin();
  Serial.println("DS18B20 Temperature Sensor Initialized");
}

void loop() {
  Blynk.run();

  if (Serial.available()) {
    String flexData = Serial.readStringUntil('\n');  // Read the entire line from Arduino
    int flex1 = 0, flex2 = 0, flex3 = 0, flex4 = 0;
    
    
    // Split the string by commas and assign values
    int comma1 = flexData.indexOf(',');
    int comma2 = flexData.indexOf(',', comma1 + 1);
    int comma3 = flexData.indexOf(',', comma2 + 1);
    
    if (comma1 != -1) {
      flex1 = flexData.substring(0, comma1).toInt();  // Extract the first value
      flex2 = flexData.substring(comma1 + 1, comma2).toInt();  // Extract the second value
      flex3 = flexData.substring(comma2 + 1, comma3).toInt();  // Extract the third value
      flex4 = flexData.substring(comma3 + 1).toInt();  // Extract the fourth value
    }
    
    // Print flex sensor values to Serial Monitor
    Serial.print("Flex1: "); Serial.print(flex1);
    Serial.print(" Flex2: "); Serial.print(flex2);
    Serial.print(" Flex3: "); Serial.print(flex3);
    Serial.print(" Flex4: "); Serial.println(flex4);
  }

  // Read MAX30105 Heart Rate & SpO2
  for (int i = 0; i < bufferLength; i++) {
    while (particleSensor.available() == false)
      particleSensor.check();
    redBuffer[i] = particleSensor.getRed();
    irBuffer[i] = particleSensor.getIR();
    particleSensor.nextSample();
  }
  
  maxim_heart_rate_and_oxygen_saturation(irBuffer, bufferLength, redBuffer, &spo2, &validSPO2, &heartRate, &validHeartRate);
  Serial.print("Heart Rate: ");
  if (validHeartRate) Serial.print(heartRate);
  else Serial.print("Invalid");
  Serial.print(" bpm, SpO2: ");
  if (validSPO2) Serial.print(spo2);
  else Serial.print("Invalid");
  Serial.println(" %");

  // Send data to Blynk
  Blynk.virtualWrite(V1, heartRate);
  Blynk.virtualWrite(V2, spo2);
  if (validHeartRate && heartRate < 60) {
    Blynk.logEvent("low_heart_rate", "Heart rate is below 60 bpm!");
  }
  if (validSPO2 && spo2 < 90) {
    Blynk.logEvent("low_spo2", "SpO2 level is below 90%!");
  }

  // Read DS18B20 Temperature Sensor
  sensors.requestTemperatures();
  float temperatureC = sensors.getTempCByIndex(0);
  if (temperatureC != DEVICE_DISCONNECTED_C) {
    Serial.print("Temperature: ");
    Serial.print(temperatureC);
    Serial.println(" °C");
    Blynk.virtualWrite(V3, temperatureC);
    if (temperatureC > 40) {
      Blynk.logEvent("high_temp", "Temperature is Very High");
    }
  } else {
    Serial.println("Error: Could not read temperature data.");
  }
  delay(1000);
}
