#include "Arduino_BHY2.h"
#include "ArduinoBLE.h"
#include "Nicla_System.h"
#include <math.h>

#define G_TO_MS2 9.81
#define INTERVAL_MS 10  // 100 Hz

BLEService senseService("19b10000-0000-537e-4f6c-d104768a1214");
BLECharacteristic dataCharacteristic("19b10000-5001-537e-4f6c-d104768a1214", BLERead | BLENotify, 128);

SensorXYZ accelerometer(SENSOR_ID_LACC);
SensorXYZ gyroscope(SENSOR_ID_GYRO);
SensorQuaternion rotation(SENSOR_ID_RV);

float acc_range = 8.0;
float gyro_range = 1000.0;
float scale_acc = acc_range / 32767.0;
float scale_gyro = gyro_range / 32767.0;

int count = 0;
unsigned long lastUpdate = 0;

void setup() {
  Serial.begin(115200);
  while (!Serial);

  BHY2.begin();
  accelerometer.begin();
  gyroscope.begin();
  rotation.begin();

  nicla::begin();
  nicla::leds.begin();
  nicla::leds.setColor(red);

  if (!BLE.begin()) {
    Serial.println("BLE init failed!");
    while (1);
  }

  String address = BLE.address();
  address.toUpperCase();
  String name = "NiclaME-" + address.substring(address.length() - 5);
  BLE.setLocalName(name.c_str());
  BLE.setDeviceName(name.c_str());
  BLE.setAdvertisedService(senseService);
  senseService.addCharacteristic(dataCharacteristic);
  BLE.addService(senseService);
  BLE.advertise();

  BLE.setEventHandler(BLEConnected, [](BLEDevice central) {
    nicla::leds.setColor(green);
  });

  BLE.setEventHandler(BLEDisconnected, [](BLEDevice central) {
    nicla::leds.setColor(red);
  });
}

void loop() {
  BHY2.update(10);

  unsigned long now = millis();
  if (now - lastUpdate >= INTERVAL_MS) {
    lastUpdate = now;

    count++;
    if (count == 50) {
      nicla::leds.setColor(green);
    } else if (count == 100) {
      nicla::leds.setColor(blue);
      count = 0;
    }

    float ax = accelerometer.x() * scale_acc * G_TO_MS2;
    float ay = accelerometer.y() * scale_acc * G_TO_MS2;
    float az = accelerometer.z() * scale_acc * G_TO_MS2;

    float gx = gyroscope.x() * scale_gyro;
    float gy = gyroscope.y() * scale_gyro;
    float gz = gyroscope.z() * scale_gyro;

    float qw = rotation.w();
    float qx = rotation.x();
    float qy = rotation.y();
    float qz = rotation.z();

    float roll  = atan2(2.0f * (qw * qx + qy * qz), 1.0f - 2.0f * (qx * qx + qy * qy)) * 180.0 / PI;
    float pitch = asin(2.0f * (qw * qy - qz * qx)) * 180.0 / PI;
    float yaw   = atan2(2.0f * (qw * qz + qx * qy), 1.0f - 2.0f * (qy * qy + qz * qz)) * 180.0 / PI;

    String json = "{\"ax\":" + String(ax, 2) + ",\"ay\":" + String(ay, 2) + ",\"az\":" + String(az, 2) +
                  ",\"gx\":" + String(gx, 2) + ",\"gy\":" + String(gy, 2) + ",\"gz\":" + String(gz, 2) +
                  ",\"roll\":" + String(roll, 2) + ",\"pitch\":" + String(pitch, 2) + ",\"yaw\":" + String(yaw, 2) + "}";

    Serial.println(json);

    if (BLE.connected()) {
      dataCharacteristic.writeValue(json.c_str());
    }
  }
}