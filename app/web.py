# -*- coding: utf-8 -*-
# ============================================================
# ⚠️ 国内网络适配：必须放在本文件最顶部、所有 import 之前！
# ------------------------------------------------------------
# transformers / huggingface_hub 在被 import 时就会读取这些环境变量来决定
# 用哪个下载源、是否离线。一旦它们被 import，再设就晚了。所以这几行必须是
# 整个程序最早执行的代码——放在 docstring 和所有 import 之前。
#
# 作用：
#   HF_ENDPOINT          -> 下载源换成国内镜像 hf-mirror.com（不用挂梯子）
#   HF_HUB_OFFLINE=1     -> 优先用本地已下载的模型缓存，命中则完全不联网
#   TRANSFORMERS_OFFLINE=1 -> 同上（transformers 侧的离线开关）
#
# 你的 BERT 模型和 BERTopic 的 embedding 模型都已缓存在本地
# （C:\Users\你\.cache\huggingface\hub），所以离线模式可直接命中、秒加载。
#
# 万一以后换了新模型、本地没缓存：把下面 OFFLINE 两行的 "1" 改成 "0"，
# 关梯子跑一次（会走国内镜像下载），下完再改回 "1"。
# ============================================================
import os as _os
_os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
_os.environ["HF_HUB_OFFLINE"] = "1"
_os.environ["TRANSFORMERS_OFFLINE"] = "1"
# ============================================================

"""
app/web.py

网页后端 —— 异步任务版（线程队列 + 进度轮询）

修改时间：
    2026-06-27
----------------------------------
    /api/analyze 从"同步跑完才返回"改为"提交任务立刻返回 task_id"：
      - 真正的分析在后台线程里跑（见 app/task_runner.py），不阻塞请求
      - 前端拿 task_id 轮询 /api/task/<task_id> 获取实时进度
        （正在爬评论 3000 条 / 正在情绪分析 / 正在话题聚类 …）
      - 跑完后轮询结果里 ok=True，前端显示完成、可跳详情页
    其余接口（/api/history、/api/history/<bv>、/api/image/...）不变。
"""

import re
import json
import logging
from pathlib import Path

from flask import Flask, request, jsonify, send_file, abort

# 关键：在 import 任何项目模块（task_runner / pipeline 等）之前，先初始化日志。
# 这些模块在 import 时就会调 get_logger()，谁先触发谁就定下日志配置；
# 所以必须抢在它们之前 setup_logging()，否则后台线程里的 logger.info
# （“开始爬取评论”等）可能因初始化时机不对而打不到终端。
from utils.log_utils import setup_logging, log_event
logger = setup_logging()

# 过滤 werkzeug 的「请求日志」噪音，但保留启动横幅（Running on / Press CTRL+C 等）。
# 不能简单 setLevel(WARNING)——那会把启动横幅也一起压掉。
# 这里用一个过滤器：只丢弃形如  "GET /api/task/... 200"  的逐条请求日志，
# 其它（启动信息、报错）全部放行。
class _DropRequestLog(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # werkzeug 请求日志格式形如：127.0.0.1 - - [..] "GET /xxx HTTP/1.1" 200 -
        # 命中这种就丢弃（返回 False），其余放行
        return not ('"GET ' in msg or '"POST ' in msg or '"HEAD ' in msg)

logging.getLogger("werkzeug").addFilter(_DropRequestLog())

import config.config as cfg
from app.task_runner import (
    submit_task, get_task, get_queue_overview, cancel_task, clear_queue,
)

app = Flask(__name__)

_BV_ID_PATTERN = re.compile(r"^BV[0-9A-Za-z]{10}$")

_DANMU_IMG = {
    "wordcloud": "danmu_wordcloud.png",
    "density":   "danmu_density.png",
    "top_danmu": "top_danmu.png",
}


def _error_response(message: str, status: int = 400):
    return jsonify({"ok": False, "error": message}), status


# ------------------------------------------------------------------ 工具 ----

def _find_history_files():
    root = Path(cfg.ANALYSIS_DIR)
    items = []
    if not root.exists():
        return items
    for hf in root.glob(f"*/*/*/{cfg.HISTORY_FILENAME_SUFFIX}"):
        bv_dir = hf.parent
        items.append((bv_dir.name, bv_dir.parent.parent.name, bv_dir.parent.name, hf))
    return items


def _analysis_bv_dir(bv_id: str):
    m = list(Path(cfg.ANALYSIS_DIR).glob(f"*/*/{bv_id}"))
    return m[0] if m else None


def _processed_danmu_bv_dir(bv_id: str):
    base = Path("data/processed/danmu")
    if not base.exists():
        return None
    m = list(base.glob(f"*/*/{bv_id}"))
    return m[0] if m else None


def _latest_time_dir(parent):
    if parent is None or not parent.exists():
        return None
    subs = [d for d in parent.iterdir() if d.is_dir()]
    return sorted(subs, key=lambda d: d.name)[-1] if subs else None


def _load_json(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _resolve_image_path(bv_id: str, kind: str):
    if kind == "trend":
        bv_dir = _analysis_bv_dir(bv_id)
        if bv_dir:
            p = bv_dir / "trend.png"
            return p if p.exists() else None
        return None
    if kind in _DANMU_IMG:
        latest = _latest_time_dir(_processed_danmu_bv_dir(bv_id))
        if latest:
            p = latest / _DANMU_IMG[kind]
            return p if p.exists() else None
    return None


# ------------------------------------------------------------------ 页面 ----

@app.route("/")
def index():
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bilibili 视频分析</title>
<style>
  body{font-family:-apple-system,"PingFang SC",sans-serif;max-width:760px;margin:32px auto;padding:0 16px;color:#222}
  h2{color:#00a1d6}
  input{width:300px;padding:8px;border:1px solid #ccc;border-radius:6px}
  button{padding:8px 16px;border:0;border-radius:6px;background:#00a1d6;color:#fff;cursor:pointer}
  button:hover{background:#0089b8}
  button:disabled{background:#aaa;cursor:not-allowed}
  /* 进度条 */
  #progress{margin:14px 0;display:none}
  .pbar{height:8px;background:#eee;border-radius:4px;overflow:hidden;margin-top:8px}
  .pbar>i{display:block;height:100%;width:0;background:#00a1d6;transition:width .4s}
  #pmsg{color:#444;font-size:14px}
  #pdone{display:none;margin-top:8px}
  #pdone a{color:#00a1d6}
  .hist-item{display:block;padding:10px 14px;margin:6px 0;background:#fff;border:1px solid #e0e0e0;
             border-radius:8px;text-decoration:none;color:#222;transition:.15s}
  .hist-item:hover{border-color:#00a1d6;box-shadow:0 1px 6px rgba(0,161,214,.15)}
  .hist-item .t{font-weight:600}
  .hist-item .m{color:#888;font-size:12px;margin-top:2px}
</style>
</head>
<body>
  <h2>🎬 Bilibili 视频分析</h2>
  <input id="bvInput" placeholder="输入 BV 号">
  <button id="goBtn" onclick="submitTask()">开始分析</button>

  <div id="progress">
    <div id="pmsg">排队中…</div>
    <div class="pbar"><i id="pfill"></i></div>
    <div id="pdone"></div>
  </div>

  <div id="queuePanel" style="margin-top:20px;display:none">
    <h3 style="margin-bottom:8px;color:#555;font-size:15px">📋 当前队列</h3>
    <div id="queueBox"></div>
  </div>

  <h2 style="margin-top:32px">历史记录</h2>
  <button onclick="loadHistory()">刷新历史</button>
  <div id="history" style="margin-top:12px"></div>

<script>
// 阶段 -> 进度条百分比（粗略，给用户一个推进感）
const STAGE_PCT = {
  queued:5, crawl_comments:25, crawl_danmu:45, visualize:55,
  sentiment:75, analysis:90, done:100, error:100
};
let pollTimer = null;

async function submitTask(){
  const bvId = document.getElementById('bvInput').value.trim();
  const btn = document.getElementById('goBtn');
  const prog = document.getElementById('progress');
  const pmsg = document.getElementById('pmsg');
  const pfill = document.getElementById('pfill');
  const pdone = document.getElementById('pdone');

  prog.style.display='block'; pdone.style.display='none';
  pmsg.textContent='提交中…'; pfill.style.width='5%'; pfill.style.background='#00a1d6';
  btn.disabled=true;   // 提交请求期间短暂禁用，防止狂点重复提交

  let res, data;
  try{
    res = await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({bv_id:bvId})});
    data = await res.json();
  }catch(e){ pmsg.textContent='请求失败：'+e; btn.disabled=false; return; }

  // 不管成功失败，请求一返回就立刻解禁按钮：
  // 任务是进队列异步跑的，提交完就该能继续提交下一个（排队），
  // 不能等当前任务跑完才解禁（否则任务运行时按钮一直灰着，加不了新任务）。
  btn.disabled=false;

  if(!res.ok){ pmsg.textContent='出错了：'+data.error; return; }

  const taskId = data.task_id;
  // 清空输入框，方便接着输入下一个 BV 号继续排队
  document.getElementById('bvInput').value='';
  // 开始轮询进度
  if(pollTimer) clearInterval(pollTimer);
  // 每 2 秒轮询一次进度。（终端的请求日志噪音已由 web.py 顶部的日志过滤器
  // 屏蔽，所以这里可以用较短间隔，让进度/阶段切换及时反映到界面上。）
  pollProgress(taskId);                                       // 先立刻查一次，不用干等
  pollTimer = setInterval(()=>pollProgress(taskId), 2000);
}

async function pollProgress(taskId){
  const pmsg=document.getElementById('pmsg'), pfill=document.getElementById('pfill'),
        pdone=document.getElementById('pdone'), btn=document.getElementById('goBtn');
  let res, t;
  try{ res=await fetch('/api/task/'+taskId); t=await res.json(); }
  catch(e){ return; }
  if(!t.ok_request){ return; }
  const task=t.task;

  // 排队中：显示前面还有几个任务
  if(task.stage === 'queued'){
    const ahead = task.ahead || 0;
    pmsg.textContent = ahead > 0
      ? `排队中…前面还有 ${ahead} 个任务`
      : '排队中…即将开始';
  }else{
    pmsg.textContent = task.stage_text || '处理中…';
  }
  pfill.style.width = (STAGE_PCT[task.stage]||10) + '%';

  loadQueue();   // 顺便刷新队列概览面板

  if(task.ok === true){           // 成功
    clearInterval(pollTimer); btn.disabled=false;
    pfill.style.width='100%';
    pdone.style.display='block';
    pdone.innerHTML = `✅ 完成！<a href="/video/${task.bv_id}">点击查看详情 →</a>`;
    loadHistory();
  }else if(task.ok === false){    // 失败
    clearInterval(pollTimer); btn.disabled=false;
    pfill.style.background='#f08080'; pfill.style.width='100%';
    pmsg.textContent = '❌ ' + (task.error || '分析失败');
  }
}

async function loadQueue(){
  const panel=document.getElementById('queuePanel'), box=document.getElementById('queueBox');
  let data;
  try{ data=await (await fetch('/api/queue')).json(); }catch(e){ return; }
  const running=data.running, waiting=data.waiting||[];
  // 队列空（没在跑、没排队）就隐藏整个面板，不占地方
  if(!running && waiting.length===0){ panel.style.display='none'; return; }
  panel.style.display='block';
  let html='';
  if(running){
    html += `<div style="padding:8px 12px;background:#e8f7fd;border-left:3px solid #00a1d6;border-radius:6px;margin-bottom:6px;font-size:13px">
      🔄 <b>正在处理</b>：${running.bv_id} —— ${running.stage_text}</div>`;
  }
  waiting.forEach((w,i)=>{
    // 每条排队项末尾加一个 × 按钮，点击可单独移除该排队任务
    html += `<div style="display:flex;align-items:center;justify-content:space-between;
        padding:6px 12px;background:#f7f7f7;border-radius:6px;margin-bottom:4px;font-size:13px;color:#666">
      <span>⏳ 排队第 ${i+1} 位：${w.bv_id}</span>
      <span onclick="cancelOne('${w.task_id}')" title="移除该排队任务"
            style="cursor:pointer;color:#f08080;font-weight:bold;padding:0 6px;font-size:16px">×</span>
    </div>`;
  });
  // 有排队任务时，显示"清空队列"按钮（只清排队中的，正在跑的不动）
  if(waiting.length>0){
    html += `<button onclick="clearQueue()"
        style="margin-top:6px;padding:5px 12px;font-size:12px;background:#f08080">清空队列（${waiting.length} 个排队任务）</button>`;
  }
  box.innerHTML=html;
}

// 移除单个排队任务
async function cancelOne(taskId){
  try{
    await fetch('/api/task/'+taskId+'/cancel', {method:'POST'});
  }catch(e){}
  loadQueue();   // 立刻刷新面板
}

// 清空队列（仅排队中的任务）
async function clearQueue(){
  if(!confirm('确定清空所有排队中的任务吗？（正在处理的任务会继续跑完）')) return;
  try{
    await fetch('/api/queue/clear', {method:'POST'});
  }catch(e){}
  loadQueue();
}

async function loadHistory(){
  const res=await fetch('/api/history'); const data=await res.json();
  const box=document.getElementById('history');
  if(!data.items||!data.items.length){box.innerHTML='<p style="color:#888">暂无历史记录</p>';return;}
  box.innerHTML=data.items.map(it=>
    `<a class="hist-item" href="/video/${it.bv_id}">
       <div class="t">${it.title}</div>
       <div class="m">${it.uname} · ${it.bv_id} · 共 ${it.point_count} 次抓取</div></a>`).join('');
}
loadHistory();
loadQueue();
// 队列面板独立定时刷新：不依赖某个具体任务的轮询。
// 这样即使刷新了页面（任务轮询循环会丢失），只要后台还有任务在跑，
// 队列面板也会每 2 秒自己更新一次，不会"卡住要手动刷新"。
setInterval(loadQueue, 2000);
</script>
</body>
</html>
"""


@app.route("/video/<bv_id>")
def video_detail_page(bv_id):
    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>视频详情</title>
<style>
  body{font-family:-apple-system,"PingFang SC",sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#222}
  a.back{color:#00a1d6;text-decoration:none}
  h2{color:#00a1d6;margin-bottom:4px}
  .meta{color:#888;font-size:13px;margin-bottom:20px}
  .card{background:#fff;border:1px solid #e8e8e8;border-radius:10px;padding:16px 20px;margin:14px 0}
  .card h3{margin:0 0 12px;font-size:15px}
  .senti span{display:inline-block;padding:4px 12px;border-radius:14px;margin-right:8px;font-size:13px;color:#fff}
  .pos{background:#5ab4ac}.neu{background:#d8b365}.neg{background:#f08080}
  .warn{padding:8px 12px;border-radius:6px;margin:6px 0;font-size:13px}
  .warn.warning{background:#fff3f3;border-left:3px solid #f08080}
  .warn.info{background:#f0f8ff;border-left:3px solid #5b9bd5}
  .topic{border-bottom:1px dashed #eee;padding:8px 0}
  .topic .kw{color:#00a1d6}
  img.fig{max-width:100%;border:1px solid #eee;border-radius:8px;display:block;margin-top:8px}
  table{border-collapse:collapse;width:100%;font-size:13px}
  td,th{border:1px solid #eee;padding:6px 8px;text-align:center}
  .empty{color:#aaa;font-size:13px}
</style>
</head>
<body>
  <a class="back" href="/">← 返回列表</a>
  <div id="content" style="margin-top:16px">加载中...</div>
<script>
const bvId=location.pathname.split('/').pop();
function sentiHtml(s){if(!s)return '<span class="empty">无情绪数据</span>';
  const p=s['正向']||0,n=s['中性']||0,g=s['负向']||0;
  return `<div class="senti"><span class="pos">正向 ${p}</span><span class="neu">中性 ${n}</span><span class="neg">负向 ${g}</span></div>`;}
function warnHtml(ws){if(!ws||!ws.length)return '<p class="empty">未检测到预警</p>';
  return ws.map(w=>`<div class="warn ${w.level}">${w.message}</div>`).join('');}
function topicHtml(tr){if(!tr||!tr.topics||!tr.topics.length)return '<p class="empty">无话题数据（评论太少或未启用 BERTopic）</p>';
  return tr.topics.map(t=>`<div class="topic"><span class="kw">${(t.keywords||[]).slice(0,8).join(' / ')}</span><span style="color:#888">（${t.size} 条）</span></div>`).join('');}
function historyTable(records){if(!records||!records.length)return '<p class="empty">无历史记录</p>';
  const rows=records.map(r=>{const st=r.stat||{};
    return `<tr><td>${r.crawl_time}</td><td>${st.view||0}</td><td>${st.like||0}</td><td>${st.coin||0}</td><td>${st.favorite||0}</td><td>${st.reply||0}</td></tr>`;}).join('');
  return `<table><tr><th>抓取时间</th><th>播放</th><th>点赞</th><th>投币</th><th>收藏</th><th>评论</th></tr>${rows}</table>`;}
function figHtml(kind,label){return `<img class="fig" src="/api/image/${bvId}/${kind}" alt="${label}" onerror="this.outerHTML='<p class=&quot;empty&quot;>暂无${label}</p>'">`;}
async function load(){
  const res=await fetch('/api/history/'+bvId); const data=await res.json();
  const box=document.getElementById('content');
  if(!res.ok){box.innerHTML='<p>出错了：'+data.error+'</p>';return;}
  const h=data.history||{}; const records=h.records||[]; const latest=records.length?records[records.length-1]:{};
  box.innerHTML=`
    <h2>${h.title||bvId}</h2>
    <div class="meta">${h.uname||''} · ${bvId} · 共 ${records.length} 次抓取</div>
    <div class="card"><h3>😊 最近一次情绪分布</h3>${sentiHtml(latest.sentiment_summary)}</div>
    <div class="card"><h3>📈 数据趋势</h3>${figHtml('trend','数据趋势图')}</div>
    <div class="card"><h3>☁️ 弹幕词云</h3>${figHtml('wordcloud','弹幕词云')}</div>
    <div class="card"><h3>📊 弹幕时间轴密度</h3>${figHtml('density','时间轴密度图')}</div>
    <div class="card"><h3>🔥 高频弹幕词条</h3>${figHtml('top_danmu','高频弹幕图')}</div>
    <div class="card"><h3>⚠️ 舆情预警</h3>${warnHtml(data.warnings)}</div>
    <div class="card"><h3>🏷️ 话题聚类</h3>${topicHtml(data.topic_result)}</div>
    <div class="card"><h3>📋 抓取历史</h3>${historyTable(records)}</div>`;
}
load();
</script>
</body>
</html>
"""


# ------------------------------------------------------------------ API -----

@app.route("/api/analyze", methods=["POST"])
def analyze():
    """提交分析任务，立刻返回 task_id（不阻塞）"""
    body = request.get_json(silent=True) or {}
    bv_id = (body.get("bv_id") or "").strip()
    if not bv_id:
        return _error_response("请输入视频 BV 号")
    if not _BV_ID_PATTERN.match(bv_id):
        return _error_response(f"BV 号格式不正确: {bv_id}")

    task_id = submit_task(bv_id)
    log_event("web_analyze_request", bv_id=bv_id, task_id=task_id)
    return jsonify({"ok": True, "task_id": task_id})


@app.route("/api/task/<task_id>")
def task_status(task_id: str):
    """查询任务进度（前端轮询）"""
    t = get_task(task_id)
    if t is None:
        return jsonify({"ok_request": False, "error": "任务不存在或已过期"}), 404
    return jsonify({"ok_request": True, "task": t})


@app.route("/api/queue")
def queue_overview():
    """队列概览：当前正在跑哪个任务、还有几个在排队（前端显示用）"""
    return jsonify({"ok": True, **get_queue_overview()})


@app.route("/api/task/<task_id>/cancel", methods=["POST"])
def task_cancel(task_id: str):
    """取消一个排队中的任务（正在跑的不能取消）"""
    result = cancel_task(task_id)
    status = 200 if result.get("ok") else 400
    return jsonify(result), status


@app.route("/api/queue/clear", methods=["POST"])
def queue_clear():
    """清空队列：取消所有排队中的任务，正在跑的不动"""
    return jsonify(clear_queue())


@app.route("/api/history")
def history_list():
    items = []
    for bv_id, uname, title, hf in _find_history_files():
        history = _load_json(hf) or {}
        items.append({"bv_id": bv_id, "uname": uname, "title": title,
                      "point_count": len(history.get("records", [])),
                      "history_path": str(hf)})
    items.sort(key=lambda x: x["point_count"], reverse=True)
    return jsonify({"ok": True, "items": items})


@app.route("/api/history/<bv_id>")
def history_detail(bv_id: str):
    matches = list(Path(cfg.ANALYSIS_DIR).glob(f"*/*/{bv_id}/{cfg.HISTORY_FILENAME_SUFFIX}"))
    if not matches:
        return _error_response(f"未找到该视频的历史记录: {bv_id}", status=404)
    history_file = matches[0]
    bv_dir = history_file.parent
    history = _load_json(history_file) or {}

    warnings = []
    latest_dir = _latest_time_dir(bv_dir)
    if latest_dir:
        w = _load_json(latest_dir / "warnings.json")
        if w:
            warnings = w.get("warnings", [])

    topic_result = None
    if Path(cfg.TOPIC_DIR).exists():
        tms = sorted(Path(cfg.TOPIC_DIR).glob(f"*/*/{bv_id}/*/topics.json"),
                     key=lambda p: p.parent.name)
        if tms:
            topic_result = _load_json(tms[-1])

    return jsonify({"ok": True, "history": history,
                    "warnings": warnings, "topic_result": topic_result})


@app.route("/api/image/<bv_id>/<kind>")
def get_image(bv_id: str, kind: str):
    if not _BV_ID_PATTERN.match(bv_id):
        abort(404)
    if kind not in ({"trend"} | set(_DANMU_IMG.keys())):
        abort(404)
    path = _resolve_image_path(bv_id, kind)
    if path is None or not path.exists():
        abort(404)
    return send_file(path.resolve(), mimetype="image/png")


if __name__ == "__main__":
    # 注意：debug=True 的自动重载会重启进程，导致正在跑的后台任务中断。
    # 正式使用时建议 debug=False；调试期间知道这点即可。
    app.run(debug=False, host="127.0.0.1", port=5000)