// 用 CDP 驱动 headless Chrome，真在 ComfyUI 前端里 loadGraphData 一遍，
// 确认工作流文件能被画布吃下（而不是只看 JSON 结构）。
// 用法：node check-workflow-load.mjs <chrome.ws.url> <workflow 文件名>
//
// 注意：需要能直连本机 websocket。当前开发机的透明代理会截走到 127.0.0.1:9xxx 的
// WS 握手（报 non-101），所以这个脚本在本机跑不通，留作其他环境用。
const [, , wsUrl, name = "see-through.ui.json"] = process.argv;
if (!wsUrl) {
  console.error("需要 CDP 的 page websocket url");
  process.exit(2);
}

const expr = `(async () => {
  const url = "/api/userdata/workflows%2F" + encodeURIComponent(${JSON.stringify(name)});
  const r = await fetch(url);
  if (!r.ok) return "FETCH_FAIL:" + r.status;
  const d = await r.json();
  const app = window.app || (window.comfyAPI && window.comfyAPI.app && window.comfyAPI.app.app);
  if (!app) return "NO_APP";
  try {
    await app.loadGraphData(d);
  } catch (e) {
    return "ERR:" + (e && e.message ? e.message : String(e));
  }
  const g = app.graph;
  const missing = (g._nodes || []).filter(n => n.type && String(n.type).includes("SeeThrough"));
  return "OK nodes=" + (g._nodes || []).length + " links=" + (g.links ? Object.keys(g.links).length : "?") +
         " seethrough=" + missing.length;
})()`;

const ws = new WebSocket(wsUrl);
let id = 0;
const pending = new Map();

function send(method, params = {}) {
  const mid = ++id;
  ws.send(JSON.stringify({ id: mid, method, params }));
  return new Promise((res) => pending.set(mid, res));
}

ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    pending.get(msg.id)(msg);
    pending.delete(msg.id);
  }
};

ws.onopen = async () => {
  await send("Runtime.enable");
  const r = await send("Runtime.evaluate", {
    expression: expr,
    awaitPromise: true,
    returnByValue: true,
  });
  const v = r.result && r.result.result;
  console.log(JSON.stringify(v && v.value !== undefined ? v.value : r));
  ws.close();
  process.exit(0);
};

setTimeout(() => {
  console.log("TIMEOUT");
  process.exit(1);
}, 60000);
