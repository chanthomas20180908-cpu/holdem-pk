import {buildFrames} from './presentation';
import {useEffect,useRef,useState,useCallback} from 'react';
import type {Snapshot} from './main';
export function usePresentation(fast:boolean,motion:boolean){
 const [data,setData]=useState<Snapshot|null>(null),[playing,setPlaying]=useState(false);
 const current=useRef<Snapshot|null>(null),queue=useRef<Snapshot[]>([]),fresh=useRef(true);
 const accept=useCallback((next:Snapshot)=>{
  const previous=queue.current.at(-1)||current.current;
  if(fresh.current||!previous?.table||!next.table||previous.table.hand!==next.table.hand||previous.epoch!==next.epoch){
   fresh.current=false;queue.current=[];current.current=next;setData(next);setPlaying(false);return;
  }
  const events=next.table.events.slice(previous.table.events.length);
  if(!events.length){if(!queue.current.length){current.current=next;setData(next)}return;}
  queue.current.push(...buildFrames(previous,next));setPlaying(true);
 },[]);
 useEffect(()=>{const timer=setInterval(()=>{const next=queue.current.shift();if(next){current.current=next;setData(next)}setPlaying(queue.current.length>0)},motion?(fast?180:500):40);return()=>clearInterval(timer)},[fast,motion]);
 const reconnect=useCallback(()=>{fresh.current=true;queue.current=[];setPlaying(false)},[]);
 const skip=()=>{const last=queue.current.at(-1);queue.current=[];if(last){current.current=last;setData(last)}setPlaying(false)};
 return {data,accept,playing,reconnect,skip};
}
