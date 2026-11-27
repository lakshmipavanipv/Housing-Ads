// Ring QA Portal - ESP32 BLE bridge firmware
// Turns an ESP32 board into a USB-serial <-> Bluetooth LE "central" that can hold up to 9 rings at once.
// Library: NimBLE-Arduino 1.4.x   Core: esp32 by Espressif 2.0.x   Serial: 115200 baud
//
// Protocol (one line per message, fields separated by single spaces, bytes as lowercase hex):
//   host -> board : <id> INFO | SCAN <ms> | CONN <addr> <addrType> | DISC <addr>
//                   READ <addr> <svc> <chr> | WRITE <addr> <svc> <chr> <hex> <rsp0|1> | SUB <addr> <svc> <chr>
//   board -> host : <id> OK [...] | <id> ERR <message>
//                   ADV <addr> <addrType> <rssi> <nameHex>        (during SCAN)
//                   NTF <addr> <chrUuid> <hex>                     (notifications, any time)
//                   DISCONNECTED <addr>                            (link lost, any time)
//                   READY RQA-BRIDGE-1.0                           (after boot)
#include <NimBLEDevice.h>
#include <map>
#include <string>

#define FW_NAME "RQA-BRIDGE-1.0"
#ifndef CONFIG_BT_NIMBLE_MAX_CONNECTIONS
#define CONFIG_BT_NIMBLE_MAX_CONNECTIONS 3
#endif

static SemaphoreHandle_t outLock;
static std::map<std::string, NimBLEClient*> clients;

static void out(const String& s) {
  xSemaphoreTake(outLock, portMAX_DELAY);
  // When the portal is closed nobody reads the USB port; on native-USB boards (ESP32-C3/S3) a blocking write
  // would then hang the whole board while rings keep sending notifications. Drop the line instead.
  if (Serial.availableForWrite() >= (int)s.length() + 2) Serial.println(s);
  xSemaphoreGive(outLock);
}

static String hexOf(const uint8_t* d, size_t n) {
  static const char* H = "0123456789abcdef";
  String s;
  s.reserve(n * 2 + 1);
  for (size_t i = 0; i < n; i++) { s += H[d[i] >> 4]; s += H[d[i] & 15]; }
  return s;
}

static std::string unhex(const char* h) {
  std::string b;
  size_t n = strlen(h);
  for (size_t i = 0; i + 1 < n; i += 2) {
    char t[3] = {h[i], h[i + 1], 0};
    b.push_back((char)strtol(t, nullptr, 16));
  }
  return b;
}

class ClientCB : public NimBLEClientCallbacks {
  void onDisconnect(NimBLEClient* c) override {
    out(String("DISCONNECTED ") + c->getPeerAddress().toString().c_str());
  }
};
static ClientCB clientCB;

static void onNotify(NimBLERemoteCharacteristic* ch, uint8_t* d, size_t n, bool isNotify) {
  String addr = ch->getRemoteService()->getClient()->getPeerAddress().toString().c_str();
  out("NTF " + addr + " " + ch->getUUID().toString().c_str() + " " + hexOf(d, n));
}

static NimBLERemoteCharacteristic* findChr(const char* addr, const char* svc, const char* chr, String& err) {
  auto it = clients.find(std::string(addr));
  if (it == clients.end() || !it->second->isConnected()) { err = "not connected"; return nullptr; }
  NimBLERemoteService* s = it->second->getService(NimBLEUUID(svc));
  if (!s) { err = "service not found"; return nullptr; }
  NimBLERemoteCharacteristic* c = s->getCharacteristic(NimBLEUUID(chr));
  if (!c) { err = "characteristic not found"; return nullptr; }
  return c;
}

static void handle(char* line) {
  char* id = strtok(line, " ");
  char* cmd = strtok(nullptr, " ");
  if (!id || !cmd) return;
  String rid(id);
  auto ok = [&](const String& x) { out(rid + " OK" + (x.length() ? " " + x : String(""))); };
  auto er = [&](const String& x) { out(rid + " ERR " + x); };
  char* a1 = strtok(nullptr, " ");
  char* a2 = strtok(nullptr, " ");
  char* a3 = strtok(nullptr, " ");
  char* a4 = strtok(nullptr, " ");
  char* a5 = strtok(nullptr, " ");
  String err;

  if (!strcmp(cmd, "INFO")) {
    ok(String("INFO ") + NimBLEDevice::getAddress().toString().c_str() + " " + CONFIG_BT_NIMBLE_MAX_CONNECTIONS + " " + FW_NAME);

  } else if (!strcmp(cmd, "SCAN")) {
    uint32_t ms = a1 ? atoi(a1) : 5000;
    NimBLEScan* sc = NimBLEDevice::getScan();
    sc->setActiveScan(true);
    sc->setInterval(100);
    sc->setWindow(99);
    sc->clearResults();
    NimBLEScanResults r = sc->start((ms + 999) / 1000, false);
    for (int i = 0; i < r.getCount(); i++) {
      NimBLEAdvertisedDevice d = r.getDevice(i);
      std::string nm = d.getName();
      out(String("ADV ") + d.getAddress().toString().c_str() + " " + d.getAddress().getType() + " " + d.getRSSI() +
          " " + hexOf((const uint8_t*)nm.data(), nm.size()));
    }
    sc->clearResults();
    ok("SCAN");

  } else if (!strcmp(cmd, "CONN")) {
    if (!a1) { er("missing address"); return; }
    NimBLEAddress addr(std::string(a1), (uint8_t)(a2 ? atoi(a2) : 0));
    std::string key = addr.toString();
    auto it = clients.find(key);
    NimBLEClient* c = it != clients.end() ? it->second : nullptr;
    if (c && c->isConnected()) { ok(""); return; }
    if (!c) {
      c = NimBLEDevice::getDisconnectedClient();
      if (!c) {
        if (NimBLEDevice::getClientListSize() >= CONFIG_BT_NIMBLE_MAX_CONNECTIONS) { er("board full"); return; }
        c = NimBLEDevice::createClient();
      }
      c->setClientCallbacks(&clientCB, false);
      c->setConnectTimeout(10);
    }
    if (!c->connect(addr)) { er("connect failed"); return; }
    for (auto i = clients.begin(); i != clients.end();) {
      if (i->second == c && i->first != key) i = clients.erase(i); else ++i;
    }
    clients[key] = c;
    ok("");

  } else if (!strcmp(cmd, "DISC")) {
    if (!a1) { er("missing address"); return; }
    auto it = clients.find(std::string(a1));
    if (it != clients.end() && it->second->isConnected()) it->second->disconnect();
    ok("");

  } else if (!strcmp(cmd, "READ")) {
    if (!a3) { er("usage READ addr svc chr"); return; }
    NimBLERemoteCharacteristic* ch = findChr(a1, a2, a3, err);
    if (!ch) { er(err); return; }
    auto v = ch->readValue();
    ok(hexOf((const uint8_t*)v.data(), v.length()));

  } else if (!strcmp(cmd, "WRITE")) {
    if (!a4) { er("usage WRITE addr svc chr hex rsp"); return; }
    NimBLERemoteCharacteristic* ch = findChr(a1, a2, a3, err);
    if (!ch) { er(err); return; }
    std::string b = unhex(a4);
    bool rsp = a5 && a5[0] == '1';
    if (!ch->writeValue((const uint8_t*)b.data(), b.size(), rsp)) { er("write failed"); return; }
    ok("");

  } else if (!strcmp(cmd, "SUB")) {
    if (!a3) { er("usage SUB addr svc chr"); return; }
    NimBLERemoteCharacteristic* ch = findChr(a1, a2, a3, err);
    if (!ch) { er(err); return; }
    if (!ch->canNotify() && !ch->canIndicate()) { er("characteristic cannot notify"); return; }
    if (!ch->subscribe(ch->canNotify(), onNotify, true)) { er("subscribe failed"); return; }
    ok("");

  } else {
    er(String("unknown command ") + cmd);
  }
}

void setup() {
  Serial.setRxBufferSize(1024);
#if ARDUINO_USB_CDC_ON_BOOT
  Serial.setTxBufferSize(4096);  // room for bursts of notifications from 9 rings
  Serial.setTxTimeoutMs(0);      // never block on USB when the portal is not reading
#endif
  Serial.begin(115200);
  outLock = xSemaphoreCreateMutex();
  NimBLEDevice::init("");
  NimBLEDevice::setPower(ESP_PWR_LVL_P9);
  out("READY " FW_NAME);
}

void loop() {
  static char buf[700];
  static size_t n = 0;
  while (Serial.available()) {
    char ch = (char)Serial.read();
    if (ch == '\n' || ch == '\r') {
      if (n) { buf[n] = 0; handle(buf); n = 0; }
    } else if (n < sizeof(buf) - 1) {
      buf[n++] = ch;
    }
  }
  delay(1);
}
