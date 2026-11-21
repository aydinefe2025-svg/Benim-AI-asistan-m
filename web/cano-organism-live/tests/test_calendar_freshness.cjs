'use strict';
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'..','app.js'),'utf8');
const cutoff=src.indexOf("\nel('refresh').addEventListener('click',load);");
assert.ok(cutoff>0,'Expected browser bootstrap');
const context={Date,Intl,Error,Number,Object,Math,String,Set,Map,JSON,RegExp};
vm.runInNewContext(src.slice(0,cutoff)+"\n;globalThis.testCadence=calendarWindow;",context);
const check=context.testCadence;
const at=(d,h,m)=>Date.UTC(2026,10,d,h,m);
const test=(day,now,level,required,next)=>{
  const r=check(day,now);
  assert.equal(r.level,level);assert.equal(r.requiredDay,required);
  assert.equal(r.nextRunISO,next);
};
// Seed state is valid, but the future scheduled run must not be claimed complete.
test('2026-11-07',at(7,21,15),'current','2026-11-07','2026-11-08T05:47:00.000Z');
// Before tomorrow's slot the previous UTC-day archive is expected.
test('2026-11-07',at(8,5,46),'current','2026-11-07','2026-11-08T05:47:00.000Z');
// Grace period: GitHub runners may start late.
test('2026-11-07',at(8,5,48),'pending','2026-11-07','2026-11-09T05:47:00.000Z');
// After grace: still correct SHA does not mean a healthy scheduled loop.
test('2026-11-07',at(8,7,47),'stale','2026-11-08','2026-11-09T05:47:00.000Z');
// When next daily archive is present the scheduler date is current.
test('2026-11-08',at(8,8,0),'current','2026-11-08','2026-11-09T05:47:00.000Z');
// Pretending to have tomorrow's run early must not be called fresh.
test('2026-11-08',at(8,5,46),'future','2026-11-07','2026-11-08T05:47:00.000Z');
assert.throws(()=>check('2026-11-99',at(8,8,0)),/Invalid record date/);
assert.throws(()=>check('2026-11-08',at(6,0,0)),/Invalid clock/);
console.log('calendar freshness: eight cases PASS');
