import type {CSSProperties} from 'react';

// The pile is an exact denomination breakdown; tall stacks are visually capped.
const denominations = [1000, 100, 25, 5, 1];
export function Chips({amount}: {amount:number}) {
 let remaining = Math.max(0, Math.trunc(amount));
 const stacks = denominations.flatMap(value => {
  const count = Math.floor(remaining / value); remaining %= value;
  return count ? [{value,count}] : [];
 });
 return <div className="chip-pile" aria-hidden="true">{stacks.length ? stacks.map(({value,count}) =>
  <div className={'chip-tower chip-value-'+value} key={value} title={`${value} × ${count}`}>
   {Array.from({length:Math.min(count,6)},(_,i)=><i key={i} style={{'--level':i} as CSSProperties}><span>{value>=1000?'1K':value}</span></i>)}
  </div>) : <div className="chip-empty"/>}</div>;
}
export function Money({amount,kind}:{amount:number;kind:'remaining'|'wager'}) {
 return <div className={'money money-'+kind} aria-label={`${kind==='remaining'?'剩余筹码':'本轮推出'} ${amount}`}>
  <span className="money-label">{kind==='remaining'?'剩余筹码':'本轮推出'}</span>
  <Chips amount={amount}/>
  <strong key={amount}>{amount.toLocaleString()}</strong>
 </div>;
}
