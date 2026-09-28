import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import {fileURLToPath} from 'node:url';
import {skillRoot,files,readJson,writeJson,sha,parseOptions} from './lib.mjs';
export const includeRoots=['SKILL.md','README.md','LICENSES.md','ASSETS.md','package.json','package-lock.json','.gitignore','.gitattributes','architecture.schema.json','assets','runtime','scripts','templates','references','examples','tests'];
export function whitelist(){
  return includeRoots.flatMap(name=>{
    const p=path.join(skillRoot,name);if(!fs.existsSync(p))throw new Error('Missing package payload '+name);
    return fs.statSync(p).isDirectory()?files(p):[p];
  }).map(p=>path.relative(skillRoot,p).split(path.sep).join('/')).sort();
}
export function audit(names){
  const forbidden=/(?:^|\/)(?:node_modules|\.env(?:\.|$)|__pycache__|\.hyperframes|work|credentials)(?:\/|$)|\.(?:pyc|pem|key)$/i;
  const privatePath=/(?:[A-Za-z]:[\\/]+Users[\\/]+|\/Users\/|\/home\/)[A-Za-z0-9_-]+/;
  const secret=/-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|(?:ghp|github_pat)_[A-Za-z0-9_]{30,}|sk-[A-Za-z0-9]{40,}/;
  for(const name of names){
    if(forbidden.test(name))throw new Error('Forbidden package file '+name);
    const file=path.join(skillRoot,name),bytes=fs.readFileSync(file);
    const text=bytes.toString('utf8');
    if(privatePath.test(text)||secret.test(text))throw new Error('Private path or secret-shaped content in '+name);
    if(name.endsWith('.json'))JSON.parse(text);
  }
  for(const name of names.filter(n=>n.endsWith('.md'))){
    const text=fs.readFileSync(path.join(skillRoot,name),'utf8');
    for(const match of text.matchAll(/\]\((?:<([^>]+)>|([^)\s]+))\)/g)){
      const link=match[1]||match[2];if(/^[a-z]+:|^#/.test(link))continue;
      const target=path.resolve(skillRoot,path.dirname(name),decodeURIComponent(link.split('#')[0]).replaceAll('\\',path.sep));
      if(!fs.existsSync(target))throw new Error(`Broken link ${name}: ${link}`);
    }
  }
}
function crc32(bytes){
  let crc=0xffffffff;for(const b of bytes){crc^=b;for(let k=0;k<8;k++)crc=(crc>>>1)^((crc&1)?0xedb88320:0);}return (crc^0xffffffff)>>>0;
}
export function zipFiles(entries){
  const bodies=[],directory=[];let offset=0;
  for(const {name,data} of entries){
    const filename=Buffer.from(name),compressed=zlib.deflateRawSync(data,{level:9}),crc=crc32(data);
    const local=Buffer.alloc(30);local.writeUInt32LE(0x04034b50,0);local.writeUInt16LE(20,4);local.writeUInt16LE(0x800,6);local.writeUInt16LE(8,8);local.writeUInt16LE(0x21,12);local.writeUInt32LE(crc,14);local.writeUInt32LE(compressed.length,18);local.writeUInt32LE(data.length,22);local.writeUInt16LE(filename.length,26);
    bodies.push(local,filename,compressed);
    const central=Buffer.alloc(46);central.writeUInt32LE(0x02014b50,0);central.writeUInt16LE(20,4);central.writeUInt16LE(20,6);central.writeUInt16LE(0x800,8);central.writeUInt16LE(8,10);central.writeUInt16LE(0x21,14);central.writeUInt32LE(crc,16);central.writeUInt32LE(compressed.length,20);central.writeUInt32LE(data.length,24);central.writeUInt16LE(filename.length,28);central.writeUInt32LE(offset,42);directory.push(central,filename);
    offset+=local.length+filename.length+compressed.length;
  }
  const central=Buffer.concat(directory),end=Buffer.alloc(22);end.writeUInt32LE(0x06054b50,0);end.writeUInt16LE(entries.length,8);end.writeUInt16LE(entries.length,10);end.writeUInt32LE(central.length,12);end.writeUInt32LE(offset,16);
  return Buffer.concat([...bodies,central,end]);
}
export function seal(){
  const names=whitelist();audit(names);
  const manifest={version:1,name:'3d-video',files:names.map(name=>({path:name,bytes:fs.statSync(path.join(skillRoot,name)).size,sha256:sha(path.join(skillRoot,name))}))};
  writeJson(path.join(skillRoot,'bundle-manifest.json'),manifest);return manifest;
}
export function verify(){
  const manifest=readJson(path.join(skillRoot,'bundle-manifest.json')),names=whitelist();
  audit(names);
  if(JSON.stringify(names)!==JSON.stringify(manifest.files.map(f=>f.path)))throw new Error('Package file set drifted; reseal after review.');
  for(const item of manifest.files)if(sha(path.join(skillRoot,item.path))!==item.sha256)throw new Error('Package hash changed: '+item.path);
  console.log(`Verified ${names.length} whitelisted files; references, licenses and hashes intact.`);return manifest;
}
function main(args){
  const operation=args[0],options=parseOptions(args.slice(1),{out:'value'});
  if(operation==='seal'){seal();verify();return;}
  if(operation==='verify'){verify();return;}
  if(operation==='zip'){
    if(!options.out)throw new Error('zip requires --out');
    const manifest=verify(),output=path.resolve(options.out);
    if(fs.existsSync(output))throw new Error('ZIP already exists; choose another output.');
    fs.mkdirSync(path.dirname(output),{recursive:true});
    const names=[...manifest.files.map(f=>f.path),'bundle-manifest.json'];
    fs.writeFileSync(output,zipFiles(names.map(name=>({name:'3d-video/'+name,data:fs.readFileSync(path.join(skillRoot,name))}))));
    fs.writeFileSync(output+'.sha256',sha(output)+'  '+path.basename(output)+'\n');
    console.log(`ZIP: ${output}\nFiles: ${names.length}; SHA256: ${sha(output)}`);return;
  }
  throw new Error('package commands: seal | verify | zip --out file.zip');
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===fs.realpathSync(process.argv[1]))try{main(process.argv.slice(2));}catch(e){console.error(e.message);process.exitCode=1;}
