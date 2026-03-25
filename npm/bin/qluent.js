#!/usr/bin/env node

const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const executableName = process.platform === "win32" ? "qluent.exe" : "qluent";
const executablePath = path.join(__dirname, executableName);

if (!fs.existsSync(executablePath)) {
  console.error(
    "Qluent CLI binary is missing. Reinstall @qluent/cli or run with QLUENT_SKIP_DOWNLOAD=1 only in development."
  );
  process.exit(1);
}

const result = spawnSync(executablePath, process.argv.slice(2), {
  stdio: "inherit",
});

if (result.error) {
  console.error(result.error.message);
  process.exit(1);
}

process.exit(result.status ?? 1);
