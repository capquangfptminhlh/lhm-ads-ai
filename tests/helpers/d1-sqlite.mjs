/* Minimal Cloudflare D1 binding backed by node:sqlite, with every migration
 * applied, so Worker tests run real SQL instead of string-matching mocks. */
import {DatabaseSync} from 'node:sqlite';
import {readFileSync,readdirSync} from 'node:fs';

const MIGRATIONS=new URL('../../migrations/',import.meta.url);
const clean=args=>args.map(v=>v===undefined?null:typeof v==='boolean'?Number(v):v);

export function createD1(){
 const sqlite=new DatabaseSync(':memory:');
 sqlite.exec('PRAGMA foreign_keys=ON');
 for(const name of readdirSync(MIGRATIONS).filter(n=>n.endsWith('.sql')).sort())
   sqlite.exec(readFileSync(new URL(name,MIGRATIONS),'utf8'));
 const statement=(sql,args=[])=>({
   bind:(...more)=>statement(sql,more),
   async first(column){
     const row=sqlite.prepare(sql).get(...clean(args));
     if(!row)return null;
     return column?row[column]:{...row};
   },
   async all(){return {results:sqlite.prepare(sql).all(...clean(args)).map(r=>({...r}))};},
   async run(){
     const r=sqlite.prepare(sql).run(...clean(args));
     return {meta:{changes:Number(r.changes),last_row_id:Number(r.lastInsertRowid)}};
   },
   _exec(){return sqlite.prepare(sql).run(...clean(args));}
 });
 return {
   prepare:sql=>statement(sql),
   async batch(statements){
     sqlite.exec('BEGIN');
     try{
       const out=statements.map(s=>{const r=s._exec();return {meta:{changes:Number(r.changes)}};});
       sqlite.exec('COMMIT');
       return out;
     }catch(e){sqlite.exec('ROLLBACK');throw e;}
   },
   sqlite
 };
}
