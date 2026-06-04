#!/usr/bin/env python3
"""
HERMES QUANT V2 — DASHBOARD INTERATIVO
========================================
Gera um HTML autônomo com painel de configurações interativo.
"""
import os, sys, json, glob
from datetime import datetime, timezone
import warnings
warnings.filterwarnings("ignore")

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ".")
from config.settings import (
    SYMBOLS, INPUT_TFS, CONTEXT_TFS, TF_LABEL,
    PROCESSED_DIR, MODEL_DIR, USER_SETTINGS,
)


def scan_models():
    models = []
    for s in SYMBOLS:
        for tf in INPUT_TFS + CONTEXT_TFS:
            label = TF_LABEL.get(tf, tf)
            prefix = s.replace("/", "_")
            feat_path = os.path.join(PROCESSED_DIR, f"{prefix}_{label}_features.parquet")
            xgb_paths = glob.glob(os.path.join(MODEL_DIR, f"{prefix}_{label}_*_xgb.json"))
            mrd_path = os.path.join(MODEL_DIR, f"{prefix}_{label}_regime_perf.json")
            entry = {
                "symbol": s, "tf": tf, "label": label,
                "has_features": os.path.exists(feat_path),
                "has_models": len(xgb_paths) > 0,
                "has_mrd": os.path.exists(mrd_path),
            }
            if entry["has_features"]:
                try:
                    df = __import__("pandas").read_parquet(feat_path, columns=["timestamp", "close"])
                    entry["candles"] = len(df)
                except:
                    entry["candles"] = 0
            models.append(entry)
    return models


def load_reports():
    reports = []
    for path in glob.glob(os.path.join(MODEL_DIR, "*_report.json")):
        try:
            with open(path) as f:
                reports.append(json.load(f))
        except:
            pass
    return reports


def load_mrd():
    data = {}
    for path in glob.glob(os.path.join(MODEL_DIR, "*_regime_perf.json")):
        try:
            key = os.path.basename(path).replace("_regime_perf.json", "")
            with open(path) as f:
                data[key] = json.load(f)
        except:
            pass
    return data


def generate_html():
    models = scan_models()
    reports = load_reports()
    mrd_data = load_mrd()
    now = datetime.now(timezone.utc)

    # Embed data as JSON
    embed = {
        "models": [m for m in models if m["has_models"] or m["has_features"]],
        "reports": reports,
        "mrd": mrd_data,
        "settings": USER_SETTINGS,
        "backtest": {
            "BTC_M1": {
                "total_trades": 577, "win_rate": 0.619, "expectancy": 0.1137,
                "by_regime": {
                    "lateralization": {"trades": 306, "wr": 0.618, "exp": 0.1118},
                    "strong_trend_bear": {"trades": 68, "wr": 0.529, "exp": -0.0471},
                    "strong_trend_bull": {"trades": 52, "wr": 0.654, "exp": 0.1769},
                    "weak_trend_bear": {"trades": 51, "wr": 0.706, "exp": 0.2706},
                    "weak_trend_bull": {"trades": 89, "wr": 0.629, "exp": 0.1326},
                }
            }
        },
        "generated_at": now.isoformat(),
    }

    embed_json = json.dumps(embed, ensure_ascii=False)

    # Read the HTML template (not an f-string, no brace conflicts)
    html_template = r"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Hermes Quant V2 — Dashboard</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0e17;color:#e0e6f0;padding:16px}
.tabs{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.tab{padding:10px 20px;border-radius:8px;background:#111b2e;color:#8899bb;cursor:pointer;border:1px solid #1a2a40;font-size:.9rem;font-weight:600}
.tab:hover{background:#1a2a40}
.tab.active{background:#00d4aa22;color:#00d4aa;border-color:#00d4aa44}
.tab-content{display:none}
.tab-content.active{display:block}
h1{font-size:1.5rem;color:#00d4aa;margin-bottom:4px}
.subtitle{color:#667799;margin-bottom:16px;font-size:.85rem}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-bottom:20px}
.card{background:#111b2e;border:1px solid #1a2a40;border-radius:12px;padding:14px}
.card .v{font-size:1.5rem;font-weight:700;color:#00d4aa}
.card .l{font-size:.8rem;color:#667799;margin-top:3px}
.card .s{font-size:.7rem;color:#445566}
table{width:100%;border-collapse:collapse;font-size:.82rem}
th{text-align:left;padding:8px;border-bottom:2px solid #1a2a40;color:#8899bb;font-weight:600}
td{padding:6px 8px;border-bottom:1px solid #152036}
tr:hover td{background:#0f1a30}
.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px}
.sc{background:#111b2e;border:1px solid #1a2a40;border-radius:12px;padding:16px}
.sc h3{color:#00d4aa;font-size:.95rem;margin-bottom:12px;border-bottom:1px solid #1a2a40;padding-bottom:8px}
.fg{margin-bottom:10px}
.fg label{display:block;font-size:.8rem;color:#8899bb;margin-bottom:3px}
.fg input,.fg select{width:100%;padding:8px 10px;border-radius:6px;border:1px solid #1a2a40;background:#0a0e17;color:#e0e6f0;font-size:.85rem;outline:none}
.fg input:focus{border-color:#00d4aa44}
.fg input[type=password]{font-family:monospace}
.btn{padding:8px 16px;border-radius:6px;border:none;font-weight:600;cursor:pointer;font-size:.85rem}
.bt1{background:#00d4aa;color:#0a0e17}
.bt2{background:#1a2a40;color:#8899bb}
.bt3{background:#ff4466;color:#fff}
.cb{height:8px;background:#152036;border-radius:4px;margin:6px 0;overflow:hidden}
.cf{height:100%;border-radius:4px;background:linear-gradient(90deg,#00d4aa,#00ffcc)}
.ci{margin-bottom:14px}
.gr{color:#00d4aa}
.re{color:#ff4466}
.ye{color:#ffaa00}
.bg{display:inline-block;padding:1px 6px;border-radius:4px;font-size:.7rem;font-weight:600}
.bg-green{background:#00d4aa22;color:#00d4aa}
.bg-red{background:#ff446622;color:#ff4466}
.bg-yellow{background:#ffaa0022;color:#ffaa00}
.ft{text-align:center;color:#445566;font-size:.7rem;margin-top:30px;padding-top:16px;border-top:1px solid #152036}
@media(max-width:600px){.stats{grid-template-columns:repeat(2,1fr)}.sg{grid-template-columns:1fr}table{font-size:.7rem}}
</style>
</head>
<body>

<h1>HERMES QUANT V2</h1>
<div class="subtitle">Sistema de IA Multi-Timeframe para Opções Binarias</div>

<div class="tabs">
  <div class="tab active" onclick="st('dashboard')">DASHBOARD</div>
  <div class="tab" onclick="st('settings')">CONFIG</div>
  <div class="tab" onclick="st('projections')">PROJECOES</div>
  <div class="tab" onclick="st('mrd')">MRD</div>
</div>

<div id="tb-dashboard" class="tab-content active">
<div class="stats" id="st-dash"></div>
<h2>MODELOS TREINADOS</h2>
<table><thead><tr><th>Ativo</th><th>TF</th><th>Candles</th><th>Acc</th><th>Prec</th><th>Rec</th><th>Status</th></tr></thead><tbody id="md-body"></tbody></table>
</div>

<div id="tb-settings" class="tab-content">
<h2>CONFIGURACOES</h2>
<div class="sg">
<div class="sc">
<h3>CAPITAL</h3>
<div class="fg"><label>Capital Inicial</label><input type="number" id="cfg-cap" value="100" step="10" min="10" oninput="rp()"></div>
<div class="fg"><label>Moeda</label><select id="cfg-cur" onchange="rp()"><option value="BRL">BRL (R$)</option><option value="USD">USD ($)</option></select></div>
</div>
<div class="sc">
<h3>CICLOS</h3>
<div id="cyc-cfg"></div>
<button class="btn bt2" onclick="ac()" style="margin-top:8px">+ Novo Ciclo</button>
</div>
<div class="sc">
<h3>EXCHANGES (API Keys)</h3>
<div class="fg"><label>IQOption</label><input type="password" id="api-iqo" style="font-family:monospace" onchange="ss()"></div>
<div class="fg"><label>Quotex</label><input type="password" id="api-quo" style="font-family:monospace" onchange="ss()"></div>
<div class="fg"><label>PocketOption</label><input type="password" id="api-poc" style="font-family:monospace" onchange="ss()"></div>
<div class="fg"><label>Deriv</label><input type="password" id="api-der" style="font-family:monospace" onchange="ss()"></div>
<div style="margin-top:6px"><label style="font-size:.75rem;color:#667799"><input type="checkbox" id="demo-m" checked onchange="ss()"> Modo Demo</label></div>
</div>
<div class="sc">
<h3>TRADING</h3>
<div class="fg"><label>Win Rate Alvo (%)</label><input type="number" id="cfg-wr" value="61.9" step="0.1" oninput="rp()"></div>
<div class="fg"><label>Payout (%)</label><input type="number" id="cfg-po" value="80" step="1" oninput="rp()"></div>
<div class="fg"><label>Confianca Minima (%)</label><input type="number" id="cfg-mc" value="88" step="1" oninput="rp()"></div>
</div>
</div>
<div style="margin-top:12px;display:flex;gap:8px">
<button class="btn bt1" onclick="ss()">SALVAR</button>
<button class="btn bt2" onclick="rs()">RESTAURAR</button>
<button class="btn bt2" onclick="exs()">EXPORTAR</button>
<button class="btn bt2" onclick="document.getElementById('fi').click()">IMPORTAR</button>
<input type="file" id="fi" style="display:none" onchange="ims(event)">
</div>
<div id="sv-msg" style="margin-top:6px;font-size:.8rem;color:#00d4aa"></div>
</div>

<div id="tb-projections" class="tab-content">
<h2>PROJECOES FINANCEIRAS</h2>
<div class="stats" id="st-proj"></div>
<h3>CICLOS DE CRESCIMENTO</h3>
<div id="cyc-proj"></div>
<h3 style="margin-top:20px">JUROS COMPOSTOS</h3>
<table><thead><tr><th>Periodo</th><th>Capital</th><th>Trades</th><th>Lucro</th><th>Retorno</th><th>Marco</th></tr></thead><tbody id="comp-body"></tbody></table>
</div>

<div id="tb-mrd" class="tab-content">
<h2>MARKET REGIME DETECTION</h2>
<table><thead><tr><th>Ativo/TF</th><th>Regime</th><th>Trades</th><th>WR</th><th>Exp</th><th>Status</th></tr></thead><tbody id="mrd-body"></tbody></table>
</div>

<div class="ft">Hermes Quant V2</div>

<script>
const DATA = %EMBED_JSON%;
const D = DATA;
const C = {BRL:'R$',USD:'$'};
let UC = [];

function s(v,c){const s=C[c]||'R$';return s+' '+v.toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}
function p(v){return(v*100).toFixed(1)+'%'}

function st(n){document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));document.querySelector(`[onclick*="'${n}'"]`).classList.add('active');document.getElementById('tb-'+n).classList.add('active');if(n==='projections')rp()}

function init(){
  const u=JSON.parse(localStorage.getItem('hq'))||D.settings||{};
  const cap=u.capital||{};
  document.getElementById('cfg-cap').value=cap.initial||100;
  document.getElementById('cfg-cur').value=cap.currency||'BRL';
  const tr=u.trading||{};
  document.getElementById('cfg-wr').value=(tr.win_rate_target||0.619)*100;
  document.getElementById('cfg-po').value=(tr.payout_rate||0.80)*100;
  document.getElementById('cfg-mc').value=(tr.min_confidence||0.88)*100;
  const ex=u.exchanges||{};
  const em={'iqoption':'api-iqo','quotex':'api-quo','pocketoption':'api-poc','deriv':'api-der'};
  for(const[k,v]of Object.entries(em)){const e=document.getElementById(v);if(e&&ex[k]&&ex[k].api_key)e.value=ex[k].api_key}
  document.getElementById('demo-m').checked=(ex.iqoption&&ex.iqoption.demo_mode!==undefined)?ex.iqoption.demo_mode:true;
  UC=u.cycles?Object.values(u.cycles):[{name:'Ciclo 1',target:1000,tpd:15,rp:2.0,mg:2},{name:'Ciclo 2',target:10000,tpd:10,rp:1.5,mg:1},{name:'Ciclo 3',target:50000,tpd:5,rp:1.0,mg:0}];
  rc();rm();rmrd();rp()
}

function rc(){
  const e=document.getElementById('cyc-cfg');
  e.innerHTML=UC.map((c,i)=>'<div class="ci" style="border:1px solid #1a2a40;border-radius:8px;padding:10px;margin-bottom:6px"><div style="display:flex;justify-content:space-between"><input style="background:transparent;border:none;color:#e0e6f0;font-weight:600;width:130px" value="'+c.name+'" onchange="UC['+i+'].name=this.value;ss()"><button class="btn bt3" style="padding:2px 8px;font-size:.75rem" onclick="UC.splice('+i+',1);rc();ss()">X</button></div><div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:6px"><div class="fg"><label>Meta</label><input type="number" value="'+c.target+'" onchange="UC['+i+'].target=+this.value;rp()"></div><div class="fg"><label>Trades/dia</label><input type="number" value="'+c.tpd+'" onchange="UC['+i+'].tpd=+this.value;rp()"></div><div class="fg"><label>Risco %</label><input type="number" value="'+c.rp+'" step="0.5" onchange="UC['+i+'].rp=+this.value;rp()"></div><div class="fg"><label>Martingale</label><input type="number" value="'+c.mg+'" min="0" max="5" onchange="UC['+i+'].mg=+this.value;rp()"></div></div></div>').join('')
}

function ac(){const l=UC[UC.length-1]||{target:100000,tpd:3,rp:0.5,mg:0};UC.push({name:'Ciclo '+(UC.length+1),target:l.target*3,tpd:Math.max(3,l.tpd-2),rp:Math.max(0.5,l.rp-0.5),mg:Math.max(0,l.mg-1)});rc();rp()}

function ss(){
  var s={capital:{initial:+document.getElementById('cfg-cap').value,currency:document.getElementById('cfg-cur').value},trading:{win_rate_target:document.getElementById('cfg-wr').value/100,payout_rate:document.getElementById('cfg-po').value/100,min_confidence:document.getElementById('cfg-mc').value/100},exchanges:{iqoption:{api_key:document.getElementById('api-iqo').value,demo_mode:document.getElementById('demo-m').checked},quotex:{api_key:document.getElementById('api-quo').value,demo_mode:document.getElementById('demo-m').checked},pocketoption:{api_key:document.getElementById('api-poc').value,demo_mode:document.getElementById('demo-m').checked},deriv:{api_key:document.getElementById('api-der').value,demo_mode:document.getElementById('demo-m').checked}},cycles:Object.fromEntries(UC.map((c,i)=>['c'+(i+1),c]))};
  localStorage.setItem('hq',JSON.stringify(s));
  document.getElementById('sv-msg').textContent='Salvo em '+new Date().toLocaleTimeString();
  rp()
}

function rs(){localStorage.removeItem('hq');location.reload()}
function exs(){const s=localStorage.getItem('hq');if(!s)return alert('Nada');const b=new Blob([s],{type:'application/json'});const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='hermes-quant-config.json';a.click()}
function ims(e){const f=e.target.files[0];if(!f)return;const r=new FileReader();r.onload=function(ev){localStorage.setItem('hq',ev.target.result);location.reload()};r.readAsText(f)}

function rp(){
  const cap=+document.getElementById('cfg-cap').value,cur=document.getElementById('cfg-cur').value,wr=document.getElementById('cfg-wr').value/100,po=document.getElementById('cfg-po').value/100,exp=wr*po-(1-wr),tpd=4.8;
  document.getElementById('st-dash').innerHTML='<div class="card"><div class="v">'+s(cap,cur)+'</div><div class="l">Capital Inicial</div></div><div class="card"><div class="v">'+p(wr)+'</div><div class="l">Win Rate</div></div><div class="card"><div class="v" style="color:'+(exp>=0?'#00d4aa':'#ff4466')+'">'+(exp>=0?'+':'')+p(exp)+'</div><div class="l">Expectativa</div></div><div class="card"><div class="v">577</div><div class="l">Trades Backtest</div></div><div class="card"><div class="v">'+s(cap*(1+exp*tpd*22),cur)+'</div><div class="l">Proj. Mensal</div></div><div class="card"><div class="v">'+s(cap*(1+exp*tpd*22)*10,cur)+'</div><div class="l">Proj. 10 Ativos</div></div>';
  const mp=exp*tpd*22;
  document.getElementById('st-proj').innerHTML='<div class="card"><div class="v">'+s(cap*(1+exp*tpd),cur)+'</div><div class="l">1 Dia</div></div><div class="card"><div class="v">'+s(cap*(1+exp*tpd*5),cur)+'</div><div class="l">1 Semana</div></div><div class="card"><div class="v">'+s(cap*(1+mp),cur)+'</div><div class="l">1 Mes</div></div><div class="card"><div class="v">'+s(cap*Math.pow(1+mp,3),cur)+'</div><div class="l">3 Meses</div></div><div class="card"><div class="v">'+s(cap*Math.pow(1+mp,6),cur)+'</div><div class="l">6 Meses</div></div><div class="card"><div class="v">'+s(cap*Math.pow(1+mp,12),cur)+'</div><div class="l">12 Meses</div></div>';
  rcp(cap,cur,wr,po,exp);rct(cap,cur,wr,po,exp,tpd)
}

function rcp(cap,cur,wr,po,exp){
  let h='',cc=cap;
  for(const c of UC){
    const tv=cc*c.rp/100,ppt=tv*exp,tn=Math.ceil((c.target-cc)/Math.max(ppt,0.01)),de=Math.ceil(tn/c.tpd),pd=Math.min(100,cc/c.target*100),at=cc>=c.target;
    h+='<div class="ci"><div style="display:flex;justify-content:space-between"><strong>'+c.name+'</strong><span style="color:#8899bb;font-size:.8rem">'+s(c.target,cur)+'</span></div><div class="cb"><div class="cf" style="width:'+pd.toFixed(1)+'%"></div></div><div style="display:flex;gap:12px;font-size:.8rem;flex-wrap:wrap"><span style="color:#00d4aa">'+s(cc,cur)+' / '+s(c.target,cur)+'</span><span style="color:#8899bb">'+pd.toFixed(1)+'%</span>'+(at?'<span style="color:#00d4aa">ATINGIDA</span>':'<span style="color:#667799">~'+tn.toLocaleString()+' trades ~'+de+' dias</span>')+'<span style="color:#445566">'+c.tpd+' trades/dia '+p(c.rp/100)+' risco '+c.mg+' nv MG</span></div></div>';
    cc=c.target
  }
  document.getElementById('cyc-proj').innerHTML=h
}

function rct(cap,cur,wr,po,exp,tpd){
  let rows='',c=cap,tg=UC.map(x=>x.target),ti=0;
  for(let d=30;d<=720;d+=30){
    c=c*Math.pow(1+exp*tpd,30);
    while(ti<tg.length&&c>=tg[ti])ti++;
    rows+='<tr><td>'+d+' dias</td><td>'+s(c,cur)+'</td><td>'+(tpd*30).toFixed(0)+'</td><td>'+s(c-cap,cur)+'</td><td>'+p((c-cap)/cap)+'</td><td>'+(ti<tg.length?UC[ti].name:'COMPLETO')+'</td></tr>';
    if(c>=tg[tg.length-1])break
  }
  document.getElementById('comp-body').innerHTML=rows
}

function rm(){
  const tb=document.getElementById('md-body');
  tb.innerHTML=D.models.filter(m=>m.has_features).sort((a,b)=>a.symbol.localeCompare(b.symbol)||a.tf.localeCompare(b.tf)).map(m=>{
    let met='-';
    for(const r of D.reports){if(r.symbol===m.symbol&&r.timeframe===m.tf){const me=r.results&&r.results.call_1&&r.results.call_1.metrics;if(me)met=p(me.accuracy)+' '+p(me.precision)+' '+p(me.recall);break}}
    const st=m.has_models?'<span class="bg bg-green">TREINADO</span>':'<span class="bg bg-yellow">PENDENTE</span>';
    return '<tr><td>'+m.symbol.split('/')[0]+'</td><td><span class="bg bg-green">'+m.label+'</span></td><td>'+(m.candles||0)+'</td>'+met.split(' ').map(x=>'<td>'+(x||'-')+'</td>').join('')+'<td>'+st+'</td></tr>'
  }).join('')
}

function rmrd(){
  const tb=document.getElementById('mrd-body');
  let rows='';
  for(const[k,rs]of Object.entries(D.mrd)){for(const r of rs){const e=r.expectancy_call||r.expectancy_put||0,st=e>0?'<span class="bg bg-green">TRADE</span>':'<span class="bg bg-red">EVITAR</span>',c=e>0.1?'gr':e>0?'ye':'re';rows+='<tr><td>'+k.replace('_',' ')+'</td><td>'+r.regime+'</td><td>'+(r.samples||0)+'</td><td class="'+c+'">'+p(r.win_rate_call||r.win_rate_put||0)+'</td><td class="'+c+'">'+(e>=0?'+':'')+p(e)+'</td><td>'+st+'</td></tr>'}}
  tb.innerHTML=rows||'<tr><td colspan="6" style="text-align:center;color:#667799">Sem dados MRD</td></tr>'
}

init();
</script>
</body>
</html>"""

    path = os.path.join(MODEL_DIR, "dashboard.html")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        content = html_template.replace("%EMBED_JSON%", embed_json)
        f.write(content)
    print(f"Dashboard HTML salvo: {path}")
    print(f"Tamanho: {os.path.getsize(path):,} bytes")

    # Also save a JSON data file for API consumption
    data_path = os.path.join(MODEL_DIR, "dashboard_data.json")
    with open(data_path, "w") as f:
        json.dump(embed, f, indent=2, default=str)
    print(f"Dados JSON salvos: {data_path}")


if __name__ == "__main__":
    generate_html()
