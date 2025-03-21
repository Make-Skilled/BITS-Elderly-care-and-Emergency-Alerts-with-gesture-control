#define BLYNK_TEMPLATE_ID "TMPL3fyDH50Cv"
#define BLYNK_TEMPLATE_NAME "MPU"
#define BLYNK_AUTH_TOKEN "v9j2UivcJ2QtaPl4a0OAjnx3vUtWDyyp"
#define BLYNK_PRINT Serial

#include <Wire.h>
#include "MAX30105.h"
#include "heartRate.h"
#include "spo2_algorithm.h"
#include <OneWire.h>
#include <DallasTemperature.h>
#include <BlynkSimpleEsp32.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ThingSpeak.h>

#define THINGSPEAK_URL "https://api.thingspeak.com/update"
#define THINGSPEAK_API_KEY "DKFMSF5LBO7MG9F5"

int channelid = 2571433;
const char* apikey = "DKFMSF5LBO7MG9F5";

WiFiClient client;

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

// Flex Sensors
int flex1 = 32;
int flex2 = 33;
int flex3 = 34;  // GPIO 34 is input-only
int flex4 = 35;  // GPIO 35 is input-only

void setup() {
  Serial.begin(115200);
  pinMode(flex1, INPUT);
  pinMode(flex2, INPUT);

  Serial.println("Initializing sensors...");
  WiFi.begin("Act", "Madhumakeskilled");
  while (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    Serial.println("Connecting to WiFi...");
  }
  
  Blynk.begin(BLYNK_AUTH_TOKEN, WiFi.SSID().c_str(), WiFi.psk().c_str());

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

  ThingSpeak.begin(client);
}

void sendToThingSpeak(int val1, int val2, int val3, int val4, float temperatureC, int heartRate, int spo2) {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String url = String(THINGSPEAK_URL) + "?api_key=" + THINGSPEAK_API_KEY +
                 "&field1=" + String(val1) +
                 "&field2=" + String(val2) +
                 "&field3=" + String(val3) +
                 "&field4=" + String(val4) +
                 "&field5=" + String(temperatureC) +
                 "&field6=" + String(heartRate) +
                 "&field7=" + String(spo2);

    http.begin(url);
    int httpCode = http.GET();
    if (httpCode > 0) {
      Serial.println("Data sent to ThingSpeak");
    } else {
      Serial.println("Error sending data");
    }
    http.end();
  }
}

void loop() {
  Blynk.run();

  int val1 = analogRead(flex1);
  int val2 = analogRead(flex2);
  int val3 = analogRead(flex3);
  int val4 = analogRead(flex4);

  Serial.print("Flex Sensor Values: ");
  Serial.print(val1); Serial.print(", ");
  Serial.print(val2); Serial.print(", ");
  Serial.print(val3); Serial.print(", ");
  Serial.println(val4);


  // Read MAX30105 Heart Rate & SpO2
  for (int i = 0; i < bufferLength; i++) {
    unsigned long startTime = millis();
    while (particleSensor.available() == false) {
      if (millis() - startTime > 500) {
        Serial.println("Sensor timeout");
        return;
      }
      particleSensor.check();
    }
    redBuffer[i] = particleSensor.getRed();
    irBuffer[i] = particleSensor.getIR();
    particleSensor.nextSample();
  }

  maxim_heart_rate_and_oxygen_saturation(irBuffer, bufferLength, redBuffer, &spo2, &validSPO2, &heartRate, &validHeartRate);
  Serial.print("Heart Rate: ");
    Serial.print(validHeartRate ? heartRate : -1);
    Serial.println(" BPM");
    
    Serial.print("SpO2: ");
    Serial.print(validSPO2 ? spo2 : -1);
    Serial.println(" %");

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
  
  sendToThingSpeak(val1, val2, val3, val4, temperatureC, heartRate, spo2);
  delay(1000);
}