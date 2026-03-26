const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");

const DEFAULT_DIST_BASE_URL =
  "https://github.com/qluent/qluent-cli/releases/download";

function platformArtifact({
  platform = process.platform,
  arch = process.arch,
} = {}) {
  const platformMap = {
    darwin: "darwin",
    linux: "linux",
    win32: "windows",
  };
  const archMap = {
    x64: "x64",
    arm64: "arm64",
  };

  const normalizedPlatform = platformMap[platform];
  const normalizedArch = archMap[arch];

  if (!normalizedPlatform || !normalizedArch) {
    throw new Error(`Unsupported platform ${platform}/${arch}`);
  }

  const extension = normalizedPlatform === "windows" ? ".exe" : "";
  return `qluent-${normalizedPlatform}-${normalizedArch}${extension}`;
}

function allowInsecureDownload(env = process.env) {
  return env.QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD === "1";
}

function assertSecureUrl(url, { env = process.env } = {}) {
  const parsed = new URL(url);
  if (parsed.protocol === "https:") {
    return parsed;
  }
  if (parsed.protocol === "http:" && allowInsecureDownload(env)) {
    return parsed;
  }

  throw new Error(
    `Refusing insecure download URL: ${url}. Use HTTPS or set QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD=1 for local development.`
  );
}

function resolveDownloadUrl({
  env = process.env,
  version,
  platform = process.platform,
  arch = process.arch,
} = {}) {
  if (!version) {
    throw new Error("version is required");
  }
  if (env.QLUENT_CLI_BIN_URL) {
    return assertSecureUrl(env.QLUENT_CLI_BIN_URL, { env }).toString();
  }

  const baseUrl = env.QLUENT_CLI_DIST_BASE_URL || DEFAULT_DIST_BASE_URL;
  const parsedBase = assertSecureUrl(baseUrl, { env });
  const trimmedPath = parsedBase.pathname.replace(/\/+$/, "");
  parsedBase.pathname = `${trimmedPath}/v${version}/${platformArtifact({
    platform,
    arch,
  })}`;
  return parsedBase.toString();
}

function resolveChecksumUrl(binaryUrl) {
  return `${binaryUrl}.sha256`;
}

function getTransport(url) {
  return url.startsWith("https:") ? https : http;
}

const MAX_BINARY_SIZE = 200 * 1024 * 1024; // 200 MB
const MAX_CHECKSUM_SIZE = 1024; // 1 KB

function download(url, destination, { env = process.env, redirectsRemaining = 5, maxSize = MAX_BINARY_SIZE } = {}) {
  const safeUrl = assertSecureUrl(url, { env }).toString();
  const transport = getTransport(safeUrl);

  return new Promise((resolve, reject) => {
    const request = transport.get(safeUrl, (response) => {
      if (
        response.statusCode &&
        response.statusCode >= 300 &&
        response.statusCode < 400 &&
        response.headers.location
      ) {
        if (redirectsRemaining <= 0) {
          reject(new Error(`Too many redirects while downloading ${safeUrl}`));
          return;
        }
        download(response.headers.location, destination, {
          env,
          redirectsRemaining: redirectsRemaining - 1,
          maxSize,
        }).then(resolve, reject);
        return;
      }

      if (response.statusCode !== 200) {
        reject(new Error(`Download failed with status ${response.statusCode}`));
        return;
      }

      let received = 0;
      const file = fs.createWriteStream(destination, { mode: 0o600 });

      response.on("data", (chunk) => {
        received += chunk.length;
        if (received > maxSize) {
          response.destroy();
          file.destroy();
          fs.rmSync(destination, { force: true });
          reject(new Error(`Download exceeded maximum size of ${maxSize} bytes`));
        }
      });

      response.pipe(file);
      file.on("finish", () => {
        file.close(resolve);
      });
      file.on("error", reject);
    });

    request.on("error", reject);
  });
}

function downloadText(url, { env = process.env, redirectsRemaining = 5, maxSize = MAX_CHECKSUM_SIZE } = {}) {
  const safeUrl = assertSecureUrl(url, { env }).toString();
  const transport = getTransport(safeUrl);

  return new Promise((resolve, reject) => {
    const request = transport.get(safeUrl, (response) => {
      if (
        response.statusCode &&
        response.statusCode >= 300 &&
        response.statusCode < 400 &&
        response.headers.location
      ) {
        if (redirectsRemaining <= 0) {
          reject(new Error(`Too many redirects while downloading ${safeUrl}`));
          return;
        }
        downloadText(response.headers.location, {
          env,
          redirectsRemaining: redirectsRemaining - 1,
          maxSize,
        }).then(resolve, reject);
        return;
      }

      if (response.statusCode !== 200) {
        reject(new Error(`Download failed with status ${response.statusCode}`));
        return;
      }

      let body = "";
      let received = 0;
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        received += Buffer.byteLength(chunk, "utf8");
        if (received > maxSize) {
          response.destroy();
          reject(new Error(`Download exceeded maximum size of ${maxSize} bytes`));
          return;
        }
        body += chunk;
      });
      response.on("end", () => resolve(body));
      response.on("error", reject);
    });

    request.on("error", reject);
  });
}

function parseChecksumFile(content, artifactFilename) {
  const trimmed = content.trim();
  if (!trimmed) {
    throw new Error("Checksum file is empty");
  }

  const lines = trimmed.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const patterns = [
    new RegExp(`^([a-fA-F0-9]{64})\\s+\\*?${escapeRegExp(artifactFilename)}$`),
    /^([a-fA-F0-9]{64})$/,
    new RegExp(`^SHA256 \\(${escapeRegExp(artifactFilename)}\\) = ([a-fA-F0-9]{64})$`),
  ];

  for (const line of lines) {
    for (const pattern of patterns) {
      const match = line.match(pattern);
      if (match) {
        return match[1].toLowerCase();
      }
    }
  }

  throw new Error(`Could not parse checksum for ${artifactFilename}`);
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function sha256File(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(fs.readFileSync(filePath));
  return hash.digest("hex");
}

function verifyFileChecksum(filePath, expectedHash) {
  const actualHash = sha256File(filePath);
  if (actualHash !== expectedHash.toLowerCase()) {
    throw new Error(
      `Checksum mismatch for ${path.basename(filePath)}: expected ${expectedHash.toLowerCase()}, got ${actualHash}`
    );
  }
}

async function installBinary({
  version,
  env = process.env,
  binDir = path.join(__dirname, "..", "bin"),
  platform = process.platform,
  arch = process.arch,
  logger = console,
} = {}) {
  if (!version) {
    throw new Error("version is required");
  }

  if (env.QLUENT_SKIP_DOWNLOAD === "1") {
    logger.log("Skipping Qluent CLI binary download");
    return null;
  }

  if (allowInsecureDownload(env)) {
    logger.log(
      "WARNING: QLUENT_CLI_ALLOW_INSECURE_DOWNLOAD is set. " +
        "Binary will be downloaded over insecure HTTP. " +
        "This should ONLY be used for local development."
    );
  }

  const binaryName = platform === "win32" ? "qluent.exe" : "qluent";
  const destination = path.join(binDir, binaryName);
  const tempDestination = `${destination}.tmp`;
  const binaryUrl = resolveDownloadUrl({
    env,
    version,
    platform,
    arch,
  });
  const checksumUrl = resolveChecksumUrl(binaryUrl);

  fs.mkdirSync(binDir, { recursive: true });

  logger.log(`Downloading Qluent CLI from ${binaryUrl}`);
  await download(binaryUrl, tempDestination, { env });

  try {
    const checksumBody = await downloadText(checksumUrl, { env });
    const expectedChecksum = parseChecksumFile(
      checksumBody,
      path.basename(binaryUrl)
    );
    verifyFileChecksum(tempDestination, expectedChecksum);
  } catch (error) {
    fs.rmSync(tempDestination, { force: true });
    throw error;
  }

  fs.renameSync(tempDestination, destination);
  fs.chmodSync(destination, 0o755);
  logger.log(`Installed Qluent CLI to ${destination}`);
  return destination;
}

module.exports = {
  DEFAULT_DIST_BASE_URL,
  MAX_BINARY_SIZE,
  MAX_CHECKSUM_SIZE,
  allowInsecureDownload,
  assertSecureUrl,
  download,
  downloadText,
  installBinary,
  parseChecksumFile,
  platformArtifact,
  resolveChecksumUrl,
  resolveDownloadUrl,
  sha256File,
  verifyFileChecksum,
};
