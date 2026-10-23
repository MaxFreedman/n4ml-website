import { createHash } from "node:crypto";
import { createReadStream } from "node:fs";
import { mkdir, readFile, readdir, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { resolve, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const root = fileURLToPath(new URL("../", import.meta.url));
const dist = resolve(root, "dist");
const output = resolve(root, "release");
const commit = execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
await mkdir(output, { recursive: true });
await writeFile(resolve(dist, "release.json"), JSON.stringify({ commit, builtAt: new Date().toISOString() }) + "\n");

async function files(folder) {
  const entries = await readdir(folder, { withFileTypes: true });
  const paths = [];
  for (const entry of entries) {
    const path = resolve(folder, entry.name);
    if (entry.isDirectory()) paths.push(...await files(path));
    else if (entry.isFile()) paths.push(path);
    else throw new Error(`Unexpected non-file in build: ${path}`);
  }
  return paths.sort();
}

async function sha256(path) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(path)) hash.update(chunk);
  return hash.digest("hex");
}

for (const path of await files(dist)) {
  if (/\.(html|css|js|json|svg)$/.test(path)) {
    const original = await readFile(path);
    const compressed = gzipSync(original, { level: 9 });
    if (compressed.length < original.length) await writeFile(path + ".gz", compressed);
  }
}
const inventory = (await files(dist)).filter(path => !path.endsWith("/checksums.sha256"));
const checksums = [];
for (const path of inventory) checksums.push(`${await sha256(path)}  ${relative(dist, path)}`);
await writeFile(resolve(dist, "checksums.sha256"), checksums.join("\n") + "\n");

const tarEnv = { ...process.env, COPYFILE_DISABLE: "1", GZIP: "-1" };
execFileSync("tar", ["-czf", resolve(output, "n4ml-vps.tar.gz"), "-C", dist, "."], { env: tarEnv });
execFileSync("tar", ["-czf", resolve(output, "n4ml-deploy-tools.tar.gz"), "-C", root, "deploy", "DEPLOY.md"], { env: tarEnv });
const archives = ["n4ml-vps.tar.gz", "n4ml-deploy-tools.tar.gz"];
const archiveChecksums = [];
for (const name of archives) archiveChecksums.push(`${await sha256(resolve(output, name))}  ${name}`);
await writeFile(resolve(output, "SHA256SUMS"), archiveChecksums.join("\n") + "\n");
console.log(`Packaged ${inventory.length} files for ${commit}. Output: release/`);
