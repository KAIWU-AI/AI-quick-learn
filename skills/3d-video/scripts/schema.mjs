import fs from 'node:fs';
import {fileURLToPath} from 'node:url';
const text=(maxLength=80)=>({type:'string',minLength:1,maxLength});
const id={...text(48),pattern:'^[a-z][a-z0-9-]*$'};
const number=(minimum,maximum)=>({type:'number',minimum,maximum});
const array=(items,minItems,maxItems)=>({type:'array',items,minItems,maxItems});
const object=(properties,required=Object.keys(properties))=>({type:'object',additionalProperties:false,properties,required});
const evidence=array(id,1,12);
const point=array(number(-40,40),2,2);
export const schema={
  $schema:'https://json-schema.org/draft/2020-12/schema',
  ...object({
    version:{const:1},title:text(48),duration:number(8,180),theme:{enum:['space','light']},
    sources:array(object({id,locator:text(240),note:text(400)}),1,40),
    groups:array(object({id,label:text(24),surface:{enum:['wood','none']}}),1,6),
    nodes:array(object({id,label:text(16),detail:text(32),type:{enum:['client','service','database','agent','gate','cluster','queue','storage']},group:id,position:point,status:{enum:['implemented','planned','illustrative']},evidence}),2,12),
    edges:array(object({id,from:id,to:id,label:text(24),kind:{enum:['request','event','result','planned']},evidence,via:array(array(number(-40,40),3,3),0,10)},['id','from','to','label','kind','evidence']),1,24),
    flows:array(object({id,edges:array(id,1,20),start:number(0,180),end:number(0,180)}),1,24),
    camera:array(object({time:number(0,180),targets:array(id,1,12),yaw:number(-3.14,3.14),pitch:number(.15,1.3),distance:number(10,120)},['time','targets','yaw','pitch']),2,24)
  })
};
export function validate(config){
  const errors=[];
  function visit(value,s,path){
    if(s.const!==undefined&&value!==s.const)errors.push(`${path}: expected ${s.const}`);
    if(s.enum&&!s.enum.includes(value))errors.push(`${path}: expected one of ${s.enum.join(', ')}`);
    if(s.type==='object'){
      if(!value||typeof value!=='object'||Array.isArray(value)){errors.push(`${path}: expected object`);return;}
      for(const key of s.required||[])if(!Object.hasOwn(value,key))errors.push(`${path}.${key}: required`);
      for(const [key,v] of Object.entries(value)){if(!s.properties[key])errors.push(`${path}.${key}: unknown field`);else visit(v,s.properties[key],`${path}.${key}`);}
    }else if(s.type==='array'){
      if(!Array.isArray(value)){errors.push(`${path}: expected array`);return;}
      if(value.length<s.minItems||value.length>s.maxItems)errors.push(`${path}: expected ${s.minItems}..${s.maxItems} items`);
      value.forEach((v,i)=>visit(v,s.items,`${path}[${i}]`));
    }else if(s.type==='string'){
      if(typeof value!=='string'||!value.trim()||value.length>s.maxLength)errors.push(`${path}: invalid or oversized string`);
      else if(s.pattern&&!new RegExp(s.pattern).test(value))errors.push(`${path}: invalid ID`);
    }else if(s.type==='number'&&(typeof value!=='number'||!Number.isFinite(value)||value<s.minimum||value>s.maximum))errors.push(`${path}: number outside ${s.minimum}..${s.maximum}`);
  }
  visit(config,schema,'architecture');
  if(errors.length)throw new Error(errors.join('\n'));
  const lists=['sources','groups','nodes','edges','flows'];
  for(const list of lists){
    const ids=config[list].map(x=>x.id);
    if(new Set(ids).size!==ids.length)errors.push(`${list}: duplicate IDs`);
  }
  const sources=new Set(config.sources.map(s=>s.id)),groups=new Set(config.groups.map(g=>g.id));
  const nodes=new Map(config.nodes.map(n=>[n.id,n])),edges=new Map(config.edges.map(e=>[e.id,e]));
  for(const n of config.nodes){
    if(!groups.has(n.group))errors.push(`${n.id}: missing group`);
    for(const e of n.evidence)if(!sources.has(e))errors.push(`${n.id}: missing evidence ${e}`);
  }
  for(let i=0;i<config.nodes.length;i++)for(let j=i+1;j<config.nodes.length;j++){
    const a=config.nodes[i],b=config.nodes[j];
    if(Math.hypot(a.position[0]-b.position[0],a.position[1]-b.position[1])<5.5)errors.push(`${a.id}/${b.id}: nodes closer than5.5; separate physical models`);
  }
  for(const e of config.edges){
    if(!nodes.has(e.from)||!nodes.has(e.to)||e.from===e.to)errors.push(`${e.id}: invalid endpoints`);
    if([e.from,e.to].some(id=>nodes.get(id)?.status==='planned')&&e.kind!=='planned')errors.push(`${e.id}: planned node requires planned edge`);
    for(const s of e.evidence)if(!sources.has(s))errors.push(`${e.id}: missing evidence ${s}`);
  }
  for(const f of config.flows){
    if(f.end<=f.start||f.end>config.duration)errors.push(`${f.id}: invalid flow window`);
    f.edges.forEach((id,i)=>{
      const e=edges.get(id);if(!e){errors.push(`${f.id}: missing edge ${id}`);return;}
      if(e.kind==='planned')errors.push(`${f.id}: cannot execute planned edge`);
      if(i&&edges.get(f.edges[i-1])?.to!==e.from)errors.push(`${f.id}: disconnected route at ${id}`);
    });
  }
  if(config.camera[0].time!==0||config.camera.at(-1).time!==config.duration)errors.push('camera: must cover0..duration');
  config.camera.forEach((p,i)=>{
    if(i&&p.time<=config.camera[i-1].time)errors.push('camera: non-increasing times');
    for(const id of p.targets)if(!nodes.has(id))errors.push(`camera: missing target ${id}`);
  });
  if(errors.length)throw new Error(errors.join('\n'));
  return config;
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===fs.realpathSync(process.argv[1]))console.log(JSON.stringify(schema,null,2));
