"""PDF 집중 분석 + 벤치마크 도구

PyMuPDF로 페이지를 이미지로 렌더링하고, 파서 버전별 출력을 비교하는
HTML 리포트를 생성한다. 벤치마크 스코어링(ground truth 대비 recall)과
버전 간 JSON diff를 함께 제공한다.

Usage:
    python tools/inspect_pdf.py upload/24타경285_1.pdf
    python tools/inspect_pdf.py upload/                          # 배치
    python tools/inspect_pdf.py upload/24타경285_1.pdf --no-benchmark
    python tools/inspect_pdf.py upload/ --save                   # 히스토리 저장
    python tools/inspect_pdf.py file.pdf -p v1.0.0,v1.0.1 --dpi 150
"""
import argparse
import base64
import glob
import json
import os
import sys
from datetime import datetime
from pathlib import Path

_BACKEND_ROOT = str(Path(__file__).resolve().parent.parent)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
os.chdir(_BACKEND_ROOT)

import fitz  # pymupdf
from parsers import get_parser, list_versions
from tools.benchmark import (
    extract_ground_truth, collect_parser_text,
    tokenize, compute_recall, find_missing,
    save_to_json, PDFScore, BenchmarkReport,
)


# ── 페이지 이미지 렌더링 ──────────────────────────────────────────────────────

def render_pages_b64(pdf_path: str, dpi: int = 120) -> list[str]:
    """각 페이지를 base64 PNG로 반환"""
    doc = fitz.open(pdf_path)
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    images = []
    for page in doc:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        images.append(base64.b64encode(pix.tobytes("png")).decode())
    doc.close()
    return images


# ── 파서 결과 캐시 ────────────────────────────────────────────────────────────

CACHE_DIR = "inspect/cache"


def _cache_path(pdf_path: str, version: str) -> str:
    stem = Path(pdf_path).stem
    return os.path.join(CACHE_DIR, f"{stem}_v{version}.json")


def _load_cached(pdf_path: str, version: str) -> dict | None:
    path = _cache_path(pdf_path, version)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_cache(pdf_path: str, version: str, result: dict):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _cache_path(pdf_path, version)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)


# ── 점수 히스토리 ────────────────────────────────────────────────────────────

HISTORY_FILE = "inspect/history.json"
MAX_HISTORY_PER_KEY = 20


def _load_history() -> list[dict]:
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_score_history(score: PDFScore, version: str):
    """점수를 히스토리에 추가 (파일+버전별 최근 MAX_HISTORY_PER_KEY개 유지)"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    history = _load_history()
    history.append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "version": version,
        "filename": score.filename,
        "overall": score.overall,
        "title": score.title,
        "section_a": score.section_a,
        "section_b": score.section_b,
        "gt_tokens": score.gt_tokens,
        "parser_tokens": score.parser_tokens,
    })

    # 파일+버전별로 최근 항목만 유지
    from collections import defaultdict
    by_key: dict = defaultdict(list)
    for h in history:
        k = f"{h['filename']}:{h['version']}"
        by_key[k].append(h)
    trimmed = []
    for entries in by_key.values():
        trimmed.extend(entries[-MAX_HISTORY_PER_KEY:])
    trimmed.sort(key=lambda h: h.get("date", ""))

    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)


def _get_previous_score(version: str, filename: str) -> float | None:
    """직전 실행의 종합 점수 반환 (없으면 None)"""
    history = _load_history()
    matching = [h for h in history
                if h["version"] == version and h["filename"] == filename]
    if len(matching) < 2:
        return None
    # 마지막 항목은 방금 저장된 것, 그 직전 것을 반환
    return matching[-2]["overall"]


# ── 파서 실행 ─────────────────────────────────────────────────────────────────

def run_parsers(pdf_path: str, parser_versions: list[str],
                doc_type: str = "registry",
                fresh: bool = False) -> tuple[dict, set[str]]:
    """버전별 파서 결과 반환. 최신 버전만 항상 실행, 나머지는 캐시 사용.

    Returns:
        (results, cached_versions) — cached_versions는 캐시에서 로드된 버전 집합
    """
    latest = parser_versions[-1]  # 정렬된 버전 목록의 마지막 = 최신
    results = {}
    cached_vers: set[str] = set()
    pdf_bytes = None

    for ver in parser_versions:
        # 최신 버전이 아니고, fresh 모드가 아니면 캐시 시도
        if not fresh and ver != latest:
            cached = _load_cached(pdf_path, ver)
            if cached:
                results[ver] = cached
                cached_vers.add(ver)
                continue

        # PDF 읽기 (필요할 때 한 번만)
        if pdf_bytes is None:
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

        try:
            p = get_parser(doc_type, ver)
            pr = p.parse(pdf_bytes)
            result = {"ok": True, "data": pr.data, "errors": pr.errors}
        except Exception as e:
            result = {"ok": False, "data": {}, "errors": [str(e)]}

        results[ver] = result
        _save_cache(pdf_path, ver, result)

    return results, cached_vers


# ── 벤치마크 스코어링 ────────────────────────────────────────────────────────

def compute_scores(pdf_path: str, parser_results: dict,
                   doc_type: str = "registry") -> dict[str, PDFScore]:
    """각 파서 버전의 벤치마크 점수 계산 (ground truth 1회 추출)"""
    gt = extract_ground_truth(pdf_path)
    gt_full = tokenize(gt.full_text)
    gt_title = tokenize(gt.title_text)
    gt_a = tokenize(gt.section_a_text)
    gt_b = tokenize(gt.section_b_text)

    scores = {}
    for ver, result in parser_results.items():
        score = PDFScore(filename=Path(pdf_path).name)
        if not result["ok"]:
            score.errors.append(
                result["errors"][0] if result["errors"] else "parse failed")
            scores[ver] = score
            continue

        data = result["data"]
        score.property_type = data.get("property_type", "unknown")
        parser_text = collect_parser_text(data)

        p_full = tokenize(parser_text["full"])
        p_title = tokenize(parser_text["title"])
        p_a = tokenize(parser_text["section_a"])
        p_b = tokenize(parser_text["section_b"])

        score.overall = compute_recall(gt_full, p_full) or 0.0
        score.title = compute_recall(gt_title, p_title)
        score.section_a = compute_recall(gt_a, p_a)
        score.section_b = compute_recall(gt_b, p_b)
        score.gt_tokens = sum(gt_full.values())
        score.parser_tokens = sum(
            min(gt_full[t], p_full.get(t, 0)) for t in gt_full)
        score.missing_top20 = find_missing(gt_full, p_full)
        score.parse_output = data
        scores[ver] = score

    return scores


# ── HTML 헬퍼 ─────────────────────────────────────────────────────────────────

def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _score_color(val):
    if val is None:
        return "#6c7086"
    if val >= 90:
        return "#a6e3a1"
    if val >= 70:
        return "#f9e2af"
    return "#f38ba8"


def _render_score_bar(score: PDFScore) -> str:
    if score.gt_tokens == 0 and score.overall == 0.0:
        return ""

    def badge(label, val):
        c = _score_color(val)
        v = f"{val:.1f}" if val is not None else "N/A"
        return (f'<span class="sb" style="border-color:{c}">'
                f'<span class="sv" style="color:{c}">{v}</span>'
                f'<span class="sl">{label}</span></span>')

    oc = _score_color(score.overall)
    return (
        f'<div class="score-bar">'
        f'<span class="sb sb-main" style="border-color:{oc};background:{oc}16">'
        f'<span class="sv" style="color:{oc};font-size:1.1rem">{score.overall:.1f}</span>'
        f'<span class="sl">종합</span></span>'
        f'{badge("표제부", score.title)}'
        f'{badge("갑구", score.section_a)}'
        f'{badge("을구", score.section_b)}'
        f'<span class="tk">{score.parser_tokens}/{score.gt_tokens} tokens</span>'
        f'</div>')


def _render_missing_tokens(score: PDFScore) -> str:
    if not score.missing_top20:
        return ""
    tokens = " ".join(
        f'<code class="mt">{_esc(t)}</code>' for t in score.missing_top20)
    return (
        f'<details class="section-card">'
        f'<summary class="section-head" style="cursor:pointer">'
        f'누락 토큰 <span class="cnt">상위 {len(score.missing_top20)}개</span>'
        f'</summary>'
        f'<div class="section-body" style="line-height:2">{tokens}</div>'
        f'</details>')


def _render_diff_controls(ver: str, all_versions: list[str]) -> str:
    """비교 대상 선택 드롭다운"""
    others = [v for v in all_versions if v != ver]
    if not others:
        return ""
    options = '<option value="">JSON 트리</option>'
    options += '<option value="__raw">JSON 원본</option>'
    for v in others:
        options += f'<option value="{v}">vs v{v}</option>'
    return (f'<div class="diff-ctrl">'
            f'<label>비교 대상:</label>'
            f'<select onchange="updateDiff(\'{ver}\',this.value)">'
            f'{options}</select></div>')


def _render_version_panel(ver: str, result: dict, score=None,
                          all_versions: list[str] | None = None) -> str:
    if not result["ok"]:
        err = _esc(result["errors"][0]) if result["errors"] else "알 수 없는 오류"
        return (f'<div class="ver-panel" data-ver="{ver}">'
                f'<div class="error">파서 오류: {err}</div></div>')

    parts = []

    # 벤치마크 점수 바
    if score:
        parts.append(_render_score_bar(score))

    # 누락 토큰
    if score:
        parts.append(_render_missing_tokens(score))

    # 비교 대상 드롭다운
    if all_versions and len(all_versions) > 1:
        parts.append(_render_diff_controls(ver, all_versions))

    # JSON diff 영역 (JS가 렌더링)
    parts.append(f'<div class="json-diff" id="diff-{ver}"></div>')

    return f'<div class="ver-panel" data-ver="{ver}">{"".join(parts)}</div>'


# ── CSS ───────────────────────────────────────────────────────────────────────

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #1e1e2e; color: #cdd6f4; font-size: 13px; }
header { padding: 14px 20px; background: #181825; border-bottom: 1px solid #313244;
         display: flex; align-items: center; gap: 12px; }
header h1 { font-size: 1rem; font-weight: 600; }
header .meta { color: #6c7086; font-size: .82rem; }

.layout { display: grid; grid-template-columns: 1fr 1fr; height: calc(100vh - 49px); }

.pages { overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 12px;
         border-right: 1px solid #313244; }
.page-wrap { position: relative; }
.page-label { font-size: .72rem; color: #6c7086; margin-bottom: 4px; }
.page-wrap img { width: 100%; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,.4); }

.parsers { overflow-y: auto; display: flex; flex-direction: column; }
.ver-tabs { display: flex; gap: 0; border-bottom: 1px solid #313244; background: #181825;
            position: sticky; top: 0; z-index: 10; }
.ver-tab { padding: 9px 18px; cursor: pointer; font-size: .82rem; color: #6c7086;
           border: none; background: none; border-bottom: 2px solid transparent; }
.ver-tab.active { color: #cdd6f4; border-bottom-color: #89b4fa; font-weight: 600; }

.ver-panel { display: none; flex: 1; overflow-y: auto; padding: 16px;
             flex-direction: column; gap: 12px; }
.ver-panel.active { display: flex; }

.section-card { background: #181825; border: 1px solid #313244; border-radius: 6px; overflow: hidden; }
.section-head { padding: 8px 12px; font-size: .78rem; font-weight: 600;
                background: #1e1e2e; border-bottom: 1px solid #313244;
                display: flex; justify-content: space-between; align-items: center; }
.section-head .cnt { font-size: .72rem; color: #6c7086; font-weight: 400; }
.section-body { padding: 10px 12px; }
.error { color: #f38ba8; padding: 8px; font-size: .8rem; }

/* 벤치마크 점수 바 */
.score-bar { display: flex; align-items: center; gap: 8px; padding: 10px 12px;
             background: #11111b; border-radius: 6px; margin-bottom: 10px; flex-wrap: wrap; }
.sb { display: flex; flex-direction: column; align-items: center; gap: 1px;
      padding: 5px 10px; border: 1px solid; border-radius: 6px; min-width: 56px; }
.sb-main { padding: 6px 14px; }
.sl { font-size: .64rem; color: #6c7086; letter-spacing: .02em; }
.sv { font-weight: 700; font-size: .85rem; }
.tk { margin-left: auto; font-size: .72rem; color: #585b70; }

/* 누락 토큰 */
.mt { background: #313244; padding: 2px 6px; border-radius: 3px;
      font-size: .72rem; color: #f38ba8; font-family: monospace; }

/* JSON diff tree */
.json-diff { font-family: 'Cascadia Code','Fira Code','Consolas',monospace;
             font-size: .78rem; line-height: 1.7; overflow-x: auto; }
.jl { padding: 1px 6px; white-space: pre; border-left: 3px solid transparent; }
.jl:hover { background: rgba(205,214,244,.04); }
.jt { cursor: pointer; color: #585b70; user-select: none;
      display: inline-block; width: 1em; text-align: center; font-size: .7rem; }
.jt:hover { color: #cdd6f4; }
.jp { color: #585b70; }
.jc { color: #45475a; font-size: .7rem; font-style: italic; }
.jb { background: #fab387; color: #1e1e2e; padding: 0 5px; border-radius: 3px;
      font-size: .65rem; font-weight: 600; margin-left: 6px; }
.ks { color: #89b4fa; } .ki { color: #7f849c; font-size: .72rem; }
.vs { color: #a6e3a1; } .vd { color: #cba6f7; }
.vb { color: #fab387; } .vn { color: #585b70; font-style: italic; }
.vp { color: #45475a; font-style: italic; }

.da { background: rgba(166,227,161,.07); border-left-color: #a6e3a1; }
.dd { background: rgba(243,139,168,.07); border-left-color: #f38ba8; opacity: .65; }

/* JSON 원본 */
.json-raw { background: #11111b; border-radius: 4px; padding: 12px; margin: 0;
            font-size: .75rem; line-height: 1.5; overflow-x: auto;
            white-space: pre-wrap; word-break: break-word; color: #cdd6f4; }

/* diff 컨트롤 */
.diff-ctrl { padding: 6px 0; display: flex; align-items: center; gap: 8px; font-size: .78rem; }
.diff-ctrl label { color: #6c7086; }
.diff-ctrl select { background: #181825; color: #cdd6f4; border: 1px solid #313244;
                    border-radius: 4px; padding: 4px 8px; font-size: .78rem; cursor: pointer; }
.diff-ctrl select:hover { border-color: #89b4fa; }
"""

# ── JS ────────────────────────────────────────────────────────────────────────

_JS = r"""
var D=window.__DATA, V=window.__VERS;

function h(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function T(v){if(v===null||v===undefined)return'n';if(Array.isArray(v))return'a';return typeof v}

function vH(v){
  if(v===null||v===undefined)return'<span class="vn">null</span>';
  if(typeof v==='string')return'<span class="vs">"'+h(v)+'"</span>';
  if(typeof v==='number')return'<span class="vd">'+v+'</span>';
  if(typeof v==='boolean')return'<span class="vb">'+v+'</span>';
  if(Array.isArray(v))return'<span class="vp">['+v.length+' items]</span>';
  if(typeof v==='object')return'<span class="vp">{'+Object.keys(v).length+' fields}</span>';
  return h(String(v));
}

function kH(k){
  return typeof k==='number'
    ?'<span class="ki">['+k+']</span>'
    :'<span class="ks">"'+h(k)+'"</span>';
}

/* ── deep diff ── */
function df(a,b){
  if(a===undefined)return{t:'a',v:b};
  if(b===undefined)return{t:'d',v:a};
  var ta=T(a),tb=T(b);
  if(ta!==tb)return{t:'m',o:a,n:b};
  if(ta==='n')return{t:'=',v:null};
  if(ta==='a'){
    var n=Math.max(a.length,b.length),it=[],c=0;
    for(var i=0;i<n;i++){var d=df(a[i],b[i]);it.push(d);if(d.t!=='=')c++}
    return c?{t:'A',items:it,c:c}:{t:'=',v:b}
  }
  if(ta==='object'){
    var ks=[...new Set([...Object.keys(a||{}),...Object.keys(b||{})])],f={},c=0;
    for(var k of ks){var d=df(a[k],b[k]);f[k]=d;if(d.t!=='=')c++}
    return c?{t:'O',f:f,c:c}:{t:'=',v:b}
  }
  return a===b?{t:'=',v:a}:{t:'m',o:a,n:b}
}

/* ── render JSON tree ── */
function rJ(v,k,dp,cls){
  cls=cls||'';
  var pd=dp*16,t=T(v);
  var kS=k!==null?kH(k)+': ':'';
  if(t!=='a'&&t!=='object')
    return'<div class="jl '+cls+'" style="padding-left:'+pd+'px">'+kS+vH(v)+'</div>';
  var isA=t==='a',len=isA?v.length:Object.keys(v).length;
  if(len===0)
    return'<div class="jl '+cls+'" style="padding-left:'+pd+'px">'+kS+(isA?'[]':'{}')+'</div>';
  var col=dp>=2,ar=col?'\u25b6':'\u25bc',ds=col?' style="display:none"':'';
  var s='<div class="jl '+cls+'" style="padding-left:'+pd+'px">'+
    '<span class="jt" onclick="tog(this)">'+ar+'</span> '+kS+
    '<span class="jp">'+(isA?'[':'{')+'</span> '+
    '<span class="jc">'+len+(isA?' items':' fields')+'</span></div>';
  s+='<div class="jch"'+ds+'>';
  if(isA){for(var i=0;i<v.length;i++)s+=rJ(v[i],i,dp+1,cls)}
  else{for(var ek of Object.keys(v))s+=rJ(v[ek],ek,dp+1,cls)}
  s+='</div>';
  s+='<div class="jl '+cls+'" style="padding-left:'+pd+'px"><span class="jp">'+(isA?']':'}')+'</span></div>';
  return s
}

/* ── render diff tree ── */
function rD(d,k,dp){
  var pd=dp*16,kS=k!==null?kH(k)+': ':'';
  switch(d.t){
  case'=':return rJ(d.v,k,dp);
  case'a':return rJ(d.v,k,dp,'da');
  case'd':return rJ(d.v,k,dp,'dd');
  case'm':
    return'<div class="jl dd" style="padding-left:'+pd+'px">'+kS+vH(d.o)+'</div>'+
           '<div class="jl da" style="padding-left:'+pd+'px">'+kS+vH(d.n)+'</div>';
  case'O':{
    var ks=Object.keys(d.f),col=dp>=2&&d.c===0,ar=col?'\u25b6':'\u25bc',ds=col?' style="display:none"':'';
    var badge=d.c>0?' <span class="jb">'+d.c+' changed</span>':'';
    var s='<div class="jl" style="padding-left:'+pd+'px">'+
      '<span class="jt" onclick="tog(this)">'+ar+'</span> '+kS+
      '<span class="jp">{</span>'+badge+'</div>';
    s+='<div class="jch"'+ds+'>';
    for(var ek of ks)s+=rD(d.f[ek],ek,dp+1);
    s+='</div>';
    s+='<div class="jl" style="padding-left:'+pd+'px"><span class="jp">}</span></div>';
    return s}
  case'A':{
    var col=dp>=2&&d.c===0,ar=col?'\u25b6':'\u25bc',ds=col?' style="display:none"':'';
    var badge=d.c>0?' <span class="jb">'+d.c+' changed</span>':'';
    var s='<div class="jl" style="padding-left:'+pd+'px">'+
      '<span class="jt" onclick="tog(this)">'+ar+'</span> '+kS+
      '<span class="jp">[</span>'+badge+'</div>';
    s+='<div class="jch"'+ds+'>';
    for(var i=0;i<d.items.length;i++)s+=rD(d.items[i],i,dp+1);
    s+='</div>';
    s+='<div class="jl" style="padding-left:'+pd+'px"><span class="jp">]</span></div>';
    return s}
  }
  return''
}

function tog(el){
  var ch=el.closest('.jl').nextElementSibling;
  if(!ch||!ch.classList.contains('jch'))return;
  var hidden=ch.style.display==='none';
  ch.style.display=hidden?'':'none';
  el.textContent=hidden?'\u25bc':'\u25b6'
}

function switchVer(ver){
  document.querySelectorAll('.ver-tab').forEach(function(t){t.classList.remove('active')});
  document.querySelectorAll('.ver-panel').forEach(function(p){p.classList.remove('active')});
  document.querySelector('.ver-tab[data-ver="'+ver+'"]').classList.add('active');
  document.querySelector('.ver-panel[data-ver="'+ver+'"]').classList.add('active');
  var el=document.getElementById('diff-'+ver);
  if(el&&el.innerHTML==='')updateDiff(ver,'')
}

function updateDiff(ver,cmpVer){
  var el=document.getElementById('diff-'+ver);
  if(!el)return;
  var data=D[ver];
  if(!data){el.innerHTML='<div class="error">데이터 없음</div>';return}
  if(!cmpVer){
    el.innerHTML=rJ(data,null,0)
  }else if(cmpVer==='__raw'){
    el.innerHTML='<pre class="json-raw">'+h(JSON.stringify(data,null,2))+'</pre>'
  }else{
    var cmpData=D[cmpVer];
    if(!cmpData){el.innerHTML='<div class="error">비교 데이터 없음</div>';return}
    el.innerHTML=rD(df(cmpData,data),null,0)
  }
}

document.addEventListener('DOMContentLoaded',function(){updateDiff(V[0],'')});
"""


# ── HTML 조립 ─────────────────────────────────────────────────────────────────

def build_html(pdf_path: str, page_images: list[str], parser_results: dict,
               scores: dict | None = None) -> str:
    fname = Path(pdf_path).name
    versions = list(reversed(parser_results.keys()))

    # 파서 데이터를 JS에 임베딩
    data_for_js = {}
    for ver, result in parser_results.items():
        data_for_js[ver] = result["data"] if result["ok"] else {}
    data_json = json.dumps(
        data_for_js, ensure_ascii=False, default=str).replace("</", "<\\/")
    versions_json = json.dumps(versions, ensure_ascii=False)

    # 탭 버튼
    tabs_html = "".join(
        f'<button class="ver-tab{" active" if i == 0 else ""}" '
        f'data-ver="{v}" onclick="switchVer(\'{v}\')">{v}</button>'
        for i, v in enumerate(versions))

    # 버전 패널
    panels_html = ""
    for i, ver in enumerate(versions):
        score = scores.get(ver) if scores else None
        panel = _render_version_panel(
            ver, parser_results[ver], score=score, all_versions=versions)
        if i == 0:
            panel = panel.replace(
                'class="ver-panel"', 'class="ver-panel active"', 1)
        panels_html += panel

    # 페이지 이미지
    pages_html = "".join(
        f'<div class="page-wrap"><div class="page-label">Page {i + 1}</div>'
        f'<img src="data:image/png;base64,{b64}" loading="lazy"></div>'
        for i, b64 in enumerate(page_images))

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>PDF Inspect — {_esc(fname)}</title>
  <style>{_CSS}</style>
</head>
<body>
<header>
  <h1>PDF Inspect</h1>
  <span class="meta">{_esc(fname)} &nbsp;·&nbsp; {len(page_images)}페이지 &nbsp;·&nbsp; {", ".join(versions)}</span>
</header>
<div class="layout">
  <div class="pages">{pages_html}</div>
  <div class="parsers">
    <div class="ver-tabs">{tabs_html}</div>
    {panels_html}
  </div>
</div>
<script>
window.__DATA={data_json};
window.__VERS={versions_json};
{_JS}
</script>
</body>
</html>"""


# ── CLI 헬퍼 ──────────────────────────────────────────────────────────────────

def _resolve_pdf_paths(items: list[str]) -> list[str]:
    paths = []
    for item in items:
        if os.path.isdir(item):
            paths.extend(glob.glob(os.path.join(item, "*.pdf")))
        elif os.path.isfile(item):
            paths.append(item)
        else:
            paths.extend(f for f in glob.glob(item)
                         if f.lower().endswith(".pdf"))
    return sorted(set(paths))


def _fmt(val):
    return f"{val:.1f}" if val is not None else "N/A"


def _print_history(filenames: list[str], versions: list[str]):
    """점수 히스토리 출력"""
    history = _load_history()
    if not history:
        print("히스토리 없음")
        return

    w = 70
    for ver in versions:
        for fname in filenames:
            matching = [h for h in history
                        if h["version"] == ver and h["filename"] == fname]
            if not matching:
                continue
            print(f"\n{'─' * w}")
            print(f"  v{ver} — {fname}")
            print(f"{'─' * w}")
            prev = None
            for h in matching:
                delta = ""
                if prev is not None:
                    d = h["overall"] - prev
                    arrow = "▲" if d > 0 else "▼" if d < 0 else "="
                    delta = f"  {arrow} {d:+.1f}"
                prev = h["overall"]
                t = _fmt(h.get("title"))
                a = _fmt(h.get("section_a"))
                b = _fmt(h.get("section_b"))
                print(f"  {h['date']}  {h['overall']:5.1f}/100{delta}"
                      f"  (표제 {t} | 갑 {a} | 을 {b})")
    print()


def _print_batch_summary(all_scores, versions):
    w = 60
    print(f"\n{'=' * w}")
    print(f"  Batch Summary")
    print(f"{'=' * w}")
    for ver in versions:
        scores = all_scores.get(ver, [])
        if not scores:
            continue
        valid = [s for s in scores if s.gt_tokens > 0]
        avg = (round(sum(s.overall for s in valid) / len(valid), 1)
               if valid else 0.0)
        t = [s.title for s in scores if s.title is not None]
        a = [s.section_a for s in scores if s.section_a is not None]
        b = [s.section_b for s in scores if s.section_b is not None]
        t_avg = round(sum(t) / len(t), 1) if t else None
        a_avg = round(sum(a) / len(a), 1) if a else None
        b_avg = round(sum(b) / len(b), 1) if b else None
        print(f"\n  v{ver}: {avg:.1f}/100")
        print(f"    표제부: {_fmt(t_avg)} | "
              f"갑구: {_fmt(a_avg)} | 을구: {_fmt(b_avg)}")
        for s in scores:
            print(f"    {s.filename:<35} {s.overall:.1f}")
    print(f"\n{'=' * w}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="PDF 집중 분석 + 벤치마크")
    ap.add_argument("pdf", nargs="+", help="PDF 파일 또는 디렉토리")
    ap.add_argument("--parsers", "-p", default="",
                    help="쉼표 구분 버전 (기본: 등록된 전 버전)")
    ap.add_argument("--type", "-t", default="registry", help="문서 타입")
    ap.add_argument("--dpi", type=int, default=120, help="렌더링 DPI")
    ap.add_argument("--out", "-o", default="", help="출력 HTML 경로 (단일 파일)")
    ap.add_argument("--fresh", action="store_true",
                    help="캐시 무시, 모든 버전 새로 파싱")
    ap.add_argument("--no-benchmark", action="store_true",
                    help="벤치마크 스코어링 건너뛰기")
    ap.add_argument("--save", "-s", action="store_true",
                    help="벤치마크 히스토리 JSON 저장")
    ap.add_argument("--history", action="store_true",
                    help="점수 히스토리 조회")
    args = ap.parse_args()

    pdf_paths = _resolve_pdf_paths(args.pdf)
    if not pdf_paths:
        print("PDF 파일 없음", file=sys.stderr)
        sys.exit(1)

    if args.parsers:
        versions = [v.strip().lstrip("v") for v in args.parsers.split(",")]
    else:
        versions = list_versions(args.type)

    # --history 모드: 히스토리만 출력하고 종료
    if args.history:
        filenames = [Path(p).name for p in pdf_paths]
        _print_history(filenames, versions)
        return

    batch = len(pdf_paths) > 1
    all_scores: dict[str, list[PDFScore]] = {}

    for pdf_path in pdf_paths:
        fname = Path(pdf_path).name
        print(f"\n── {fname} ──")

        print(f"  렌더링 ({args.dpi} DPI)…")
        page_images = render_pages_b64(pdf_path, dpi=args.dpi)
        print(f"  {len(page_images)}페이지")

        print(f"  파싱 ({', '.join(f'v{v}' for v in versions)})…")
        results, cached_vers = run_parsers(
            pdf_path, versions, doc_type=args.type, fresh=args.fresh)
        for ver, r in results.items():
            tag = "캐시" if ver in cached_vers else "실행"
            status = "OK" if r["ok"] else "ERROR"
            print(f"    v{ver}: {status} ({tag})")

        scores = None
        if not args.no_benchmark:
            print("  스코어링…")
            scores = compute_scores(pdf_path, results, doc_type=args.type)
            for ver, sc in scores.items():
                if sc.gt_tokens == 0:
                    print(f"    v{ver}: N/A")
                    continue
                # 히스토리 저장 후 delta 계산
                _save_score_history(sc, ver)
                prev = _get_previous_score(ver, sc.filename)
                delta = ""
                if prev is not None:
                    d = sc.overall - prev
                    arrow = "▲" if d > 0 else "▼" if d < 0 else "="
                    delta = f" ({arrow} {d:+.1f})"
                print(f"    v{ver}: {sc.overall:.1f}/100{delta}")
                all_scores.setdefault(ver, []).append(sc)

        html = build_html(pdf_path, page_images, results, scores=scores)

        if args.out and not batch:
            out_path = args.out
        else:
            os.makedirs("inspect", exist_ok=True)
            stem = Path(pdf_path).stem
            out_path = f"inspect/{stem}.html"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  → {out_path}")

    # 배치 요약
    if batch and all_scores:
        _print_batch_summary(all_scores, versions)

    # 히스토리 저장
    if args.save and all_scores:
        for ver in versions:
            ver_scores = all_scores.get(ver, [])
            if not ver_scores:
                continue
            report = BenchmarkReport(
                document_type=args.type,
                parser_version=ver,
                date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                file_count=len(ver_scores),
                scores=ver_scores,
            )
            valid = [s for s in ver_scores if s.gt_tokens > 0]
            if valid:
                report.average = round(
                    sum(s.overall for s in valid) / len(valid), 1)
            t_s = [s.title for s in ver_scores if s.title is not None]
            if t_s:
                report.title_avg = round(sum(t_s) / len(t_s), 1)
            a_s = [s.section_a for s in ver_scores if s.section_a is not None]
            if a_s:
                report.section_a_avg = round(sum(a_s) / len(a_s), 1)
            b_s = [s.section_b for s in ver_scores if s.section_b is not None]
            if b_s:
                report.section_b_avg = round(sum(b_s) / len(b_s), 1)
            save_to_json(report)

    if not batch:
        out_path = args.out or f"inspect/{Path(pdf_paths[0]).stem}.html"
        print(f"\n브라우저에서 열기: file:///{Path(out_path).resolve().as_posix()}")


if __name__ == "__main__":
    main()
