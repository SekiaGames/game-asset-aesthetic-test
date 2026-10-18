// 无头渲染 Spine 骨骼（官方 spine-webgl 4.2 + playwright-core 驱动本机 Edge），逐帧输出 PNG。
// 用法：node scripts/spine-render.mjs <job.json> <输出目录>
// job.json 里 skel / atlas 是相对 --root（默认仓库的 projects/ 目录）的路径；格式见 spine-render.html 的 renderJob 注释。
// 连续帧（frames>1）会推进 AnimationState 与 Spine 4.2 物理约束；之后可用 ffmpeg 拼成视频。
import fs from "node:fs";
import path from "node:path";
import http from "node:http";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const rootIdx = args.indexOf("--root");
const root = rootIdx >= 0 ? path.resolve(args.splice(rootIdx, 2)[1]) : path.resolve(here, "..");
const [jobPath, outDir] = args;
const job = JSON.parse(fs.readFileSync(jobPath, "utf8"));
const EDGE = process.env.SPINE_RENDER_BROWSER || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

const types = { ".html": "text/html", ".js": "text/javascript", ".json": "application/json", ".png": "image/png", ".atlas": "text/plain" };
const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split("?")[0]);
  let file;
  if (url === "/") file = path.join(here, "spine-render.html");
  else if (url.startsWith("/__spine/")) file = path.join(here, "../node_modules/@esotericsoftware/spine-webgl/dist/iife", url.slice(9));
  else file = path.join(root, url);
  if (!path.resolve(file).startsWith(path.resolve(root)) && !url.startsWith("/__spine/") && url !== "/") { res.writeHead(403); return res.end(); }
  fs.readFile(file, (err, buf) => {
    if (err) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "Content-Type": types[path.extname(file)] || "application/octet-stream" });
    res.end(buf);
  });
}).listen(0);
const port = server.address().port;

const browser = await chromium.launch({ executablePath: EDGE, headless: true, args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
try {
  const page = await browser.newPage();
  page.on("console", (m) => { if (m.type() === "error") console.error("[page]", m.text()); });
  page.on("pageerror", (e) => console.error("[page]", e.message));
  await page.goto(`http://127.0.0.1:${port}/`);
  await page.waitForFunction(() => window.ready);
  const rel = (p) => "/" + p.replace(/\\/g, "/");
  if (job.list) {
    console.log((await page.evaluate(([s, a]) => window.listAnimations(s, a), [rel(job.skel), rel(job.atlas)])).join("\n"));
  } else {
    fs.mkdirSync(outDir, { recursive: true });
    // 分批渲染，避免一次返回太多 dataURL
    const meta = [];
    for (const shot of job.shots) {
      const [r] = await page.evaluate((j) => window.renderJob(j), { ...job, skel: rel(job.skel), atlas: rel(job.atlas), shots: [shot] });
      const dir = r.frames.length > 1 ? path.join(outDir, r.name) : outDir;
      fs.mkdirSync(dir, { recursive: true });
      r.frames.forEach((d, i) => {
        const f = r.frames.length > 1 ? path.join(dir, `f${String(i).padStart(4, "0")}.png`) : path.join(dir, `${r.name}.png`);
        fs.writeFileSync(f, Buffer.from(d.split(",")[1], "base64"));
      });
      meta.push({ name: r.name, frames: r.frames.length, cam: r.cam });
      console.log(`${r.name}: ${r.frames.length} 帧`);
    }
    fs.writeFileSync(path.join(outDir, "render_meta.json"), JSON.stringify(meta, null, 1));
  }
} finally {
  await browser.close();
  server.close();
}
