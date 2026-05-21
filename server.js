const express = require('express');
const { spawn } = require('child_process');
const db = require('./database');

const app = express();

process.on('uncaughtException', (err) => console.error(err));
process.on('unhandledRejection', (err) => console.error(err));


app.use(express.json());
app.use(express.static('public'));

let currentCommand = "NONE";
let bottleCount = 0;
let yoloRunning = false;
let yoloProcess = null;

function getOrCreateUser(mac, callback) {
  db.get(`SELECT * FROM sessions WHERE mac_address = ?`, [mac], (err, row) => {
    if (err) return callback(err);
    if (!row) {
      db.run(
        `INSERT INTO sessions (mac_address, time_remaining, tokens, status) VALUES (?, 0, 0, 'inactive')`,
        [mac],
        function (err) {
          if (err) return callback(err);
          db.get(`SELECT * FROM sessions WHERE mac_address = ?`, [mac], callback);
        }
      );
    } else {
      callback(null, row);
    }
  });
}

app.get('/api/device', (req, res) => {
  res.send(currentCommand);
  currentCommand = "NONE";
});

app.post('/api/detect', (req, res) => {
  const { result, mac } = req.body;

  if (!mac) return res.status(400).json({ error: "MAC address missing" });

  if (result === "ACCEPT") {
    bottleCount++;                    // ✅ this is what /api/count returns
    currentCommand = "ACCEPT";
    sendToESP("ACCEPT");

    console.log(`✅ Bottle accepted. Total: ${bottleCount}`);  // ✅ debug log

    getOrCreateUser(mac, (err, user) => {
      if (err) return console.error(err);
      const newTime = user.time_remaining + 300;
      db.run(
        `UPDATE sessions SET time_remaining = ?, status = 'active', last_update = CURRENT_TIMESTAMP WHERE mac_address = ?`,
        [newTime, mac]
      );
    });
  } else {
    currentCommand = "REJECT";
    sendToESP("REJECT");
  }

  res.json({ status: "ok", count: bottleCount }); 
});

app.get('/', (req, res) => {
  res.sendFile(__dirname + '/public/index.html');
});

app.get('/api/count', (req, res) => {
  res.json({ count: bottleCount });
});

app.post('/api/start', (req, res) => {
  if (yoloRunning) return res.json({ status: "already running" });

  yoloRunning = true;
  bottleCount = 0;              
  yoloProcess = spawn('python3', ['main.py']);

  yoloProcess.stdout.on('data', (data) => console.log(data.toString()));  
  yoloProcess.stderr.on('data', (data) => console.error(data.toString()));
  yoloProcess.on('close', () => {
    yoloRunning = false;
    console.log("🛑 YOLO process stopped");
  });
  yoloProcess.on('error', (err) => {
    console.error(err);
    yoloRunning = false;
  });

  res.json({ status: "started" });
});

app.post('/api/stop', (req, res) => {
  if (yoloRunning && yoloProcess) {
    yoloProcess.kill('SIGKILL');
    yoloRunning = false;
    console.log("🛑 YOLO process killed");
  }
  res.json({ status: "stopped", count: bottleCount });
});

// Captive portal redirects
app.get('/generate_204', (req, res) => res.redirect('/'));
app.get('/gen_204', (req, res) => res.redirect('/'));
app.get('/hotspot-detect.html', (req, res) => res.redirect('/'));
app.get('/ncsi.txt', (req, res) => res.redirect('/'));

app.get('/api/time/:mac', (req, res) => {
  const mac = req.params.mac;
  db.get(`SELECT * FROM sessions WHERE mac_address = ?`, [mac], (err, row) => {
    if (err) return res.status(500).json(err);
    if (!row) return res.json({ time: 0 });
    res.json({ time: row.time_remaining, status: row.status });
  });
});

// ⏱️ Session countdown timer
setInterval(() => {
  db.all(`SELECT * FROM sessions WHERE status = 'active'`, [], (err, rows) => {
    if (err) return console.error(err);
    rows.forEach(user => {
      let newTime = user.time_remaining - 1;
      if (newTime <= 0) {
        db.run(
          `UPDATE sessions SET time_remaining = 0, status = 'expired' WHERE mac_address = ?`,
          [user.mac_address]
        );
        console.log(`⏰ Session expired: ${user.mac_address}`);
      } else {
        db.run(
          `UPDATE sessions SET time_remaining = ? WHERE mac_address = ?`,
          [newTime, user.mac_address]
        );
      }
    });
  });
}, 1000);


app.listen(8080, '0.0.0.0', () => {
  console.log("🚀 Server listening on port 8080");
}); //THHIS IS ONLY FOR PYTHON MAIN.JS callling