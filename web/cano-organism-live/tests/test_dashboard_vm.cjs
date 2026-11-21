const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
const base=path.resolve(__dirname);const src=fs.readFileSync(path.join(base,'../app.js'),'utf8');
const state=JSON.parse(fs.readFileSync(path.join(base,'fixture/genome-state.json'),'utf8'));
const report=JSON.parse(fs.readFileSync(path.join(base,'fixture/2026-11-07.json'),'utf8'));
class E{constructor(id=''){this.id=id;this.textContent='';this.dataset={};this.style={};this.hidden=false;this.className='';this.children=[];this.attrs={};this.listeners={};this.disabled=false;}addEventListener(k,f){this.listeners[k]=f;}appendChild(x){this.children.push(x);return x;}replaceChildren(){this.children=[];}setAttribute(k,v){this.attrs[k]=v;if(k==='hidden')this.hidden=true;}removeAttribute(k){delete this.attrs[k];if(k==='hidden')this.hidden=false;}getAttribute(k){return this.attrs[k]} }
function test(broken){let nodes=new Map();let logs=[];let dayReqs=0;let stateReqs=0;
 const get=id=>{if(!nodes.has(id))nodes.set(id,new E(id));return nodes.get(id)};
 const doc={getElementById:get,createElementNS(ns,tag){return new E(tag)},hidden:false};
 const fetch=async url=>{
  if(url.endsWith('/genome-state.json')){stateReqs++;return {ok:true,json:async()=>broken?{...state,sha256:'bad'}:state}}
  if(url.endsWith('/daily/2026-11-07.json')){dayReqs++;return {ok:true,json:async()=>report}}
  return {ok:false,status:404}
 };
 const ctx={document:doc,fetch,console,Date,Intl,TextEncoder,crypto:crypto.webcrypto,AbortController,setTimeout,clearTimeout,setInterval:()=>0,URL,Error};
 vm.runInNewContext(src,ctx,{filename:'dashboard.js'});
 return new Promise((resolve,reject)=>{
  let attempts=0;let t=setInterval(()=>{
   attempts++;
   const status=get('statusPill').dataset.status;
   if(status==='verified'||status==='error'){ 
    clearInterval(t);
    try{
     if(broken){if(status!=='error'||get('population').textContent!=='—')throw Error('Tamper not rejected');console.log('tamper negative test PASS: no unverified metrics');}
     else{
      for(const [id,val] of [['population',4],['births',3],['generation',2],['ticks',8],['controlBirths',0]]){
       if(get(id).textContent!==val)throw Error(id+' expected '+val+' got '+get(id).textContent)}
      if(get('lineage').children.filter(x=>x.id==='g').length!==4)throw Error('lineage count mismatch');
      if(get('integrity').textContent!=='✓ SHA-256 ve kayıt tutarlı')throw Error('integrity string mismatch');
      if(get('statusPill').dataset.status!=='verified')throw Error('not verified');
      console.log('valid snapshot PASS: population=4, births=3, tick=8, 4 lineage nodes, SHA verified')
     }resolve()}
    catch(e){reject(e)}
   }
   if(attempts>=50){clearInterval(t);reject(Error('did not settle. status '+status+' detail '+get('errorDetail').textContent))}
  },40)
 })
}
(async()=>{await test(false);await test(true)})().catch(e=>{console.error(e);process.exit(1)})
