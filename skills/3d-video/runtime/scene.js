import * as THREE from '../assets/vendor/three.module.min.js';
import {GLTFLoader} from '../assets/vendor/loaders/GLTFLoader.js';
import {HDRLoader} from '../assets/vendor/loaders/HDRLoader.js';
import {createComponent} from './components.js';
import {createBackground} from './background.js';
import {cameraAt,clamp,smooth,pointOnSegments,flowPoints,labelTrack} from './motion.js';

export async function initialize(config){
  const width=1920,height=1080;
  const renderer=new THREE.WebGLRenderer({canvas:document.querySelector('#world'),antialias:true,alpha:true,preserveDrawingBuffer:true});
  renderer.setSize(width,height,false);renderer.setPixelRatio(1);renderer.setClearColor(0,0);
  renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=1.08;
  renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFShadowMap;
  const stage=new THREE.Scene(),camera=new THREE.PerspectiveCamera(39,width/height,.1,200);
  stage.add(new THREE.HemisphereLight(0xffffff,0x807b97,1.2));
  const sun=new THREE.DirectionalLight(0xffffff,2.4);sun.position.set(-12,22,18);sun.castShadow=true;
  Object.assign(sun.shadow.camera,{left:-45,right:45,top:45,bottom:-45,near:1,far:100});sun.shadow.mapSize.set(2048,2048);sun.shadow.bias=-.001;stage.add(sun);
  const textureLoader=new THREE.TextureLoader();
  const [monitor,hdr,woodMap,roughMap,normalMap]=await Promise.all([
    new GLTFLoader().loadAsync('assets/models/computerScreen.glb'),
    new HDRLoader().loadAsync('assets/hdri/studio.hdr'),
    textureLoader.loadAsync('assets/textures/walnut/color.jpg'),
    textureLoader.loadAsync('assets/textures/walnut/roughness.jpg'),
    textureLoader.loadAsync('assets/textures/walnut/normal.jpg'),
    document.fonts.ready
  ]);
  woodMap.colorSpace=THREE.SRGBColorSpace;
  for(const t of [woodMap,roughMap,normalMap]){t.wrapS=t.wrapT=THREE.RepeatWrapping;t.repeat.set(2,1);t.anisotropy=4;}
  const pmrem=new THREE.PMREMGenerator(renderer);stage.environment=pmrem.fromEquirectangular(hdr).texture;stage.environmentIntensity=.6;hdr.dispose();pmrem.dispose();
  const materials={
    white:new THREE.MeshPhysicalMaterial({color:0xf6f4fa,roughness:.3,metalness:.1,clearcoat:.55}),
    dark:new THREE.MeshStandardMaterial({color:0x34323f,roughness:.4,metalness:.3}),
    metal:new THREE.MeshStandardMaterial({color:0xbfc3d0,roughness:.3,metalness:.65}),
    gold:new THREE.MeshStandardMaterial({color:0xc6a27d,roughness:.3,metalness:.65}),
    accent:new THREE.MeshPhysicalMaterial({color:0x9873d0,roughness:.25,metalness:.2,clearcoat:.6}),
    event:new THREE.MeshPhysicalMaterial({color:0xd6a064,roughness:.28,metalness:.15}),
    result:new THREE.MeshPhysicalMaterial({color:0x69b2aa,roughness:.25,metalness:.2})
  };
  const ground=new THREE.Mesh(new THREE.PlaneGeometry(160,160),new THREE.ShadowMaterial({opacity:config.theme==='space'?.20:.12}));
  ground.rotation.x=-Math.PI/2;ground.position.y=-.43;ground.receiveShadow=true;stage.add(ground);
  const nodes=new Map(),groupEntries=[];
  for(const node of config.nodes){
    const component=createComponent(THREE,node.type,{materials,monitor:monitor.scene,title:node.label});
    component.root.position.set(node.position[0],0,node.position[1]);component.root.name=node.id;
    if(node.status==='planned')component.root.traverse(m=>{if(m.isMesh){m.material=m.material.clone();m.material.transparent=true;m.material.opacity=.55;}});
    stage.add(component.root);
    const label=document.createElement('div');label.className='node-label';label.id=`label-${node.id}`;
    const title=document.createElement('b');title.textContent=node.label;const detail=document.createElement('span');detail.textContent=node.detail;
    label.append(title,detail);
    if(node.status==='planned'){const planned=document.createElement('i');planned.textContent='规划';label.append(planned);}
    document.querySelector('#labels').append(label);
    nodes.set(node.id,{...node,...component,label});
  }
  for(const group of config.groups){
    const members=config.nodes.filter(n=>n.group===group.id);if(!members.length)continue;
    const minX=Math.min(...members.map(n=>n.position[0]))-2.9,maxX=Math.max(...members.map(n=>n.position[0]))+2.9;
    const minZ=Math.min(...members.map(n=>n.position[1]))-2.5,maxZ=Math.max(...members.map(n=>n.position[1]))+2.5;
    const w=maxX-minX,d=maxZ-minZ;
    const mat=group.surface==='wood'?new THREE.MeshPhysicalMaterial({map:woodMap,roughnessMap:roughMap,normalMap:normalMap,normalScale:new THREE.Vector2(.1,.1),roughness:.52,clearcoat:.2}):new THREE.MeshStandardMaterial({color:config.theme==='space'?0x616982:0xc4ceda,transparent:true,opacity:.20,roughness:.7});
    const plate=new THREE.Mesh(new THREE.BoxGeometry(w,.22,d),mat);plate.position.set((maxX+minX)/2,-.18,(maxZ+minZ)/2);plate.receiveShadow=true;stage.add(plate);
    const outline=new THREE.LineSegments(new THREE.EdgesGeometry(plate.geometry),new THREE.LineBasicMaterial({color:0xa49eae,transparent:true,opacity:.35}));outline.position.copy(plate.position);stage.add(outline);
    groupEntries.push({id:group.id,label:group.label});
  }
  const color={request:0xa685dc,event:0xe0aa74,result:0x76c3b4,planned:0xa7a8b5};
  const edges=new Map();
  for(const edge of config.edges){
    const a=nodes.get(edge.from),b=nodes.get(edge.to);
    const start=[a.position[0],a.portHeight,a.position[1]],end=[b.position[0],b.portHeight,b.position[1]];
    const points=[start,...(edge.via||[]),end];
    const curve=new THREE.CurvePath();
    for(let i=1;i<points.length;i++)curve.add(new THREE.LineCurve3(new THREE.Vector3(...points[i-1]),new THREE.Vector3(...points[i])));
    const route=new THREE.Line(new THREE.BufferGeometry().setFromPoints(points.map(p=>new THREE.Vector3(...p))),edge.kind==='planned'?new THREE.LineDashedMaterial({color:color.planned,dashSize:.3,gapSize:.2,transparent:true,opacity:.6}):new THREE.LineBasicMaterial({color:0xaba4bd,transparent:true,opacity:.55}));
    route.computeLineDistances();stage.add(route);
    const arrow=new THREE.Mesh(new THREE.ConeGeometry(.095,.26,10),new THREE.MeshStandardMaterial({color:color[edge.kind]}));
    arrow.position.copy(curve.getPoint(.76));arrow.quaternion.setFromUnitVectors(new THREE.Vector3(0,1,0),curve.getTangent(.76));stage.add(arrow);
    edges.set(edge.id,{...edge,points,curve,route});
  }
  const flows=config.flows.map(flow=>{
    const chain=flow.edges.map(id=>edges.get(id)),points=flowPoints(chain),kind=chain[0].kind;
    const mesh=new THREE.Mesh(kind==='event'?new THREE.OctahedronGeometry(.22):new THREE.BoxGeometry(.30,.24,.30),new THREE.MeshPhysicalMaterial({color:color[kind],roughness:.23,metalness:.15,emissive:color[kind],emissiveIntensity:.3}));
    mesh.name=flow.id;stage.add(mesh);
    const tail=Array.from({length:5},(_,i)=>{const m=new THREE.Mesh(new THREE.SphereGeometry(.053-i*.006,8,8),new THREE.MeshBasicMaterial({color:color[kind],transparent:true,opacity:.6-i*.1}));stage.add(m);return m;});
    return {...flow,mesh,tail,points,chain};
  });
  const poses=config.camera.map(p=>{
    const targets=p.targets.map(id=>nodes.get(id).position);
    const minX=Math.min(...targets.map(p=>p[0])),maxX=Math.max(...targets.map(p=>p[0])),minZ=Math.min(...targets.map(p=>p[1])),maxZ=Math.max(...targets.map(p=>p[1]));
    return {...p,target:[(minX+maxX)/2,1.25,(minZ+maxZ)/2],distance:p.distance||Math.max(22,Math.hypot(maxX-minX,maxZ-minZ)*1.5+16)};
  });
  function apply(time){
    const t=clamp(time,0,config.duration),pose=cameraAt(poses,t),target=new THREE.Vector3(...pose.target);
    camera.position.set(target.x+Math.sin(pose.yaw)*Math.cos(pose.pitch)*pose.distance,target.y+Math.sin(pose.pitch)*pose.distance,target.z+Math.cos(pose.yaw)*Math.cos(pose.pitch)*pose.distance);
    camera.lookAt(target);camera.updateMatrixWorld(true);
    for(const node of nodes.values()){
      const active=flows.some(f=>t>=f.start&&t<=f.end&&f.chain.some(e=>e.from===node.id||e.to===node.id));
      node.renderAt(t,active?1:0,1);
    }
    for(const f of flows){
      const active=t>=f.start&&t<=f.end,u=clamp((t-f.start)/(f.end-f.start));
      f.mesh.visible=active;f.mesh.position.fromArray(pointOnSegments(f.points,u));f.mesh.rotation.y=t*.65;
      f.tail.forEach((m,i)=>{const v=u-(i+1)*.008;m.visible=active&&v>0;m.position.fromArray(pointOnSegments(f.points,clamp(v)));});
    }
    stage.updateMatrixWorld(true);return t;
  }
  const projector=new THREE.Vector3();
  const labelEntries=[...nodes.values()];
  const labelsAt=labelTrack(config.duration,time=>{
    apply(time);
    return labelEntries.map(n=>{
      n.anchor.getWorldPosition(projector);
      const distance=projector.distanceTo(camera.position);projector.project(camera);
      const x=(projector.x*.5+.5)*width,y=(-projector.y*.5+.5)*height;
      const fade=smooth(-60,90,x)*(1-smooth(1810,1980,x))*smooth(25,120,y)*(1-smooth(925,1120,y));
      return {id:n.id,x:clamp(x-110,36,1664),y:clamp(y-65,100,922),alpha:fade*(.76+.24*(1-smooth(22,70,distance)))*(projector.z<1?1:0)};
    });
  });
  const background=createBackground(document.querySelector('#backdrop'),config.theme);
  const status=document.querySelector('#flow-status');
  function renderAt(time){
    const t=apply(time);background(t);
    const labels=labelsAt(t);
    labels.forEach((s,i)=>{const el=labelEntries[i].label;el.style.transform=`translate(${s.x}px,${s.y}px)`;el.style.opacity=String(s.alpha);});
    const active=flows.find(f=>t>=f.start&&t<=f.end);
    status.textContent=active?active.chain.map(e=>e.label).join(' → '):config.title;
    renderer.render(stage,camera);
    window.architectureState={time:t,camera:camera.position.toArray(),labels,groups:groupEntries,nodes:[...nodes.values()].map(n=>({id:n.id,uuid:n.root.uuid,status:n.status})),flows:flows.map(f=>({id:f.id,uuid:f.mesh.uuid,visible:f.mesh.visible,position:f.mesh.position.toArray()})),audioCount:document.querySelectorAll('audio').length};
  }
  const driver={t:0},tl=gsap.timeline({paused:true});
  tl.to(driver,{t:config.duration,duration:config.duration,ease:'none',onUpdate:()=>renderAt(driver.t)},0);
  window.addEventListener('hf-seek',event=>renderAt(event.detail.time));
  window.renderArchitectureAt=time=>{tl.seek(time,false);renderAt(time);};
  window.architectureTimeline=tl;
  renderAt(0);return {timeline:tl};
}
