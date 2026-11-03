import type {Snapshot} from './main';
export function buildFrames(previous:Snapshot,next:Snapshot){
 const events=next.table!.events.slice(previous.table!.events.length);
  const frames:Snapshot[]=[];
  let frame=structuredClone(previous);
  for(const event of events){
   const t=frame.table!;t.events.push(event);t.pot=event.pot;t.street=event.street;
   if(event.kind==='deal'){t.board=event.cards||[];t.players.forEach(p=>p.bet=0)}
   if(event.seat!==undefined){const p=t.players[event.seat];
    if(event.kind==='action'||event.kind==='blind'){p.stack-=event.paid||0;p.total+=event.paid||0;p.bet=event.bet||0;if(event.action==='fold')p.folded=true}
    if(event.kind==='refund')p.stack+=event.amount||0;
   }
   if(event.kind==='settlement'){
    const stacks=t.players.map(p=>p.stack);
    frame=structuredClone(next);frame.table!.players.forEach((p,i)=>{p.stack=stacks[i];p.bet=0});
    frame.table!.pot=(event.pots||[]).reduce((sum,p)=>sum+p.amount,0);
    frames.push(structuredClone(frame));
    for(const pot of event.pots||[]){for(const [seat,amount] of Object.entries(pot.shares)){
     frame.table!.players[Number(seat)].stack+=amount;frame.table!.pot-=amount;
     frame.table!.events.push({kind:'payout',street:t.street,seat:Number(seat),amount,pot:pot.amount});frames.push(structuredClone(frame));
    }}
   }
   if(event.kind!=='settlement')frames.push(structuredClone(frame));
  }
 frames.push(next);return frames;
}
