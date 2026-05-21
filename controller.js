const { SerialPort } = require('serialport');
const readline = require('readline');

// 🔌 Connect to ESP8266 NodeMCU
const port = new SerialPort({
  path: '/dev/ttyUSB1',  // ✅ Changed from USB0 to USB1
  baudRate: 9600,
});

port.on('open', () => {
  console.log("✅ ESP8266 NodeMCU connected");
  console.log("Press X = LEFT | B = RIGHT | Ctrl+C to exit");
});

port.on('error', (err) => {
  console.error("❌ Port Error:", err.message);
  console.log("👉 Check your COM port in Device Manager (Windows) or ls /dev/tty* (Linux/Mac)");
});

// 📥 Read serial messages from ESP8266
port.on('data', (data) => {
  console.log("📟 ESP8266:", data.toString().trim());
});

// 🎮 Keyboard input
readline.emitKeypressEvents(process.stdin);
process.stdin.setRawMode(true);

process.stdin.on('keypress', (str, key) => {
  if (key.sequence === 'x') {
    port.write("LEFT\n");
    console.log("⬅️  Sending LEFT  → Servo sweeps 90° to 180°");
  }

  if (key.sequence === 'b') {
    port.write("RIGHT\n");
    console.log("➡️  Sending RIGHT → Servo sweeps 90° to 0°");
  }

  if (key.ctrl && key.name === 'c') {
    console.log("\n👋 Disconnecting...");
    port.close();
    process.exit();
  }
});