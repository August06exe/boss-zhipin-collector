const params = new URLSearchParams(location.search);
let TOKEN = params.get("t") || sessionStorage.getItem("boss_token") || "";
// 令牌存 sessionStorage：同标签刷新不丢；从地址栏抹掉，降低误复制链接泄露面；关标签自动失效
if (TOKEN) {
  sessionStorage.setItem("boss_token", TOKEN);
  if (history.replaceState) history.replaceState(null, "", location.pathname);
}

// 会话失效兜底：清掉旧令牌，盖一层明确的提示页，不再让半残界面迷惑用户
let sessionDead = false;
function killSession() {
  if (sessionDead) return;
  sessionDead = true;
  sessionStorage.removeItem("boss_token");
  const el = document.getElementById("session-dead");
  if (el) el.hidden = false;
}

const api = (path, opts = {}) => fetch(path + (path.includes("?") ? "&" : "?") + "t=" + TOKEN, {
  headers: {"X-Token": TOKEN, "Content-Type": "application/json"},
  ...opts,
}).then(r => {
  if (r.status === 401) { killSession(); throw new Error("会话已失效，请重新打开"); }
  return r.json();
});

const $ = id => document.getElementById(id);
let ALL_CITIES = [];

// 简短日志 / 完整日志切换
$("log-toggle").onclick = () => {
  const full = $("logs-full");
  full.hidden = !full.hidden;
  $("logs").hidden = !full.hidden;
  $("log-toggle").textContent = full.hidden ? "展开完整日志" : "收起日志";
};

function fillSelect(id, options, current) {
  const el = $(id);
  el.innerHTML = "";
  options.forEach(o => {
    const opt = document.createElement("option");
    opt.textContent = o;
    el.appendChild(opt);
  });
  el.value = options.includes(current) ? current : "不限";
}

const FILTER_OPTIONS = {
  salary: ["不限", "3K以下", "3-5K", "5-10K", "10-20K", "20-50K", "50K以上"],
  experience: ["不限", "在校生", "应届生", "经验不限", "1年内", "1-3年", "3-5年", "5-10年", "10年以上"],
  degree: ["不限", "初中及以下", "中专/中技", "高中", "大专", "本科", "硕士", "博士"],
  scale: ["不限", "0-20人", "20-99人", "100-499人", "500-999人", "1000-9999人", "10000人以上"],
};

// ---- 城市选择器：热门标签 + 搜索 ----
function selectCity(name) {
  $("city-search").value = name;
  $("city-tag").textContent = name;
  $("city-selected").hidden = false;
  $("city-list").hidden = true;
}

function clearCity() {
  $("city-search").value = "";
  $("city-selected").hidden = true;
  $("city-tag").textContent = "";
}

function renderCityList(filter) {
  const box = $("city-list");
  const kw = (filter || "").trim();
  const matches = ALL_CITIES.filter(c => !kw || c.includes(kw)).slice(0, 40);
  box.innerHTML = "";
  if (!matches.length) {
    box.hidden = false;
    box.innerHTML = '<div class="city-item muted">没有找到这个城市</div>';
    return;
  }
  matches.forEach(c => {
    const item = document.createElement("div");
    item.className = "city-item";
    item.textContent = c;
    item.onclick = () => { selectCity(c); box.hidden = true; };
    box.appendChild(item);
  });
  box.hidden = false;
}

async function initCities() {
  try {
    const data = await api("/api/cities");
    ALL_CITIES = data.cities || [];
    (data.hot || []).forEach(c => {
      const chip = document.createElement("button");
      chip.className = "chip";
      chip.textContent = c;
      chip.onclick = () => selectCity(c);
      $("hot-cities").appendChild(chip);
    });
  } catch (e) { /* 城市列表加载失败不阻塞页面 */ }
}

// ---- 表单回填与收集 ----
async function initForm() {
  try {
    const v = await api("/api/settings");
    $("keyword").value = v.keyword || "";
    $("target-count").value = v.target_count || 300;
    $("max-minutes").value = v.max_minutes || 300;
    $("data-dir").value = v.data_dir || "";
    if (v.city) selectCity(v.city); else clearCity();
    Object.keys(FILTER_OPTIONS).forEach(k => fillSelect(k, FILTER_OPTIONS[k], v[k]));
    const fields = await api("/api/fields");
    const box = $("fields-box");
    box.innerHTML = "";
    fields.forEach(f => {
      const label = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox";
      cb.value = f.key;
      cb.checked = !v.fields || v.fields.length === 0 || v.fields.includes(f.key);
      label.appendChild(cb);
      label.appendChild(document.createTextNode(" " + f.csv));
      box.appendChild(label);
    });
  } catch (e) {
    $("form-error").textContent = e.message;
  }
}

function collectForm() {
  const fields = [...document.querySelectorAll("#fields-box input:checked")].map(x => x.value);
  return {
    keyword: $("keyword").value.trim(),
    city: $("city-tag").textContent || $("city-search").value.trim(),
    salary: $("salary").value, experience: $("experience").value,
    degree: $("degree").value, scale: $("scale").value,
    target_count: Number($("target-count").value),
    max_minutes: Number($("max-minutes").value), fields,
    data_dir: $("data-dir").value,
  };
}

function scopePreview() {
  const target = Number($("target-count").value);
  const minutes = Number($("max-minutes").value);
  const el = $("scope-preview");
  if (!target || !minutes) { el.textContent = ""; return; }
  el.textContent = `本次目标 ${target} 条（约 ${Math.ceil(target / 30)} 页）；超过 ${minutes} 分钟自动停，先到先停；抓到的部分都会保存。`;
}

const STATE_NAMES = {idle: "待机", checking: "检查中", login_required: "待登录",
  ready: "就绪", running: "采集中", stopping: "停止中", stopped: "已结束", error: "出现问题"};

async function poll() {
  if (sessionDead) return;
  try {
    const st = await api("/api/state");
    // 单页布局：登录/浏览器缺失接管内容区，其余状态表单常驻、运行区块按需显示
    $("browser-missing").hidden = !st.browser_missing;
    $("screen-form").hidden = st.browser_missing || st.state === "login_required";
    $("screen-login").hidden = st.state !== "login_required";
    const loginStatus = $("login-status");
    if (st.state === "login_required") {
      const last = (st.logs || []).slice(-1)[0] || "";
      loginStatus.textContent = last;
      loginStatus.hidden = !last;
    } else {
      loginStatus.hidden = true;
    }
    const runVisible = ["running", "stopping", "stopped"].includes(st.state) || !!st.task;
    $("screen-run").hidden = !runVisible;
    $("state-badge").textContent = STATE_NAMES[st.state] || st.state;
    $("state-badge").dataset.state = st.state;
    const cur = st.current;
    $("run-current").textContent = cur
      ? `关键词「${cur.keyword}」 · 城市「${cur.city}」`
      : "-";
    const total = st.stats.total || 0;
    const target = st.target_count || 0;
    $("run-total").textContent = total;
    $("run-new").textContent = st.stats.new || 0;
    $("run-target").textContent = target || "-";
    $("run-round").textContent = (st.rounds || []).length;
    const pct = target ? Math.min(100, Math.round((total / target) * 100)) : 0;
    $("run-progress-fill").style.width = pct + "%";
    $("run-progress-pct").textContent = pct + "%";
    // 详情阶段：列表抓完只是拿到岗位清单，职位描述要一条条抓（10-25 秒/条）
    const det = st.details;
    const detBox = $("run-details");
    if (det && det.done < det.total) {
      detBox.textContent = `职位描述抓取中 ${det.done}/${det.total}（每条间隔 10-25 秒防风控；这一步完成前「职位描述」列是空的，属正常现象）`;
      detBox.hidden = false;
    } else if (det && det.done >= det.total) {
      detBox.textContent = `职位描述已抓完 ${det.done}/${det.total}`;
      detBox.hidden = false;
    } else {
      detBox.hidden = true;
    }
    const KEY = /✓|轮|完成|保存|已登录|未登录|限制|❌|内部|数据|拉起|浏览器|检测|目标|最长|\[\d+\/\d+\]/;
    const all = (st.logs || []);
    const fill = (el, lines) => {
      el.textContent = "";
      for (const line of lines) {
        const div = document.createElement("div");
        div.textContent = line;
        el.appendChild(div);
      }
    };
    fill($("logs"), all.filter(x => KEY.test(x)).slice(-8));
    fill($("logs-full"), all.slice(-300));
    $("run-done").textContent = (st.state === "stopped" && st.task)
      ? `已结束：共 ${st.stats.total} 条，文件在 ${st.task_dir}` : "";
    // 新一轮开始时把运行区块滚进视野，用户不用自己找
    if (["running", "stopping"].includes(st.state) && poll.lastState !== "running"
        && poll.lastState !== "stopping" && runVisible) {
      $("screen-run").scrollIntoView({behavior: "smooth", block: "start"});
    }
    poll.lastState = st.state;
  } catch (e) {
    $("state-badge").textContent = e.message;
  }
}

$("start").onclick = async () => {
  const form = collectForm();
  // 必填拦截在前端先做，不用等后端报错
  if (!form.keyword) {
    $("form-error").textContent = "请先填写关键词（如：AI Agent、运营、会计）";
    $("keyword").focus();
    return;
  }
  if (!form.city) {
    $("form-error").textContent = "请先选城市：点上面的热门城市，或在搜索框输入后选择";
    $("city-search").focus();
    return;
  }
  const res = await api("/api/start", {method: "POST", body: JSON.stringify(form)});
  if (res.error) { $("form-error").textContent = res.error; return; }
  await api("/api/settings", {method: "POST", body: JSON.stringify(form)});
  $("form-error").textContent = "";
  poll();
};
$("stop").onclick = () => api("/api/stop", {method: "POST"});
$("open-browser").onclick = () => api("/api/login/start-browser", {method: "POST"});
$("login-done").onclick = async () => {
  const res = await api("/api/login/verify", {method: "POST"});
  if (!res.ok) $("login-error").textContent = "还没检测到登录，请在弹出的浏览器里完成登录后重试";
};
$("choose-dir").onclick = async () => {
  const res = await api("/api/choose-dir", {method: "POST"});
  if (res.path) $("data-dir").value = res.path;
};
$("cleanup-browser").onclick = () => api("/api/browser/cleanup", {method: "POST"});

$("city-search").addEventListener("input", e => renderCityList(e.target.value));
$("city-search").addEventListener("focus", () => renderCityList($("city-search").value));
$("clear-city").onclick = clearCity;
initCities().then(async () => {
  await initForm();
  scopePreview();
});
["target-count", "max-minutes"].forEach(id => {
  $(id).addEventListener("input", scopePreview);
});
setInterval(poll, 2000);
