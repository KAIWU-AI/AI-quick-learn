export function createComponent(THREE,type,{materials,monitor,title}){
  const root=new THREE.Group(),animated=[];
  function block(w,h,d,material,x=0,y=h/2,z=0){
    const shape=new THREE.Shape(),r=Math.min(.10,w/6,d/6);
    shape.moveTo(-w/2+r,-d/2);shape.lineTo(w/2-r,-d/2);shape.quadraticCurveTo(w/2,-d/2,w/2,-d/2+r);
    shape.lineTo(w/2,d/2-r);shape.quadraticCurveTo(w/2,d/2,w/2-r,d/2);shape.lineTo(-w/2+r,d/2);
    shape.quadraticCurveTo(-w/2,d/2,-w/2,d/2-r);shape.lineTo(-w/2,-d/2+r);shape.quadraticCurveTo(-w/2,-d/2,-w/2+r,-d/2);
    const geo=new THREE.ExtrudeGeometry(shape,{depth:h,bevelEnabled:true,bevelSize:.022,bevelThickness:.022,bevelSegments:2,curveSegments:5});
    geo.translate(0,0,-h/2);geo.rotateX(-Math.PI/2);
    const mesh=new THREE.Mesh(geo,material);mesh.position.set(x,y,z);mesh.castShadow=true;mesh.receiveShadow=true;root.add(mesh);return mesh;
  }
  function disc(radius,h,material,y){
    const mesh=new THREE.Mesh(new THREE.CylinderGeometry(radius,radius,h,48),material);
    mesh.position.y=y;mesh.castShadow=true;mesh.receiveShadow=true;root.add(mesh);return mesh;
  }
  const base=block(type==='client'?5:3.5,.16,type==='client'?3.1:3.3,materials.white);
  let labelHeight=3.0;
  if(type==='client'){
    const screen=monitor.clone(true);screen.scale.setScalar(11.8);screen.position.set(-.196344*11.8,.18,.052*11.8-.3);
    screen.traverse(mesh=>{if(mesh.isMesh){mesh.castShadow=true;mesh.receiveShadow=true;mesh.material=Array.isArray(mesh.material)?mesh.material.map(m=>m.clone()):mesh.material.clone();}});
    root.add(screen);
    const canvas=document.createElement('canvas');canvas.width=768;canvas.height=480;
    const ctx=canvas.getContext('2d');ctx.fillStyle='#f6f5fa';ctx.fillRect(0,0,768,480);ctx.fillStyle='#27283e';
    ctx.font='600 45px ArchitectureSans';ctx.fillText(title,54,91);
    for(let i=0;i<4;i++){ctx.fillStyle=i===0?'#a78ada':'#ded9ea';ctx.fillRect(55,145+i*64,550-i*43,30);}
    ctx.fillStyle='#756099';ctx.fillRect(548,409,135,32);
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
    const face=new THREE.Mesh(new THREE.PlaneGeometry(4.40,2.75),new THREE.MeshBasicMaterial({map:texture,toneMapped:false}));
    face.position.set(0,.17128*11.8+.18,-.297);face.rotation.x=-Math.atan(.03252/.23138);root.add(face);
    labelHeight=4.25;
  }else if(type==='service'){
    for(let i=0;i<3;i++){block(2.35,.53,1.9,materials.white,0,.54+i*.63);block(1.86,.12,.045,materials.dark,0,.59+i*.63,.982);}
    labelHeight=2.8;
  }else if(type==='database'){
    for(let i=0;i<4;i++){disc(1.02,.32,i===3?materials.accent:materials.metal,.43+i*.46);disc(1.04,.038,materials.white,.60+i*.46);}
  }else if(type==='agent'){
    for(let i=0;i<3;i++)animated.push(block(2.5-i*.2,.23,2.5-i*.2,i===2?materials.accent:materials.dark,0,.40+i*.35));
    for(let i=0;i<10;i++)for(const side of [-1,1])block(.1,.06,.35,materials.gold,-1.08+i*.24,.37,side*1.48);
    const ring=new THREE.Mesh(new THREE.TorusGeometry(1.67,.026,8,64,Math.PI*1.7),materials.accent);ring.rotation.x=Math.PI/2;ring.position.y=.22;root.add(ring);
    root.userData.ring=ring;labelHeight=2.5;
  }else if(type==='gate'){
    for(const z of [-1.16,1.16])block(.24,2.50,.24,materials.metal,0,1.42,z);
    block(.30,.23,2.58,materials.accent,0,2.65);
    animated.push(block(.13,1.83,.84,materials.event,0,1.2,-.44),block(.13,1.83,.84,materials.event,0,1.2,.44));
    labelHeight=3.45;
  }else if(type==='cluster'){
    const core=new THREE.Group();core.position.y=1.3;root.add(core);
    const points=[];
    for(let i=0;i<12;i++){
      const y=1-2*i/11,a=i*2.39996,r=Math.sqrt(1-y*y),p=new THREE.Vector3(Math.cos(a)*r,y,Math.sin(a)*r).multiplyScalar(.63);points.push(p);
      const dot=new THREE.Mesh(new THREE.SphereGeometry(.07,12,12),materials.accent);dot.position.copy(p);core.add(dot);
    }
    for(let i=0;i<12;i++)for(let j=i+1;j<12;j++)if(points[i].distanceTo(points[j])<.92)core.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([points[i],points[j]]),new THREE.LineBasicMaterial({color:0x937ac0})));
    for(let i=0;i<5;i++){const cube=new THREE.Mesh(new THREE.BoxGeometry(.42,.48,.42),materials.result);cube.castShadow=true;root.add(cube);animated.push(cube);}
    root.userData.core=core;labelHeight=2.7;
  }else if(type==='queue'){
    for(let i=0;i<5;i++){const slot=block(.45,.28,1.05,i<3?materials.event:materials.metal,-1.2+i*.6,.48);animated.push(slot);}
    block(3.0,.10,1.48,materials.dark,0,.26);labelHeight=2.2;
  }else if(type==='storage'){
    block(2.4,1.6,2.2,materials.metal,0,1);
    block(2.42,.16,2.24,materials.accent,0,1.88);
    block(1.3,.5,.05,materials.white,0,1.1,1.13);labelHeight=2.8;
  }else throw new Error(`Unsupported component ${type}`);
  const anchor=new THREE.Object3D();anchor.position.y=labelHeight;root.add(anchor);
  function renderAt(time,focus,gateOpen){
    if(type==='agent'){
      animated.forEach((m,i)=>{m.position.y=.40+i*.35+focus*i*.30;});root.userData.ring.rotation.z=time*.35;
    }
    if(type==='gate'){animated[0].position.z=-.44-gateOpen*.64;animated[1].position.z=.44+gateOpen*.64;}
    if(type==='cluster'){
      root.userData.core.rotation.y=time*.3;
      animated.forEach((m,i)=>{const a=time*.18+i*Math.PI*2/5;m.position.set(Math.cos(a)*1.2,.70,Math.sin(a)*1.2);m.rotation.y=-a;});
    }
    if(type==='queue')animated.forEach((m,i)=>{m.position.y=.48+Math.max(0,Math.sin(time*1.3-i*.5))*.1*focus;});
  }
  return {root,anchor,renderAt,base,portHeight:type==='gate'?1.2:.85};
}
