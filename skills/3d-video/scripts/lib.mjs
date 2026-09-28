import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import {spawn,spawnSync} from 'node:child_process';
export const skillRoot=path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const sha=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
export function readJson(file){return JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''));}
export function writeJson(file,data){fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,JSON.stringify(data,null,2)+'\n');}
export function inside(root,relative){
  if(typeof relative!=='string'||path.isAbsolute(relative)||/^[A-Za-z]:|^[/\\]{2}/.test(relative))throw new Error('Asset must use a project-relative path.');
  const target=path.resolve(root,relative),rel=path.relative(root,target);
  if(rel==='..'||rel.startsWith('..'+path.sep))throw new Error('Path escapes project.');
  if(fs.existsSync(target)){
    const real=fs.realpathSync(target),realRoot=fs.realpathSync(root),r=path.relative(realRoot,real);
    if(r==='..'||r.startsWith('..'+path.sep))throw new Error('Symbolic link escapes project.');
  }
  return target;
}
export function files(root){
  return fs.readdirSync(root,{withFileTypes:true}).sort((a,b)=>a.name.localeCompare(b.name)).flatMap(e=>{
    const p=path.join(root,e.name);
    if(e.isSymbolicLink())throw new Error('Package/project symlink is not permitted: '+e.name);
    return e.isDirectory()?files(p):[p];
  });
}
export function parseOptions(args,allowed){
  const result={};
  for(let i=0;i<args.length;i++){
    const key=args[i].replace(/^--/,'');
    if(!args[i].startsWith('--')||!Object.hasOwn(allowed,key))throw new Error('Unknown option: '+args[i]);
    if(allowed[key]==='flag')result[key]=true;
    else{const value=args[++i];if(!value||value.startsWith('--'))throw new Error('Missing value for --'+key);result[key]=value;}
  }
  return result;
}
export function serve(root,port=4020){
  root=fs.realpathSync(root);
  const types={'.html':'text/html; charset=utf-8','.js':'text/javascript','.mjs':'text/javascript','.css':'text/css','.json':'application/json','.ttf':'font/ttf','.png':'image/png','.jpg':'image/jpeg','.glb':'model/gltf-binary','.hdr':'application/octet-stream','.mp3':'audio/mpeg'};
  const server=http.createServer((request,response)=>{
    if(!['GET','HEAD'].includes(request.method)){response.writeHead(405);response.end();return;}
    try{
      const pathname=decodeURIComponent(new URL(request.url,'http://localhost').pathname);
      const parts=pathname.split(/[\\/]/);
      if(parts.some(p=>p.startsWith('.')&&p!==''))throw new Error('Hidden paths not served');
      const requested=pathname.replace(/^[/\\]+/,'')+(pathname.endsWith('/')?'index.html':'');
      const file=inside(root,requested);
      if(!fs.statSync(file).isFile())throw new Error('not a file');
      const size=fs.statSync(file).size,range=request.headers.range;
      let start=0,end=size-1,status=200;
      if(range){
        const match=/^bytes=(\d+)-(\d*)$/.exec(range);
        if(!match){response.writeHead(416);response.end();return;}
        start=+match[1];end=match[2]?Math.min(+match[2],end):end;status=206;
        if(start>end||start>=size){response.writeHead(416,{'Content-Range':`bytes */${size}`});response.end();return;}
      }
      const headers={'Content-Type':types[path.extname(file)]||'application/octet-stream','Content-Length':end-start+1,'Cache-Control':'no-store','Accept-Ranges':'bytes'};
      if(status===206)headers['Content-Range']=`bytes ${start}-${end}/${size}`;
      response.writeHead(status,headers);
      if(request.method==='HEAD')response.end();else fs.createReadStream(file,{start,end}).on('error',()=>response.destroy()).pipe(response);
    }catch{response.writeHead(404,{'Content-Type':'text/plain'});response.end('Not found');}
  });
  return new Promise((resolve,reject)=>{server.once('error',reject);server.listen(port,'127.0.0.1',()=>resolve(server));});
}
export function run(bin,args,options={}){
  const p=spawnSync(bin,args,{encoding:'utf8',maxBuffer:12*1024*1024,...options});
  if(p.error||p.status!==0)throw new Error(`Command failed: ${path.basename(bin)} ${args[0]||''}\n${p.error?.message||p.stderr?.slice(-2500)||`exit ${p.status}`}`);
  return p.stdout;
}
export function cliPath(){
  const require=createRequire(path.join(skillRoot,'package.json'));
  let manifest;try{manifest=require.resolve('hyperframes/package.json');}catch{throw new Error('Missing local HyperFrames dependency. Run npm ci in the skill directory.');}
  const pkg=readJson(manifest);if(pkg.version!=='0.8.4')throw new Error('Expected pinned HyperFrames0.8.4; restore package-lock with npm ci.');
  return path.resolve(path.dirname(manifest),typeof pkg.bin==='string'?pkg.bin:pkg.bin.hyperframes);
}
export function runCli(args,project,logfile){
  const cli=cliPath();fs.mkdirSync(path.dirname(logfile),{recursive:true});
  return new Promise((resolve,reject)=>{
    const stream=fs.createWriteStream(logfile);
    const child=spawn(process.execPath,[cli,...args],{cwd:project,env:{...process.env,DO_NOT_TRACK:'1',HYPERFRAMES_NO_TELEMETRY:'1',HYPERFRAMES_NO_UPDATE_CHECK:'1'},stdio:['ignore','pipe','pipe']});
    let output='';
    for(const channel of [child.stdout,child.stderr])channel.on('data',data=>{stream.write(data);if(output.length<12*1024*1024)output+=data.toString();});
    child.on('error',e=>{stream.end();reject(e);});
    child.on('close',(code,signal)=>stream.end(()=>resolve({code,signal,output})));
  });
}
export function treeFingerprint(project){
  const list=['architecture.json','index.html','style.css','index.motion.json',...['runtime','assets'].flatMap(d=>files(path.join(project,d)).map(p=>path.relative(project,p)))];
  return crypto.createHash('sha256').update(list.sort().map(p=>`${p.replaceAll(path.sep,'/')}:${sha(path.join(project,p))}`).join('\n')).digest('hex');
}
export function verifyVideo(file,duration,audioExpected=false){
  const probe=JSON.parse(run('ffprobe',['-v','error','-show_streams','-show_format','-of','json',file]));
  const video=probe.streams.find(s=>s.codec_type==='video'),audios=probe.streams.filter(s=>s.codec_type==='audio');
  if(!video||video.width!==1920||video.height!==1080||video.r_frame_rate!=='30/1')throw new Error('Video format mismatch.');
  if(Math.abs(+probe.format.duration-duration)>.1)throw new Error('Video duration mismatch.');
  if(audios.length!==(audioExpected?1:0))throw new Error('Unexpected audio stream count.');
  run('ffmpeg',['-v','error','-i',file,'-f','null','-']);
  return {bytes:fs.statSync(file).size,sha256:sha(file),duration:+probe.format.duration,width:video.width,height:video.height,fps:30,frames:Number(video.nb_frames),audioStreams:audios.length,fullDecode:true};
}
