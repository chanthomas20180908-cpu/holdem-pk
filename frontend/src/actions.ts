export type PokerEvent = {kind:string;street:string;seat?:number;action?:string;paid?:number;bet?:number;pot:number;all_in?:boolean;amount?:number;cards?:string[];pots?:{amount:number;shares:Record<string,number>}[]};
export function actionLabel(e?:PokerEvent){
 if(!e)return '';
 if(e.kind==='refund')return `退回 ${e.amount}`;
 if(e.kind==='blind')return `盲注 +${e.paid}`;
 if(e.action==='fold')return '弃牌';
 if(e.action==='check')return '过牌';
 if(e.all_in)return `全押 ${e.bet} · +${e.paid}`;
 if(e.action==='raise')return `加注到 ${e.bet} · +${e.paid}`;
 if(e.action==='call')return `跟注 +${e.paid}`;
 return '';
}
