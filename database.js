const sqlite3 = require('sqlite3').verbose();

const db = new sqlite3.Database('./wifi_vendo.db', (err) => {
  if (err) {
    console.error(err.message);
  } else {
    console.log('Connected to SQLite database.');
  }
});

db.serialize(() => {
  db.run(`
    CREATE TABLE IF NOT EXISTS sessions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      mac_address TEXT UNIQUE,
      time_remaining INTEGER DEFAULT 0,
      tokens INTEGER DEFAULT 0,
      status TEXT DEFAULT 'inactive',
      last_update DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);
});

module.exports = db;