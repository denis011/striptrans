// NOTICE za javnu verziju: licence npm paketa koje frontend koristi u radu (bez razvojnih).
// Radi u `frontend` kontejneru: node /repo/scripts/notice-frontend.cjs > frontend.md
const { execSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const tree = JSON.parse(execSync("npm ls --omit=dev --all --json", { encoding: "utf8", maxBuffer: 64 << 20 }));
const found = new Map();
(function walk(deps) {
  for (const [name, info] of Object.entries(deps || {})) {
    if (!info.version) continue; // neobavezan paket koji nije instaliran (npr. skia-canvas za konvu)
    if (!found.has(name)) {
      const file = path.join("node_modules", name, "package.json");
      const pkg = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, "utf8")) : {};
      const license = typeof pkg.license === "string" ? pkg.license : (pkg.license && pkg.license.type) || "?";
      found.set(name, { version: info.version, license });
    }
    walk(info.dependencies);
  }
})(tree.dependencies);
const bad = [...found].filter(([, v]) => /\bA?GPL/i.test(v.license) && !/LGPL/i.test(v.license));
if (bad.length) {
  console.error("GPL/AGPL paketi:", bad.map(([n, v]) => `${n}: ${v.license}`).join(", "));
  process.exit(1);
}
console.log("## npm paketi (frontend)\n\n| Paket | Verzija | Licenca |\n|---|---|---|");
for (const [name, v] of [...found].sort(([a], [b]) => a.localeCompare(b))) console.log(`| ${name} | ${v.version} | ${v.license} |`);
