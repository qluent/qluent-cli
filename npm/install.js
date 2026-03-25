const fs = require("fs");
const path = require("path");
const http = require("http");
const https = require("https");

const pkg = require("./package.json");

function platformArtifact() {
  const platformMap = {
    darwin: "darwin",
    linux: "linux",
    win32: "windows",
  };
  const archMap = {
    x64: "x64",
    arm64: "arm64",
  };

  const platform = platformMap[process.platform];
  const arch = archMap[process.arch];

  if (!platform || !arch) {
    throw new Error(`Unsupported platform ${process.platform}/${process.arch}`);
  }

  const extension = process.platform === "win32" ? ".exe" : "";
  return `qluent-${platform}-${arch}${extension}`;
}

function resolveDownloadUrl() {
  if (process.env.QLUENT_CLI_BIN_URL) {
    return process.env.QLUENT_CLI_BIN_URL;
  }

  const baseUrl =
    process.env.QLUENT_CLI_DIST_BASE_URL ||
    "https://downloads.qluent.io/cli";

  return `${baseUrl}/v${pkg.version}/${platformArtifact()}`;
}

function download(url, destination) {
  const transport = url.startsWith("https:") ? https : http;

  return new Promise((resolve, reject) => {
    const request = transport.get(url, (response) => {
      if (
        response.statusCode &&
        response.statusCode >= 300 &&
        response.statusCode < 400 &&
        response.headers.location
      ) {
        download(response.headers.location, destination).then(resolve, reject);
        return;
      }

      if (response.statusCode !== 200) {
        reject(new Error(`Download failed with status ${response.statusCode}`));
        return;
      }

      const file = fs.createWriteStream(destination, { mode: 0o755 });
      response.pipe(file);
      file.on("finish", () => {
        file.close(resolve);
      });
      file.on("error", reject);
    });

    request.on("error", reject);
  });
}

async function main() {
  if (process.env.QLUENT_SKIP_DOWNLOAD === "1") {
    console.log("Skipping Qluent CLI binary download");
    return;
  }

  const binDir = path.join(__dirname, "bin");
  const destination = path.join(
    binDir,
    process.platform === "win32" ? "qluent.exe" : "qluent"
  );

  fs.mkdirSync(binDir, { recursive: true });

  const url = resolveDownloadUrl();
  console.log(`Downloading Qluent CLI from ${url}`);
  await download(url, destination);
  fs.chmodSync(destination, 0o755);
  console.log(`Installed Qluent CLI to ${destination}`);
}

main().catch((error) => {
  console.error(`Failed to install Qluent CLI: ${error.message}`);
  process.exit(1);
});
