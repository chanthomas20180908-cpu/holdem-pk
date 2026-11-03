import {test} from 'node:test';
import assert from 'node:assert/strict';
import {buildFrames} from '../src/presentation.ts';
import {actionLabel} from '../src/actions.ts';
const initial:any={version:'a',epoch:0,table:{hand:1,done:false,board:[],street:'preflop',pot:10,events:[],players:[{stack:90,bet:10,total:10,folded:false},{stack:100,bet:0,total:0,folded:false}]}};
test('amounts and board follow events without early reveal',()=>{
 const next=structuredClone(initial);next.version='b';next.table.board=['As','Kd','2c'];next.table.events=[{kind:'action',street:'preflop',seat:1,action:'call',paid:10,bet:10,pot:20},{kind:'deal',street:'flop',cards:next.table.board,pot:20}];
 const frames=buildFrames(initial,next);
 assert.deepEqual(frames[0].table.board,[]);assert.equal(frames[0].table.players[1].stack,90);assert.equal(frames[0].table.players[1].total,10);
 assert.deepEqual(frames[1].table.board,next.table.board);assert.equal(frames[1].table.players[1].bet,0);
 assert.equal(initial.table.players[1].stack,100);
 assert.equal(buildFrames(next,next).length,1);
});
test('refund and pot shares remain distinct',()=>{
 const next=structuredClone(initial);next.table.done=true;next.table.events=[{kind:'refund',street:'river',seat:0,amount:5,pot:20},{kind:'settlement',street:'river',pot:20,pots:[{amount:20,shares:{0:10,1:10}}]}];
 const frames=buildFrames(initial,next);
 assert.equal(frames[0].table.players[0].stack,95);
 const payouts=frames.filter(x=>x.table.events.at(-1).kind==='payout');assert.equal(payouts.length,2);assert.deepEqual(payouts.map(x=>x.table.events.at(-1).amount),[10,10]);
 assert.equal(actionLabel(next.table.events[0]),'退回 5');
});
