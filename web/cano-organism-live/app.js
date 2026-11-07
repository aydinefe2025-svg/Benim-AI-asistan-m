
'use strict';
const REPO='aydinefe2025-svg/Benim-AI-asistan-m';
const REF='experiment/cano-digital-state-20261107';
const BASE=`https://raw.githubusercontent.com/${REPO}/${REF}/research_reports/cano-digital-continuity`;
const el=id=>document.getElementById(id);
const SVG='http://www.w3.org/2000/svg';
const hex=(buffer)=>Array.from(new Uint8Array(buffer)).map(x=>x.toString(16).padStart(2,'0')).join('');
function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value!==null && typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
async function sha256(value){return hex(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonical(value)+'\n')))}
function assert(c,message){if(!c)throw new Error(message)}
function setStatus(state,message){el('statusPill').dataset.status=state;el('statusText').textContent=message;el('footerStatus').textContent=message}
function shortHash(s){return typeof s==='string'?s.slice(0,9)+'…': '—'}
function formatDate(date){try{return new Intl.DateTimeFormat('tr-TR',{dateStyle:'medium',timeZone:'UTC'}).format(new Date(date+'T12:00:00Z'))}catch{return date}}
// Distinguish integrity (cryptographic record check) from timely scheduled execution.
// GitHub Actions runs at 05:47 UTC; allow up to two hours for a delayed runner.
const ONE_DAY_MS=86400000;
const SCHEDULE_OFFSET_MS=(5*60+47)*60000;
const SCHEDULE_GRACE_MS=2*60*60000;
const SIMULATION_EPOCH_MS=Date.UTC(2026,10,7);
function calendarWindow(recordDay,nowMs=Date.now()){
  assert(typeof recordDay==='string' && /^\d{4}-\d{2}-\d{2}$/.test(recordDay), 'Invalid report day');
  assert(Number.isFinite(nowMs) && nowMs>=SIMULATION_EPOCH_MS,'Invalid clock');
  const dayStart=Math.floor(nowMs/ONE_DAY_MS)*ONE_DAY_MS;
  const reportStart=Date.parse(recordDay+'T00:00:00Z');
  assert(Number.isFinite(reportStart) && new Date(reportStart).toISOString().slice(0,10)===recordDay,'Invalid record date');
  const planned=dayStart+SCHEDULE_OFFSET_MS;
  const nextRun=nowMs < planned ? planned : planned+ONE_DAY_MS;
  const requiredStart=Math.max(SIMULATION_EPOCH_MS,nowMs >= planned+SCHEDULE_GRACE_MS ? dayStart : dayStart-ONE_DAY_MS);
  let level='current';
  if(reportStart>dayStart || (reportStart===dayStart && nowMs<planned && reportStart!==SIMULATION_EPOCH_MS))level='future';
  else if(reportStart<requiredStart)level='stale';
  else if(nowMs>=planned && nowMs<planned+SCHEDULE_GRACE_MS && reportStart<dayStart)level='pending';
  return {level,requiredDay:new Date(requiredStart).toISOString().slice(0,10),nextRunISO:new Date(nextRun).toISOString()};
}
function renderCadence(day){
  const health=calendarWindow(day);
  const desc={
    current:'Son günlük kayıt beklenen zaman penceresinde; gerçek görev çalışması ayrıca doğrulanmalıdır.',
    pending:'Yeni günlük koşu penceresi açıldı; GitHub Actions çalışması ve yeni kayıt bekleniyor.',
    stale:'UYARI: Beklenen yeni günlük kayıt henüz yok. Veri sağlam olabilir ancak çoğalma görevinin devamı doğrulanmadı.',
    future:'UYARI: Kayıt takvimde geleceğe ait görünüyor; canlı süreç kanıtı değildir.'
  };
  el('cadenceStatus').dataset.status=health.level;
  el('cadenceStatus').textContent=desc[health.level];
  el('scheduledNext').textContent=new Intl.DateTimeFormat('tr-TR',{timeZone:'Europe/Istanbul',dateStyle:'medium',timeStyle:'short'}).format(new Date(health.nextRunISO))+' (Türkiye saati)';
  el('requiredDay').textContent=health.requiredDay;
  return health.level;
}
async function fetchJSON(url){const controller=new AbortController();const timeout=setTimeout(()=>controller.abort(),14000);try{const response=await fetch(url,{cache:'no-cache',signal:controller.signal});if(!response.ok)throw new Error('GitHub HTTP '+response.status);return await response.json()}finally{clearTimeout(timeout)}}
async function load(){
  el('refresh').disabled=true;el('errorDetail').textContent='';setStatus('loading','Kaynak doğrulanıyor');
  try{
    const state=await fetchJSON(BASE+'/genome-state.json');
    assert(state && state.schema==='genome-replay-checkpoint-v1','Genom şeması tanınmıyor');
    assert(Number.isInteger(state.ticks)&&state.ticks>=0&&state.ticks<=10000,'Adım sınırı geçersiz');
    assert(state.parameters?.capacity===24,'Beklenmeyen kapasite');
    assert(state.parameters?.allow_replication===true,'Çoğalma ayarı doğrulanmadı');
    assert(typeof state.sha256==='string','Durum özeti eksik');
    const stateBody={schema:state.schema,parameters:state.parameters,ticks:state.ticks,state:state.state};
    assert(await sha256(stateBody)===state.sha256,'Durum SHA-256 uyuşmuyor');
    const day=dateForTick(state.ticks);
    assert(day!==null,'Kontrol noktası gün takvimiyle eşleşmiyor');
    const report=await fetchJSON(BASE+'/daily/'+day+'.json');
    assert(report.schema==='cano-calendar-digital-cycle-v1'&&report.day===day&&report.tick===state.ticks,'Günlük rapor ve durum tarihleri farklı');
    const reportBody={...report};delete reportBody.sha256;
    assert(await sha256(reportBody)===report.sha256,'Günlük rapor SHA-256 uyuşmuyor');
    assert(await sha256(state.state)===report.state_sha256,'Genom ve günlük rapor durum hashleri uyuşmuyor');
    const metrics=state.state?.metrics, observed=report.observed;
    assert(metrics&&observed&&Array.isArray(state.state?.organisms),'Nüfus verisi eksik');
    assert(JSON.stringify(metrics)===JSON.stringify(observed),'Rapordaki ölçümler durumla uyuşmuyor');
    assert(metrics.population===state.state.organisms.length&&metrics.population<=state.parameters.capacity,'Nüfus/kota uyuşmazlığı');
    assert(metrics.births>=0&&metrics.deaths>=0&&metrics.population===1+metrics.births-metrics.deaths,'Nüfus muhasebesi uyuşmuyor');
    assert(report.division_disabled_control?.births===0,'Kontrol grubunda beklenmeyen doğum');
    const ids=new Set(state.state.organisms.map(x=>x.identifier));assert(ids.size===state.state.organisms.length,'Tekrarlı birey kimliği');
    for(const organism of state.state.organisms){assert(Number.isInteger(organism.generation)&&organism.generation>=0,'Nesil değeri geçersiz')}
    populate(state,report,day);const cadence=renderCadence(day);setStatus(cadence==='stale'||cadence==='future'?'stale':'verified',cadence==='stale'?'Kayıt sağlam; günlük koşu gecikti':cadence==='future'?'Gelecek gün kaydı; işlem doğrulanmadı':'GitHub kaydı doğrulandı');
    el('validation').textContent='GitHub’dan okunan genom kontrol noktası ve günlük kayıt, ayrı SHA-256 özetleri, ölçüm tutarlılığı, nüfus kotası ve çoğalması kapalı kontrol grubu ile tarayıcıda denetlendi. Bu denetim bilimsel bağımsız yeniden oynatma değildir.';
    el('integrity').textContent='✓ SHA-256 ve kayıt tutarlı';el('integrity').className='verified-label';
  }catch(err){
    setStatus('error','Doğrulanmış kayıt yok');el('errorDetail').textContent=err?.name==='AbortError'?'Kaynak bağlantısı zaman aşımına uğradı':String(err.message||err);
    el('integrity').textContent='Doğrulama başarısız';el('integrity').className='error-label';
    el('validation').textContent='Kaynak bütünlüğü doğrulanamadı. Eski değerler yeni sonuçmuş gibi kullanılmaz.';el('cadenceStatus').dataset.status='error';el('cadenceStatus').textContent='Güncel koşu değerlendirilemedi: kaynak bütünlüğü doğrulanmadı.';el('requiredDay').textContent='—';el('scheduledNext').textContent='—';
    for(const id of ['population','births','generation','ticks','expBirths','controlBirths'])el(id).textContent='—';el('lineage').setAttribute('hidden','');el('chartEmpty').hidden=false;el('chartEmpty').textContent='Doğrulanmış veriye erişilemedi; hayalî bir nüfus gösterilmiyor.';
  }finally{el('lastRefresh').textContent=new Date().toLocaleTimeString('tr-TR',{timeZone:'Europe/Istanbul'});el('refresh').disabled=false}
}
function dateForTick(tick){if(!Number.isInteger(tick)||tick<8||tick%8!==0)return null;const start=Date.UTC(2026,10,7);return new Date(start+((tick/8)-1)*86400000).toISOString().slice(0,10)}
function populate(state,report,day){
  const m=state.state.metrics;
  el('population').textContent=m.population;el('births').textContent=m.births;el('generation').textContent=m.max_generation;el('ticks').textContent=state.ticks;
  el('dataDate').textContent='Kaydedilmiş son gün: '+formatDate(day)+' (UTC)';el('checkpointDate').textContent=day;el('checkpointHash').textContent=shortHash(state.sha256);el('reportHash').textContent=shortHash(report.sha256);el('capacity').textContent=state.parameters.capacity+' sanal birey';
  el('expBirths').textContent=m.births;el('controlBirths').textContent=report.division_disabled_control.births;
  el('experimentBar').style.width=Math.min(100,100*m.births/Math.max(m.births,1))+'%';el('controlBar').style.width=Math.min(100,100*report.division_disabled_control.births/Math.max(m.births,1))+'%';
  el('dayReportLink').href=`https://github.com/${REPO}/blob/${REF}/research_reports/cano-digital-continuity/daily/${day}.json`;
  drawLineage(state.state.organisms);
}
function svgNode(tag,attrs={}){const n=document.createElementNS(SVG,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));return n}
function drawLineage(organisms){
  const svg=el('lineage');svg.replaceChildren();
  if(!organisms.length){svg.setAttribute('hidden','');el('chartEmpty').hidden=false;el('chartEmpty').textContent='Bu durumda yaşayan dijital organizma bulunamadı.';return}
  const gens=new Map();for(const o of organisms){const a=gens.get(o.generation)||[];a.push(o);gens.set(o.generation,a)}
  const generationValues=[...gens.keys()].sort((a,b)=>a-b),maxGen=Math.max(...generationValues),minGen=Math.min(...generationValues);
  const points=new Map();let largest=0;
  for(const generation of generationValues){const list=gens.get(generation).sort((a,b)=>a.identifier-b.identifier);largest=Math.max(largest,list.length);list.forEach((o,i)=>points.set(o.identifier,{x:65+(generation-minGen)*810/Math.max(1,maxGen-minGen),y:45+(i+1)*285/(list.length+1),o}))}
  for(const o of organisms){if(o.parent===null||!points.has(o.parent))continue;const a=points.get(o.parent),b=points.get(o.identifier);svg.appendChild(svgNode('path',{d:`M ${a.x} ${a.y} C ${(a.x+b.x)/2} ${a.y}, ${(a.x+b.x)/2} ${b.y}, ${b.x} ${b.y}`,fill:'none',stroke:'#4b8383','stroke-width':1.8,opacity:.8}))}
  for(const gen of generationValues){const p=points.get(gens.get(gen)[0].identifier);const x=p.x;const label=svgNode('text',{x,y:24,'text-anchor':'middle',fill:'#8eabb0','font-size':13});label.textContent='Nesil '+gen;svg.appendChild(label)}
  for(const [id,p] of points){const g=svgNode('g');g.appendChild(svgNode('circle',{cx:p.x,cy:p.y,r:20,fill:'#0d3940',stroke:'#62e8d0','stroke-width':1.8}));g.appendChild(svgNode('circle',{cx:p.x,cy:p.y,r:6,fill:'#96ffe5'}));const title=svgNode('title');title.textContent=`Dijital organizma #${id}, nesil ${p.o.generation}, enerji ${p.o.energy}`;g.appendChild(title);const label=svgNode('text',{x:p.x,y:p.y+34,'text-anchor':'middle',fill:'#b6d0cf','font-size':11});label.textContent='#'+id;g.appendChild(label);svg.appendChild(g)}
  svg.removeAttribute('hidden');el('chartEmpty').hidden=true;
}
el('refresh').addEventListener('click',load);
load();setInterval(()=>{if(!document.hidden)load()},90000);
