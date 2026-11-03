import {actionLabel,type PokerEvent} from './actions';
const seats=[[50,86],[8,48],[22,20],[47,16],[78,20],[92,48],[85,76],[15,76]];
export function EventEffects({event,sequence,names,playing}:{event?:PokerEvent;sequence:string;names:string[];playing:boolean}){
 if(!playing||!event)return null;
 const pos=seats[event.seat??0];const money=event.paid||event.amount||0;
 const title=event.kind==='payout'?`分得底池 +${money}`:event.kind==='refund'?`退回 +${money}`:actionLabel(event);
 return <div className={'event-fx '+(event.all_in?'all-in':'')} key={sequence} aria-live="polite">
  {title&&<div className="event-shout">{names[event.seat??0]}<strong>{title}</strong></div>}
  {money>0&&<div className={'flying-chips '+(['refund','payout'].includes(event.kind)?'returning':'')} style={{'--from-x':pos[0]+'%','--from-y':pos[1]+'%'} as React.CSSProperties}><i>◉</i><i>◉</i><i>◉</i><b>{money}</b></div>}
  {event.action==='fold'&&<div className="fold-effect" style={{left:pos[0]+'%',top:pos[1]+'%'}}>弃牌 ✕</div>}
 </div>;
}
