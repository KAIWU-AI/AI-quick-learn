export function createBackground(canvas,theme){
  canvas.width=1920;canvas.height=1080;
  const ctx=canvas.getContext('2d');if(!ctx)throw new Error('2D background canvas unavailable');
  let seed=2417;const rand=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  const stars=Array.from({length:85},()=>({angle:rand()*Math.PI*2,phase:rand(),speed:.011+rand()*.01,width:.5+rand()*.7}));
  return time=>{
    ctx.fillStyle=theme==='space'?'#121c33':'#e9edf3';ctx.fillRect(0,0,1920,1080);
    const glow=ctx.createRadialGradient(900,440,60,900,440,1080);
    glow.addColorStop(0,theme==='space'?'#35405b':'#f8f9fc');glow.addColorStop(1,theme==='space'?'#121c33':'#e9edf3');
    ctx.fillStyle=glow;ctx.fillRect(0,0,1920,1080);
    if(theme!=='space')return;
    for(const star of stars){
      const u=(star.phase+time*star.speed)%1,r=40+u*u*1400;
      const alpha=Math.sin(u*Math.PI)*.46,length=3+u*38;
      const x=870+Math.cos(star.angle)*r,y=450+Math.sin(star.angle)*r;
      ctx.strokeStyle=`rgba(223,233,255,${alpha})`;ctx.lineWidth=star.width;
      ctx.beginPath();ctx.moveTo(x-Math.cos(star.angle)*length,y-Math.sin(star.angle)*length);ctx.lineTo(x,y);ctx.stroke();
    }
  };
}
