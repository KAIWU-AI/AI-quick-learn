export const clamp=(v,a=0,b=1)=>Math.max(a,Math.min(b,v));
export const smooth=(a,b,t)=>{const v=clamp((t-a)/(b-a));return v*v*(3-2*v);};
export function cameraAt(poses,time){
  let a=poses[0],b=a;
  for(let i=1;i<poses.length;i++){b=poses[i];if(time<=b.time)break;a=b;}
  const u=a===b?0:smooth(a.time,b.time,time),lerp=(x,y)=>x+(y-x)*u;
  return {target:a.target.map((n,i)=>lerp(n,b.target[i])),distance:lerp(a.distance,b.distance),yaw:lerp(a.yaw,b.yaw),pitch:lerp(a.pitch,b.pitch)};
}
export function pointOnSegments(points,progress){
  const lengths=points.slice(1).map((p,i)=>Math.hypot(...p.map((v,k)=>v-points[i][k])));
  const total=lengths.reduce((a,b)=>a+b,0);let remaining=clamp(progress)*total;
  for(let i=0;i<lengths.length;i++){
    if(remaining<=lengths[i]||i===lengths.length-1){
      const t=lengths[i]?clamp(remaining/lengths[i]):0;
      return points[i].map((v,k)=>v+(points[i+1][k]-v)*t);
    }
    remaining-=lengths[i];
  }
  return points[0];
}
export function flowPoints(edgeList){
  return edgeList.flatMap((e,i)=>i?e.points.slice(1):e.points);
}
export function labelTrack(duration,sampleAt,fps=30){
  const frames=[];let last;
  for(let i=0;i<=Math.ceil(duration*fps);i++){
    const row=sampleAt(Math.min(duration,i/fps)).map((p,j)=>{
      const prev=last?.[j],blend=1-Math.exp(-1/fps/.25);
      return {...p,x:prev?prev.x+(p.x-prev.x)*blend:p.x,y:prev?prev.y+(p.y-prev.y)*blend:p.y,alpha:prev?prev.alpha+(p.alpha-prev.alpha)*blend:p.alpha};
    });
    for(let pass=0;pass<16;pass++)for(let a=0;a<row.length;a++)for(let b=a+1;b<row.length;b++){
      const x=row[a],y=row[b],strength=smooth(.02,.25,x.alpha)*smooth(.02,.25,y.alpha);
      const dx=x.x-y.x,dy=x.y-y.y,ix=226-Math.abs(dx),iy=100-Math.abs(dy);
      if(ix<=0||iy<=0||strength===0)continue;
      if(ix<iy){const v=ix*.28*strength*(dx>=0?1:-1);x.x+=v;y.x-=v;}
      else{const v=iy*.28*strength*(dy>=0?1:-1);x.y+=v;y.y-=v;}
      for(const p of [x,y]){p.x=clamp(p.x,36,1664);p.y=clamp(p.y,100,922);}
    }
    frames.push(row);last=row;
  }
  return time=>{
    const n=clamp(time*fps,0,frames.length-1),a=Math.floor(n),b=Math.min(a+1,frames.length-1),u=n-a;
    return frames[a].map((p,i)=>({...p,x:p.x+(frames[b][i].x-p.x)*u,y:p.y+(frames[b][i].y-p.y)*u,alpha:p.alpha+(frames[b][i].alpha-p.alpha)*u}));
  };
}
