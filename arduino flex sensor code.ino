#include <Wire.h>
#include <LiquidCrystal_I2C.h>

LiquidCrystal_I2C lcd(0x27, 16, 2);

// Define flex sensor pins
int flex1 = A0;
int flex2 = A1;
int flex3 = A2;
int flex4 = A3;

void setup() {
    pinMode(flex1, INPUT);
    pinMode(flex2, INPUT);
    pinMode(flex3, INPUT);
    pinMode(flex4, INPUT);
    
    Wire.begin();
    lcd.begin(16, 2); // Initialize the LCD
    lcd.home();
    lcd.backlight(); // Enable backlight
    lcd.print("Patient Monitor");
    delay(1000);
    
    Serial.begin(115200); // Set baud rate for ESP32 communication
}

void loop() {
    // Read values from flex sensors
    int val1 = analogRead(flex1);
    int val2 = analogRead(flex2);
    int val3 = analogRead(flex3);
    int val4 = analogRead(flex4);
    
    // Display flex values on LCD
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("F1:"); lcd.print(val1);
    lcd.setCursor(8, 0);
    lcd.print("F2:"); lcd.print(val2);
    lcd.setCursor(0, 1);
    lcd.print("F3:"); lcd.print(val3);
    lcd.setCursor(8, 1);
    lcd.print("F4:"); lcd.print(val4);

    // Send data to ESP32 via Serial
    Serial.print("Flex Sensor Values: ");
    Serial.print(val1); Serial.print(", ");
    Serial.print(val2); Serial.print(", ");
    Serial.print(val3); Serial.print(", ");
    Serial.println(val4);

    // Check for threshold crossings and display alert
    if (val1 < 750 || val1 > 760) {
        lcd.clear();
        lcd.print("Alert: Need Food");
//        Serial.println("Alert: Need Food");
    } 
    else if (val2 < 720 || val2 > 730) {
        lcd.clear();
        lcd.print("Alert: Need Water");
//        Serial.println("Alert: Need Water");
    } 
    else if (val3 < 730 || val3 > 740) {
        lcd.clear();
        lcd.print("Alert: Washroom");
//        Serial.println("Alert: Washroom");
    } 
    else if (val4 < 720 || val4 > 730) {
        lcd.clear();
        lcd.print("Alert: Need Help");
//        Serial.println("Alert: Need Help");
    }

    delay(500); // Small delay for stability
}
