const pkg = require("./package.json");
const { installBinary } = require("./lib/installer");

installBinary({ version: pkg.version }).catch((error) => {
  console.error(`Failed to install Qluent CLI: ${error.message}`);
  process.exit(1);
});
