import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {validate} from '../scripts/schema.mjs';
import {readJson,skillRoot,inside,serve} from '../scripts/lib.mjs';
import {create,build,htmlEscape} from '../scripts/project.mjs';
import {pointOnSegments,flowPoints,cameraAt} from '../runtime/motion.js';
import {speechPlan,speechCredentials,checkWordEvents,azureSynthesize} from '../scripts/tts.mjs';
import {zipFiles,whitelist,audit} from '../scripts/package.mjs';
test('source package is complete, licensed and portable',()=>{
  const names=whitelist();
  assert.ok(names.includes('assets/licenses/three.txt'));
  assert.ok(names.includes('assets/licenses/gsap.txt'));
  assert.ok(!names.some(name=>name.startsWith('evidence/')));
  audit(names);
});
const fixture=()=>readJson(path.join(skillRoot,'examples','service.json'));
const fails=fn=>{const c=fixture();fn(c);assert.throws(()=>validate(c));};
test('both unrelated example topologies validate',()=>{
  validate(fixture());validate(readJson(path.join(skillRoot,'examples','pipeline.json')));
});
test('reject unknown fields, duplicate IDs and missing evidence',()=>{
  fails(c=>c.voice='unexpected');fails(c=>c.nodes[1].id=c.nodes[0].id);
  fails(c=>c.nodes[0].evidence=['missing']);fails(c=>c.nodes[0].detail='x'.repeat(100));
});
test('reject disconnected flows, invalid targets and hidden execution of planned nodes',()=>{
  fails(c=>c.flows[0].edges=['web-api','orders-db']);
  fails(c=>c.camera[0].targets=['absent']);fails(c=>c.nodes[2].status='planned');
  fails(c=>c.flows[0].end=200);fails(c=>c.nodes[1].position=c.nodes[0].position);
});
test('camera boundaries are total, route vertices are continuous and clamped',()=>{
  fails(c=>c.camera[0].time=1);fails(c=>c.camera.at(-1).time=23);
  const points=flowPoints([{points:[[0,0,0],[2,0,0]]},{points:[[2,0,0],[2,2,0]]}]);
  assert.deepEqual(points,[[0,0,0],[2,0,0],[2,2,0]]);
  assert.deepEqual(pointOnSegments(points,.5),[2,0,0]);
  assert.deepEqual(pointOnSegments(points,1.5),[2,2,0]);
  assert.deepEqual(pointOnSegments(points,-1),[0,0,0]);
});
test('source text is not executable HTML',()=>{
  assert.equal(htmlEscape('<x&"'), '&lt;x&amp;&quot;');
});
test('safe static paths reject escapes and HTTP traversal',async()=>{
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'architecture-path-test-'));
  fs.writeFileSync(path.join(dir,'index.html'),'local');
  assert.throws(()=>inside(dir,'../outside'));
  assert.throws(()=>inside(dir,path.resolve(dir,'index.html')));
  const server=await serve(dir,0);
  try{
    const base=`http://127.0.0.1:${server.address().port}`;
    assert.equal(await (await fetch(base+'/')).text(),'local');
    assert.equal((await fetch(base+'/%2e%2e%5csecret')).status,404);
    assert.equal((await fetch(base+'/.env')).status,404);
    assert.equal((await fetch(base+'/',{method:'POST'})).status,405);
  }finally{await new Promise(r=>server.close(r));fs.rmSync(path.join(dir,'index.html'));fs.rmdirSync(dir);}
});
test('narration plan escapes XML and enforces time slots',()=>{
  const p=speechPlan([{start:0,end:2,text:'a < b & "yes"'}],8);
  assert.match(p[0].ssml,/a &lt; b &amp; &quot;yes&quot;/);
  assert.throws(()=>speechPlan([{start:0,end:4,text:'a'},{start:3,end:6,text:'b'}],8));
  assert.throws(()=>speechCredentials({}));
  assert.throws(()=>speechCredentials({AZURE_SPEECH_KEY:'replace-me',AZURE_SPEECH_REGION:'eastus'}));
  assert.throws(()=>checkWordEvents([{start:2,duration:1},{start:1,duration:.1}],4));
});
test('SDK adapter closes resources, returns word times and never exposes key',async()=>{
  let closed=false,receivedVoice;
  const sdk={
    SpeechConfig:{fromSubscription:()=>({})},SpeechSynthesisOutputFormat:{Audio24Khz48KBitRateMonoMp3:1},ResultReason:{SynthesizingAudioCompleted:9},
    SpeechSynthesizer:class{
      constructor(c){receivedVoice=c.speechSynthesisVoiceName;}
      speakSsmlAsync(_,done){this.wordBoundary(null,{text:'词',audioOffset:1000000,duration:2000000,textOffset:0,wordLength:1});done({reason:9,audioData:new Uint8Array(900),audioDuration:10000000});}
      close(){closed=true;}
    }
  };
  const clip=speechPlan([{start:0,end:2,text:'词'}],8)[0];
  const result=await azureSynthesize(sdk,{key:'test-placeholder',region:'eastus'},clip);
  assert(closed);assert.equal(receivedVoice,clip.voice);assert.equal(result.words[0].start,.1);
  assert.equal(result.duration,1);assert(!JSON.stringify(result).includes('test-placeholder'));
});
test('ZIP emits standard local and central headers',()=>{
  const zip=zipFiles([{name:'skill/SKILL.md',data:Buffer.from('skill')}]);
  assert.equal(zip.readUInt32LE(0),0x04034b50);
  assert.equal(zip.readUInt32LE(zip.length-22),0x06054b50);
});
