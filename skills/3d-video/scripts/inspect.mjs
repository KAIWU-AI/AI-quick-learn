import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {build} from './project.mjs';
import {parseOptions,serve,writeJson,treeFingerprint} from './lib.mjs';
import {PNG} from 'pngjs';
import puppeteer from 'puppeteer-core';

export function browserPath(){
  const choices=[process.env.CHROME_PATH];
  if(process.platform==='win32'){
    for(const base of [process.env.PROGRAMFILES,process.env['PROGRAMFILES(X86)'],process.env.LOCALAPPDATA].filter(Boolean))
      for(const rest of [['Microsoft','Edge','Application','msedge.exe'],['Google','Chrome','Application','chrome.exe']])choices.push(path.join(base,...rest));
  }else if(process.platform==='darwin')choices.push('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome','/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge');
  else choices.push('/usr/bin/chromium','/usr/bin/chromium-browser','/usr/bin/google-chrome');
  const found=choices.find(p=>p&&fs.existsSync(p));if(!found)throw new Error('Set CHROME_PATH to an installed Chromium/Chrome/Edge executable.');return found;
}
export async function inspect(project){
  const config=build(project),server=await serve(project,0);
  let browser;
  const rootUrl=`http://127.0.0.1:${server.address().port}`;
  const qa=path.join(project,'qa');fs.mkdirSync(qa,{recursive:true});
  const errors=[],requests=[],samples=[];
  try{
    browser=await puppeteer.launch({executablePath:browserPath(),headless:true,args:['--hide-scrollbars']});
    const page=await browser.newPage();await page.setViewport({width:1920,height:1080,deviceScaleFactor:1});
    page.on('pageerror',error=>errors.push(error.message));
    page.on('request',r=>{const u=r.url();if(!u.startsWith(rootUrl)&&!u.startsWith('data:')&&!u.startsWith('blob:'))requests.push(new URL(u).origin);});
    await page.goto(rootUrl+'/',{waitUntil:'networkidle0'});
    await page.waitForFunction(()=>window.architectureReady||window.architectureFailure,{timeout:60000});
    const error=await page.evaluate(()=>window.architectureFailure);if(error)throw new Error(error);
    const sample=async t=>page.evaluate(t=>{
      window.renderArchitectureAt(t);
      const s=window.architectureState;
      const textErrors=[];
      for(const el of document.querySelectorAll('.node-label b,.node-label span')){
        const parent=el.closest('.node-label');if(+parent.style.opacity<.5)continue;
        if(el.scrollWidth>el.clientWidth+2||el.scrollHeight>el.clientHeight+3)textErrors.push(el.textContent);
      }
      return {...s,textErrors,videoCount:document.querySelectorAll('video').length};
    },t);
    const initial=await sample(0);const nodeIds=initial.nodes.map(n=>n.uuid).join(',');
    for(let t=0;t<=config.duration;t+=.5){
      const s=await sample(t);samples.push(s);
      if(s.nodes.map(n=>n.uuid).join(',')!==nodeIds)errors.push('Scene rebuilt its nodes.');
      if(s.videoCount)errors.push('Unexpected avatar/footage video element.');
      if(s.textErrors.length)errors.push(`Text overflow at ${t}: ${s.textErrors.join(',')}`);
    }
    for(const f of config.flows){
      let uuid;for(const t of [f.start+.01,(f.start+f.end)/2,f.end-.01]){
        const s=await sample(t),flow=s.flows.find(x=>x.id===f.id);
        if(!flow.visible)errors.push(`Flow ${f.id} vanishes during travel.`);
        if(uuid&&flow.uuid!==uuid)errors.push(`Flow ${f.id} changes identity.`);uuid=flow.uuid;
      }
    }
    const times=[0.2,config.duration*.22,config.duration*.48,config.duration*.73,config.duration-.15];
    for(let i=0;i<times.length;i++){await sample(times[i]);await page.screenshot({path:path.join(qa,`frame-${i+1}.png`)});}
    const proof=config.duration*.48;
    const canonical=s=>JSON.stringify({camera:s.camera,labels:s.labels,flows:s.flows.map(({uuid,...f})=>f)});
    const a=canonical(await sample(proof)),imageA=PNG.sync.read(await page.screenshot());
    await sample(config.duration);await sample(0);const b=canonical(await sample(proof));
    if(a!==b)errors.push('Reverse-seek state differs.');
    await page.reload({waitUntil:'networkidle0'});await page.waitForFunction(()=>window.architectureReady,{timeout:60000});
    const c=canonical(await sample(proof)),imageB=PNG.sync.read(await page.screenshot());
    if(a!==c)errors.push('Fresh-load state differs.');
    let changed=0,max=0;for(let i=0;i<imageA.data.length;i+=4){let diff=false;for(let j=0;j<3;j++){const d=Math.abs(imageA.data[i+j]-imageB.data[i+j]);max=Math.max(max,d);if(d)diff=true;}if(diff)changed++;}
    const ratio=changed/(1920*1080);
    if(max>2||ratio>.001)errors.push(`Fresh-load pixels differ beyond tiny GPU rounding: max${max},ratio${ratio}`);
    await page.goto(rootUrl+'/review/',{waitUntil:'networkidle0'});await page.waitForFunction(()=>!document.querySelector('#play').disabled,{timeout:60000});
    await page.click('#play');await page.waitForFunction(()=>Number(document.querySelector('#seek').value)>.15);
    await page.click('#play');
    const report={ok:!errors.length&&!requests.length,errors:[...new Set(errors)],unexpectedNetworkOrigins:[...new Set(requests)],sampleCount:samples.length,proofTime:proof,reverseSeek:true,freshLoadState:a===c,pixels:{changed,maxChannelDifference:max,changedFraction:ratio},audioStreams:initial.audioCount,videoElements:initial.videoCount,previewControls:'play/pause verified',fingerprint:treeFingerprint(project)};
    writeJson(path.join(qa,'browser-check.json'),report);writeJson(path.join(qa,'sample-states.json'),samples);
    if(!report.ok)throw new Error(JSON.stringify(report,null,2));
    console.log(`Browser verified ${samples.length} states; ${config.nodes.length} persistent nodes; local assets only.`);return report;
  }finally{if(browser)await browser.close();await new Promise(resolve=>server.close(resolve));}
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===fs.realpathSync(process.argv[1])){
  const options=parseOptions(process.argv.slice(2),{project:'value'});
  if(!options.project)throw new Error('Specify --project');
  inspect(path.resolve(options.project)).catch(e=>{console.error(e.message);process.exitCode=1;});
}
