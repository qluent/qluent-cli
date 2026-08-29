const pkg = require("./package.json");
const { installBinary } = require("./lib/installer");
const { warnIfShadowed } = require("./lib/shadow-check");

installBinary({ version: pkg.version })
  .then((installedPath) => {
    if (!installedPath || process.env.QLUENT_SKIP_PATH_CHECK === "1") {
      return;
    }
    try {
      warnIfShadowed({ installedPath, installedVersion: pkg.version });
    } catch (error) {
      // Diagnostics only — never fail an otherwise successful install.
      console.error(`Could not verify qluent on PATH: ${error.message}`);
    }
  })
  .catch((error) => {
    console.error(`Failed to install Qluent CLI: ${error.message}`);
    process.exit(1);
  });
