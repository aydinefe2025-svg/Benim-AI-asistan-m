const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const html=fs.readFileSync(path.join(__dirname,'CANO_EPS_operating_simulator.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements=new Map(), ctx={clearRect(){},beginPath(){},moveTo(){},lineTo(){},stroke(){}};
let exported, interval, downloads=0;
const el=id=>{if(!elements.has(id))elements.set(id,{value:'baseline',textContent:'',getContext:()=>ctx});return elements.get(id)};
const sandbox={module:{exports:{}},document:{getElementById:el,createElement:()=>({click(){downloads++}})},Blob:class {constructor(parts){exported=JSON.parse(parts.join(''))}},URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},setInterval(fn){interval=fn;return 1},clearInterval(){interval=null},setTimeout(fn){fn()}};
vm.runInNewContext(script,sandbox);
const {newMonitor,advance,inject}=sandbox.module.exports, base=[260,260,9,9,800];
let checks=0;function check(b){assert.ok(b);checks++}
const m=newMonitor();check(advance(m,base).state==='NORMAL');
for(let i=0;i<4;i++)check(advance(m,inject(base,'loss')).state==='WATCH');check(advance(m,inject(base,'loss')).state==='ALARM');
for(const k of ['dropout','negative','night','overflow','zero'])check(advance(m,inject(base,k)).state==='UNAVAILABLE');check(advance(m,inject(base,'recovery')).state==='NORMAL');
check(base[3]===9);check(advance(m,[1,1,1,1,200]).state==='NORMAL');
let seed=19,streak=0;const state=newMonitor();const scenarios=['baseline','loss','open','dropout','night','negative','overflow','zero','recovery'];for(let i=0;i<100000;i++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;const k=scenarios[seed%scenarios.length];const valid=['baseline','loss','open','recovery'].includes(k);streak=valid&&['loss','open'].includes(k)?streak+1:0;const expected=!valid?'UNAVAILABLE':streak>=5?'ALARM':streak?'WATCH':'NORMAL';const r=advance(state,inject(base,k));assert.equal(r.state,expected);assert.equal(r.control,'DISABLED');assert.equal(r.position,i+1)}checks++;
el('fault').value='open';el('run').onclick();check(typeof interval==='function');for(let i=0;i<5;i++)interval();check(el('state').textContent==='ALARM');el('pause').onclick();check(interval===null);el('fault').value='dropout';el('step').onclick();check(el('state').textContent==='UNAVAILABLE');el('save').onclick();check(downloads===1&&exported.events.length===6&&exported.events.every(e=>e.control==='DISABLED'));el('reset').onclick();check(el('state').textContent==='HAZIR'&&interval===null);el('save').onclick();check(exported.events.length===0);console.log(JSON.stringify({checks,randomized_steps:100000,failures:0,mode:'JS engine with DOM stubs; not full browser or hardware'}));
