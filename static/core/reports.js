/* Report periods and account-level daily reports.
 * Mirrors ads_core/report_dates.py and ads_core/providers.py (report_output and
 * the Google/Meta daily parsers). Parity is enforced by tests/fixtures/core. */
import {pyRound,pySum} from './pyfmt.js';

export const PERIODS=['today','yesterday','last_7d','last_14d','last_30d','last_90d',
 'this_week','last_week','this_month','last_month','this_quarter','last_quarter',
 'this_year','last_year','custom'];

const DAY=86400000;
const parse=s=>{const [y,m,d]=s.split('-').map(Number);return Date.UTC(y,m-1,d);};
const iso=t=>new Date(t).toISOString().slice(0,10);
const ymd=t=>{const d=new Date(t);return [d.getUTCFullYear(),d.getUTCMonth()+1,d.getUTCDate()];};
const make=(y,m,d)=>Date.UTC(y,m-1,d);
export class ReportError extends Error{constructor(message,status=422){super(message);this.status=status;}}

/** Local calendar date as YYYY-MM-DD (what Python's date.today() returns on the PC). */
export function localToday(now=new Date()){
 return now.getFullYear()+'-'+String(now.getMonth()+1).padStart(2,'0')+'-'+String(now.getDate()).padStart(2,'0');
}

export function resolveDateRange(period='last_7d',dateFrom=null,dateTo=null,today=localToday()){
 const now=parse(today);
 if(!PERIODS.includes(period))throw new ReportError('Khoảng thời gian không được hỗ trợ');
 let start,end;
 const weekday=(new Date(now).getUTCDay()+6)%7; // Monday=0 like Python
 const [Y,M]=ymd(now);
 if(period==='custom'){
   if(typeof dateFrom!=='string'||typeof dateTo!=='string')throw new ReportError('Chọn đủ ngày bắt đầu và ngày kết thúc');
   const ok=s=>s.length===10&&/^\d{4}-\d{2}-\d{2}$/.test(s)&&iso(parse(s))===s;
   if(!ok(dateFrom)||!ok(dateTo))throw new ReportError('Ngày phải có định dạng YYYY-MM-DD');
   start=parse(dateFrom);end=parse(dateTo);
 }else if(dateFrom!==null&&dateFrom!==undefined||dateTo!==null&&dateTo!==undefined){
   throw new ReportError('Ngày tùy chỉnh chỉ dùng khi chọn Tùy chỉnh');
 }else if(period==='today'){start=end=now;}
 else if(period==='yesterday'){start=end=now-DAY;}
 else if(['last_7d','last_14d','last_30d','last_90d'].includes(period)){
   // Match Google's LAST_N_DAYS: completed days, excluding today.
   const n=Number(period.split('_')[1].slice(0,-1));
   start=now-n*DAY;end=now-DAY;
 }else if(period==='this_week'){start=now-weekday*DAY;end=now;}
 else if(period==='last_week'){end=now-(weekday+1)*DAY;start=end-6*DAY;}
 else if(period==='this_month'){start=make(Y,M,1);end=now;}
 else if(period==='last_month'){end=make(Y,M,1)-DAY;const [y,m]=ymd(end);start=make(y,m,1);}
 else if(period==='this_quarter'){start=make(Y,Math.floor((M-1)/3)*3+1,1);end=now;}
 else if(period==='last_quarter'){
   end=make(Y,Math.floor((M-1)/3)*3+1,1)-DAY;
   const [y,m]=ymd(end);start=make(y,Math.floor((m-1)/3)*3+1,1);
 }else if(period==='this_year'){start=make(Y,1,1);end=now;}
 else{start=make(Y-1,1,1);end=make(Y-1,12,31);}
 if(start>end||end>now||(end-start)/DAY>365)
   throw new ReportError('Ngày không hợp lệ, nằm trong tương lai hoặc vượt quá 366 ngày');
 return [iso(start),iso(end)];
}

/** providers.report_output */
export function reportOutput(rows,currency,source){
 const spend=pyRound(pySum(rows.map(x=>Number(x.spend||0))),2);
 const impressions=rows.reduce((a,x)=>a+Math.trunc(Number(x.impressions||0)),0);
 const clicks=rows.reduce((a,x)=>a+Math.trunc(Number(x.clicks||0)),0);
 // Only expose conversion KPIs when the provider actually supplied them.
 const hasConversions=rows.length>0&&rows.every(x=>x.conversions!==undefined&&x.conversions!==null);
 const hasValues=rows.length>0&&rows.every(x=>x.conversion_value!==undefined&&x.conversion_value!==null);
 const conversions=hasConversions?pyRound(pySum(rows.map(x=>Number(x.conversions))),2):null;
 const conversionValue=hasValues?pyRound(pySum(rows.map(x=>Number(x.conversion_value))),2):null;
 return {source,currency,spend,impressions,clicks,
   ctr:impressions?pyRound(clicks*100/impressions,2):0,
   cpc:clicks?pyRound(spend/clicks,2):null,
   conversions,conversion_value:conversionValue,
   conversion_action_type:source==='google_live'&&hasConversions?'google_all_conversions':null,
   cpa:conversions&&conversions>0?pyRound(spend/conversions,2):null,
   roas:conversionValue!==null&&spend>0?pyRound(conversionValue/spend,2):null,
   daily:rows};
}

/** Day rows from a Google Ads searchStream response (providers.google_report). */
export function googleDailyRows(pages){
 if(!Array.isArray(pages))throw new ReportError('Google Ads trả về dữ liệu không hợp lệ',502);
 const days={};
 for(const page of pages){
   for(const item of page.results||[]){
     const ds=(item.segments||{}).date;
     if(!ds)continue;
     const m=item.metrics||{};
     const x=days[ds]||(days[ds]={date:ds,spend:0,impressions:0,clicks:0});
     x.spend+=Math.trunc(Number(m.costMicros||0))/1000000;
     x.impressions+=Math.trunc(Number(m.impressions||0));
     x.clicks+=Math.trunc(Number(m.clicks||0));
     // Missing values are unknown (not silently assumed to be zero).
     for(const [src,dest] of [['conversions','conversions'],['conversionsValue','conversion_value']]){
       if(src in m&&m[src]!==null&&m[src]!==undefined)x[dest]=Number(x[dest]||0)+Number(m[src]);
     }
   }
 }
 return Object.keys(days).sort().map(k=>days[k]);
}

/** Day rows from a Meta /insights?time_increment=1 response. */
export function metaDailyRows(body){
 return (body.data||[]).map(x=>({date:x.date_start,spend:Number(x.spend??0),
   impressions:Math.trunc(Number(x.impressions??0)),clicks:Math.trunc(Number(x.clicks??0))}));
}
