import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import {fileURLToPath} from 'node:url';
import {readJson,writeJson,parseOptions,run,sha} from './lib.mjs';
import {validate} from './schema.mjs';
import {build} from './project.mjs';

export const defaultVoice='zh-CN-Xiaoxiao2:DragonHDFlashLatestNeural';
export function speechCredentials(env=process.env){
  const key=env.AZURE_SPEECH_KEY,region=env.AZURE_SPEECH_REGION;
  if(!key||/^(your|replace|example|<)/i.test(key))throw new Error('Set AZURE_SPEECH_KEY in the process environment. No credential files or CLI account will be read.');
  if(!region||!/^[a-z][a-z0-9]{2,35}$/.test(region))throw new Error('Set a valid AZURE_SPEECH_REGION in the process environment.');
  return {key,region};
}
const xml=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c]));
export function speechPlan(script,duration,voice=defaultVoice){
  if(!Array.isArray(script)||script.length<1||script.length>30)throw new Error('narration.json must be an array of1..30 clips.');
  if(!/^[a-z]{2}-[A-Z]{2}-[A-Za-z0-9:-]+Neural$/.test(voice))throw new Error('Use a complete Azure voice ID.');
  let end=0;
  return script.map((line,index)=>{
    if(!line||Object.keys(line).some(k=>!['start','end','text'].includes(k)))throw new Error('Narration clips accept only start,end,text.');
    if(!Number.isFinite(line.start)||!Number.isFinite(line.end)||line.start<end||line.end<=line.start||line.end>duration)throw new Error('Narration times overlap or exceed composition.');
    if(typeof line.text!=='string'||!line.text.trim()||line.text.length>2000)throw new Error('Narration text is empty/too long.');
    end=line.end;
    const ssml=`<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" xml:lang="${voice.slice(0,5)}"><voice name="${xml(voice)}"><prosody rate="0%" pitch="0Hz">${xml(line.text)}</prosody></voice></speak>`;
    const hash=crypto.createHash('sha256').update(ssml).digest('hex');
    return {index,start:line.start,end:line.end,text:line.text,voice,ssml,hash};
  });
}
export function checkWordEvents(words,duration){
  let previous=-1;
  for(const word of words){
    if(!Number.isFinite(word.start)||!Number.isFinite(word.duration)||word.start<previous||word.start<0||word.duration<0||word.start+word.duration>duration+.15)throw new Error('Azure word boundaries are invalid or out of order.');
    previous=word.start;
  }
}
export async function azureSynthesize(sdk,credentials,clip){
  const config=sdk.SpeechConfig.fromSubscription(credentials.key,credentials.region);
  config.speechSynthesisVoiceName=clip.voice;
  config.speechSynthesisOutputFormat=sdk.SpeechSynthesisOutputFormat.Audio24Khz48KBitRateMonoMp3;
  const synthesizer=new sdk.SpeechSynthesizer(config,null),words=[];
  synthesizer.wordBoundary=(_,event)=>words.push({text:event.text,start:event.audioOffset/1e7,duration:(event.duration||0)/1e7,textOffset:event.textOffset,wordLength:event.wordLength});
  return new Promise((resolve,reject)=>{
    const timeout=setTimeout(()=>{synthesizer.close();reject(new Error('Azure synthesis timed out; no automatic chargeable retry.'));},120000);
    synthesizer.speakSsmlAsync(clip.ssml,result=>{
      clearTimeout(timeout);synthesizer.close();
      if(result.reason!==sdk.ResultReason.SynthesizingAudioCompleted){reject(new Error(`Azure speech failed (reason ${result.reason}). Check resource/voice/quota; credentials and provider detail are withheld.`));return;}
      resolve({audio:Buffer.from(result.audioData),duration:result.audioDuration/1e7,words});
    },()=>{clearTimeout(timeout);synthesizer.close();reject(new Error('Azure connection/synthesis failed. Check connectivity, key, region and quota. Sensitive provider errors are not printed.'));});
  });
}
export async function main(args){
  const options=parseOptions(args,{project:'value',voice:'value',prepare:'flag',approved:'flag'});
  if(!options.project)throw new Error('Specify --project.');
  const project=path.resolve(options.project),config=validate(readJson(path.join(project,'architecture.json')));
  const source=path.join(project,'narration.json'),plan=speechPlan(readJson(source),config.duration,options.voice||defaultVoice);
  const scriptHash=sha(source),planDir=path.join(project,'narration-plan');fs.mkdirSync(planDir,{recursive:true});
  for(const clip of plan)fs.writeFileSync(path.join(planDir,`${String(clip.index+1).padStart(2,'0')}.ssml`),clip.ssml);
  writeJson(path.join(planDir,'plan.json'),{voice:options.voice||defaultVoice,scriptSha256:scriptHash,format:'Audio24Khz48KBitRateMonoMp3',clips:plan.map(({ssml,...clip})=>clip)});
  if(options.prepare||!options.approved){console.log('Prepared reviewable SSML only. No request sent. Pass --approved after reviewing the text; Azure Speech is billable.');return;}
  const credentials=speechCredentials();
  const sdk=await import('microsoft-cognitiveservices-speech-sdk');
  const audioDir=path.join(project,'narration-audio');fs.mkdirSync(audioDir,{recursive:true});
  writeJson(path.join(project,'narration-manifest.json'),{status:'pending',scriptSha256:scriptHash,clips:[]});
  const manifest={status:'verified',provider:'Azure Speech',voice:options.voice||defaultVoice,region:credentials.region,scriptSha256:scriptHash,clips:[]};
  for(const clip of plan){
    const stem=String(clip.index+1).padStart(2,'0')+'-'+clip.hash.slice(0,16);
    const file=path.join(audioDir,stem+'.mp3'),receipt=path.join(audioDir,stem+'.json');
    let result;
    if(fs.existsSync(file)&&fs.existsSync(receipt)){
      result=readJson(receipt);
      if(result.ssmlSha256!==clip.hash||result.sha256!==sha(file))throw new Error('Speech cache mismatch; remove only the invalid clip after inspection.');
    }else{
      const generated=await azureSynthesize(sdk,credentials,clip);
      if(generated.audio.length<500||generated.duration<.1)throw new Error('Azure returned unusable audio.');
      fs.writeFileSync(file,generated.audio);
      const probe=JSON.parse(run('ffprobe',['-v','error','-show_format','-of','json',file]));
      run('ffmpeg',['-v','error','-i',file,'-f','null','-']);
      const actual=Number(probe.format.duration);
      checkWordEvents(generated.words,actual);
      result={duration:actual,sdkDuration:generated.duration,words:generated.words,ssmlSha256:clip.hash,sha256:sha(file),decode:true};
      writeJson(receipt,result);
    }
    if(result.duration>clip.end-clip.start+.02)throw new Error(`Narration clip${clip.index+1} is ${result.duration.toFixed(2)}s, exceeding its ${(clip.end-clip.start).toFixed(2)}s slot. Edit timing or text; audio retained, no silent speed-up or voice replacement.`);
    manifest.clips.push({...result,start:clip.start,file:path.relative(project,file).split(path.sep).join('/'),text:clip.text});
  }
  writeJson(path.join(project,'narration-manifest.json'),manifest);
  build(project);
  console.log(`Added ${manifest.clips.length} verified Azure narration clips. Review pronunciation before video export.`);
}
if(process.argv[1]&&fileURLToPath(import.meta.url)===fs.realpathSync(process.argv[1]))main(process.argv.slice(2)).catch(error=>{console.error(error.message);process.exitCode=1;});
