/** Device fingerprint — must match lib/device_id.py logic on Windows. */
const crypto = require("crypto");
const os = require("os");
const { execSync } = require("child_process");

function run(cmd) {
  try {
    return execSync(cmd, {
      encoding: "utf8",
      timeout: 4000,
      windowsHide: true,
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

function windowsParts() {
  const parts = [];
  // 勿用 powershell：部分客户机上 Get-* 会挂起；reg/wmic 更稳
  const guid = run(
    'reg query "HKLM\\SOFTWARE\\Microsoft\\Cryptography" /v MachineGuid'
  );
  const gm = guid.match(/MachineGuid\s+REG_SZ\s+(\S+)/i);
  if (gm) parts.push(gm[1]);

  const board = run("wmic baseboard get serialnumber");
  for (const line of board.split(/\r?\n/)) {
    const t = line.trim();
    if (t && t.toLowerCase() !== "serialnumber") {
      parts.push(t);
      break;
    }
  }
  const vol = run("wmic logicaldisk where DeviceID='C:' get VolumeSerialNumber");
  for (const line of vol.split(/\r?\n/)) {
    const t = line.trim();
    if (t && t.toLowerCase() !== "volumeserialnumber") {
      parts.push(t);
      break;
    }
  }
  parts.push(os.hostname());
  return parts;
}

function computeDeviceId() {
  const env = process.env.MYKNOWLEDGE_DEVICE_ID;
  if (env && env.trim()) return env.trim().slice(0, 64);
  let parts;
  if (process.platform === "win32") {
    parts = windowsParts();
  } else {
    parts = [os.hostname()];
    try {
      const fs = require("fs");
      if (fs.existsSync("/etc/machine-id")) {
        parts.push(fs.readFileSync("/etc/machine-id", "utf8").trim());
      }
    } catch {
      /* ignore */
    }
  }
  const raw = parts.filter(Boolean).join("|") || os.platform();
  return crypto.createHash("sha256").update(raw, "utf8").digest("hex").slice(0, 32);
}

module.exports = { computeDeviceId };
