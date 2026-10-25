/* Number helpers that reproduce CPython exactly, so the PWA shows the same
 * figures and messages as the Windows app (ads_core/*.py is the reference).
 *  - round()/format() round the exact binary value, ties to even.
 *  - sum() of floats (CPython >= 3.12) uses Neumaier compensated summation.
 */
const TIE=/^(\d+)\.?(\d*)$/;

// Exact decimal expansion with `extra` digits beyond `n`, as digit strings.
function digits(x,n){
 const s=Math.abs(x).toFixed(Math.min(100,n+40));
 const [whole,frac='']=s.split('.');
 return {whole,head:frac.slice(0,n),tail:frac.slice(n)};
}

/** Python format(x, f'.{n}f') without grouping. */
export function pyFixed(x,n=0){
 if(!Number.isFinite(x))return x>0?'inf':x<0?'-inf':'nan';
 const {whole,head,tail}=digits(x,n);
 const tie=/^50*$/.test(tail);
 let out;
 if(!tie)out=Math.abs(x).toFixed(n);
 else{
   // Exact half: keep if the kept last digit is even, otherwise round away.
   const last=Number((n?head:whole).slice(-1));
   out=last%2===0?(n?whole+'.'+head:whole):Math.abs(x).toFixed(n);
 }
 if(x<0&&/[1-9]/.test(out))out='-'+out;
 return out;
}

/** Python round(x, n) -> number (n=0 returns an integer like round(x)). */
export function pyRound(x,n=0){
 if(!Number.isFinite(x))return x;
 return Number(pyFixed(x,n));
}

/** Python f"{x:,.{n}f}" — comma thousands separators. */
export function pyGrouped(x,n=0){
 const s=pyFixed(x,n);
 const neg=s.startsWith('-');
 const [w,f]=(neg?s.slice(1):s).split('.');
 const grouped=w.replace(/\B(?=(\d{3})+(?!\d))/g,',');
 return (neg?'-':'')+grouped+(f!==undefined?'.'+f:'');
}

/** Python f"{x:g}" (6 significant digits, trailing zeros stripped). */
export function pyG(x){
 if(!Number.isFinite(x))return x>0?'inf':x<0?'-inf':'nan';
 if(x===0)return Object.is(x,-0)?'-0':'0';
 const exp=Math.floor(Math.log10(Math.abs(Number(x.toPrecision(6)))));
 if(exp<-4||exp>=6){
   let [m,e]=x.toExponential(5).split('e');
   m=m.replace(/\.?0+$/,'');
   const sign=e.startsWith('-')?'-':'+';
   e=e.replace(/^[+-]/,'').padStart(2,'0');
   return m+'e'+sign+e;
 }
 return String(Number(x.toPrecision(6)));
}

/** CPython >= 3.12 sum() over floats (Neumaier compensation). */
export function pySum(values){
 let total=0,c=0;
 for(const v of values){
   const x=Number(v);
   const t=total+x;
   if(Math.abs(total)>=Math.abs(x))c+=(total-t)+x;
   else c+=(x-t)+total;
   total=t;
 }
 return c&&Number.isFinite(c)?total+c:total;
}

/** statistics.median */
export function median(values){
 const v=[...values].sort((a,b)=>a-b);
 const n=v.length;
 if(!n)throw Error('median of empty data');
 return n%2?v[(n-1)/2]:(v[n/2-1]+v[n/2])/2;
}

/** Python int(x) for finite numbers. */
export const pyInt=x=>Math.trunc(x);
