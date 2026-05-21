#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <Servo.h>

const char* ssid = "MarkyKunFREEWIFI";
const char* password = "39858078";

const char* serverURL = "http://192.168.10.99/api/device";

#define SERVO_PIN 5

Servo myServo;

int centerPos = 90;
int rightPos = 150;   
int leftPos  = 30;    

void setup() {
  Serial.begin(115200);

  myServo.attach(SERVO_PIN);
  myServo.write(centerPos);

  WiFi.begin(ssid, password);

  Serial.print("Connecting");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\nConnected!");
}

void loop() {
  if (WiFi.status() == WL_CONNECTED) {

    WiFiClient client;
    HTTPClient http;

    http.begin(client, serverURL);
    int httpCode = http.GET();

    if (httpCode > 0) {
      String payload = http.getString();
      Serial.println(payload);

      if (payload == "ACCEPT") {
        acceptBottle();
      }
      else if (payload == "REJECT") {
        rejectBottle();
      }
    }

    http.end();
  }

  delay(2000);
}


void acceptBottle() {
  Serial.println("ACCEPTED");

  myServo.write(rightPos);
  delay(800);

  myServo.write(centerPos);
  delay(500);
}

void rejectBottle() {
  Serial.println("REJECTED");

  myServo.write(leftPos);
  delay(800);

  myServo.write(centerPos);
  delay(500);
}
