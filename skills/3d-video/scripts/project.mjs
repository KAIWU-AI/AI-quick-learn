import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {validate} from './schema.mjs';
import {skillRoot,readJson,writeJson,files,inside,parseOptions,serve,runCli,treeFingerprint,verifyVideo,sha} from './lib.mjs';

export const htmlEscape=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function audioMarkup(project,config){
  const manifest=path.join(project,'narration-manifest.json');if(!fs.existsSync(manifest))return '';
  const data=readJson(manifest);
  if(data.status!=='verified'||!Array.isArray(data.clips)||!data.clips.length)throw new Error('Narration receipt is not verified.');
  if(data.scriptSha256!==sha(path.join(project,'narration.json')))throw new Error('Narration script changed; synthesize again before build.');
  let end=0;
  return data.clips.map((clip,i)=>{
    if(!Number.isFinite(clip.start)||!Number.isFinite(clip.duration)||clip.start<end||clip.duration<=0||clip.start+clip.duration>config.duration)throw new Error('Invalid/overlapping narration timing.');
    end=clip.start+clip.duration;
    const local=inside(project,clip.file);
    if(sha(local)!==clip.sha256)throw new Error('Narration audio hash mismatch.');
    return `<audio id="narration-${i}" class="clip" src="${htmlEscape(clip.file.replaceAll('\\','/'))}" data-start="${clip.start}" data-duration="${clip.duration}" data-track-index="10" data-volume="1"></audio>`;
  }).join('\n');
}
export function build(project){
  const config=validate(readJson(path.join(project,'architecture.json')));
  const root=path.join(project,'runtime');
  if(!fs.existsSync(root))throw new Error('Not a scaffolded architecture project. Use create first.');
  const template=fs.readFileSync(path.join(project,'templates','index.html'),'utf8');
  const serialized=JSON.stringify(config).replaceAll('<','\\u003c').replaceAll('\u2028','\\u2028').replaceAll('\u2029','\\u2029');
  const values={TITLE:htmlEscape(config.title),DURATION:String(config.duration),STATUS:config.nodes.some(n=>n.status==='illustrative')?'示例架构':'代码架构',CONFIG:serialized,AUDIO:audioMarkup(project,config)};
  const html=template.replace(/__(TITLE|DURATION|STATUS|CONFIG|AUDIO)__/g,(_,key)=>values[key]);
  fs.writeFileSync(path.join(project,'index.html'),html);
  fs.copyFileSync(path.join(project,'runtime','style.css'),path.join(project,'style.css'));
  fs.mkdirSync(path.join(project,'review'),{recursive:true});
  fs.writeFileSync(path.join(project,'review','index.html'),fs.readFileSync(path.join(project,'templates','review.html'),'utf8').replaceAll('__DURATION__',String(config.duration)));
  writeJson(path.join(project,'index.motion.json'),{duration:config.duration,assertions:[{kind:'staysInFrame',selector:'#header'}]});
  writeJson(path.join(project,'build.json'),{status:'built',title:config.title,duration:config.duration,nodes:config.nodes.length,edges:config.edges.length,flows:config.flows.length,audio:!!values.AUDIO,fingerprint:treeFingerprint(project)});
  return config;
}
export function create(output,example){
  const name=example||'service';
  const source=['service','pipeline'].includes(name)?path.join(skillRoot,'examples',name+'.json'):path.resolve(name);
  validate(readJson(source));
  if(fs.existsSync(output))throw new Error('Output already exists; refusing to overwrite. Use build to continue an existing project.');
  fs.mkdirSync(output,{recursive:true});
  for(const dir of ['assets','runtime','templates'])fs.cpSync(path.join(skillRoot,dir),path.join(output,dir),{recursive:true,errorOnExist:true});
  fs.copyFileSync(source,path.join(output,'architecture.json'));
  fs.copyFileSync(path.join(skillRoot,'examples','architecture-notes.md'),path.join(output,'architecture-notes.md'));
  for(const file of ['ASSETS.md','LICENSES.md'])fs.copyFileSync(path.join(skillRoot,file),path.join(output,file));
  writeJson(path.join(output,'hyperframes.json'),{paths:{assets:'assets',compositions:'compositions'},media:{autoProxy:false}});
  fs.writeFileSync(path.join(output,'.gitignore'),'node_modules/\n.hyperframes/\nrenders/\nqa/\nnarration-audio/\n');
  return build(output);
}
export async function check(project){
  const config=build(project),log=path.join(project,'qa','check.log');
  const result=await runCli(['check',project,'--samples','17','--json'],project,log);
  const first=result.output.indexOf('{\n');
  if(first<0)throw new Error('HyperFrames returned no JSON; inspect qa/check.log');
  let report;try{report=JSON.parse(result.output.slice(first));}catch{throw new Error('Invalid check JSON; inspect qa/check.log');}
  writeJson(path.join(project,'qa','hyperframes-check.json'),report);
  if(!report.ok||result.code!==0)throw new Error('HyperFrames checks failed; inspect qa/hyperframes-check.json');
  writeJson(path.join(project,'qa','checked.json'),{ok:true,fingerprint:treeFingerprint(project),duration:config.duration});
  return report;
}
export async function main(args){
  const command=args[0],options=parseOptions(args.slice(1),{out:'value',example:'value',project:'value',port:'value',approved:'flag',workers:'value'});
  if(command==='create'){
    if(!options.out)throw new Error('create requires --out');
    const output=path.resolve(options.out);create(output,options.example);console.log('Created '+output);return;
  }
  if(!options.project)throw new Error('Specify --project for build/preview/check/render.');
  const project=path.resolve(options.project);
  if(command==='build'){const config=build(project);console.log(`Built ${config.nodes.length} nodes; ${config.duration}s`);return;}
  if(command==='preview'){
    build(project);const port=options.port===undefined?4020:Number(options.port);
    if(!Number.isInteger(port)||port<1024||port>65535)throw new Error('Preview port must be1024..65535.');
    const server=await serve(project,port);console.log(`Preview: http://127.0.0.1:${server.address().port}/review/\nKeep this terminal open. Ctrl+C stops only this server.`);
    for(const signal of ['SIGINT','SIGTERM'])process.once(signal,()=>server.close(()=>process.exit(0)));return;
  }
  if(command==='check'){await check(project);console.log('HyperFrames check passed.');return;}
  if(command==='render'){
    if(!options.approved)throw new Error('Review the current preview first, then pass --approved to render.');
    const target=path.resolve(options.out||path.join(project,'renders','architecture.mp4'));
    if(fs.existsSync(target))throw new Error('Output exists; choose a new --out filename to preserve prior work.');
    await check(project);
    const config=readJson(path.join(project,'architecture.json')),fingerprint=treeFingerprint(project);
    const workers=Number(options.workers||2);if(!Number.isInteger(workers)||workers<1||workers>4)throw new Error('workers must be1..4.');
    fs.mkdirSync(path.dirname(target),{recursive:true});
    const result=await runCli(['render',project,'--fps','30','--quality','high','--workers',String(workers),'--browser-timeout','120','--output',target],project,path.join(project,'qa','render.log'));
    if(result.code!==0)throw new Error(`Renderer exited ${result.code??result.signal}. Output is NOT accepted automatically. See qa/render.log; diagnose and verify any partial file separately.`);
    if(treeFingerprint(project)!==fingerprint)throw new Error('Source changed during rendering.');
    const verification=verifyVideo(target,config.duration,fs.existsSync(path.join(project,'narration-manifest.json')));
    writeJson(path.join(project,'qa','render-verification.json'),{...verification,fingerprint,rendererVersion:'0.8.4',quality:'high',output:path.relative(project,target)});
    console.log(`Rendered ${target}\n${verification.duration}s / 1920x1080 / ${verification.audioStreams?'narrated':'silent'}`);return;
  }
  throw new Error('Commands: create, build, preview, check, render');
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===fs.realpathSync(process.argv[1]))main(process.argv.slice(2)).catch(error=>{console.error(error.message);process.exitCode=1;});
