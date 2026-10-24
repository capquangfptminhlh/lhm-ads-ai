/* LHM Ads AI — 100% on-device encrypted Ads account vault (browser).
 * Never calls fetch, localStorage, sessionStorage or posts a credential to LHM.
 * Threat model: protects storage at rest; DOES NOT protect against injected scripts,
 * a compromised browser, device malware or lost storage keys.
 */
'use strict';
(() => {
  const DATABASE='lhm-ads-device-only-v1';
  const STORE='vaults', KEY='default', VERSION=1, MAX_ACCOUNTS=100;
  const ITERATIONS=450000;
  const CTX=new TextEncoder().encode('LHM-Ads-AI:device-only:v1');
  let cryptoKey=null, memory=null;
  const encoder=new TextEncoder(), decoder=new TextDecoder('utf-8',{fatal:true});
  const base64=bytes=>{
    let string='';for(let i=0;i<bytes.length;i+=32768)
      string+=String.fromCharCode(...bytes.subarray(i,i+32768));
    return btoa(string);
  };
  const unbase64=str=>{
    if(typeof str!=='string'||str.length>4_000_000||!/^[A-Za-z0-9+/]*={0,2}$/.test(str))
      throw new Error('Tệp mã hóa không hợp lệ.');
    const data=atob(str);
    return Uint8Array.from(data,c=>c.charCodeAt(0));
  };
  const requireSecure=()=>{
    if(!window.isSecureContext||!window.crypto?.subtle||!window.indexedDB)
      throw new Error('Thiết bị cần HTTPS và IndexedDB/WebCrypto.');
  };
  function open(){
    requireSecure();
    return new Promise((resolve,reject)=>{
      const req=indexedDB.open(DATABASE,VERSION);
      req.onupgradeneeded=()=>{req.result.createObjectStore(STORE,{keyPath:'id'});};
      req.onsuccess=()=>resolve(req.result);
      req.onerror=()=>reject(new Error('Không mở được kho dữ liệu trên thiết bị.'));
      req.onblocked=()=>reject(new Error('Kho đang mở ở tab khác.'));
    });
  }
  async function read(){
    const db=await open();
    try{return await new Promise((resolve,reject)=>{
      const tx=db.transaction(STORE,'readonly'),req=tx.objectStore(STORE).get(KEY);
      req.onsuccess=()=>resolve(req.result??null);
      req.onerror=()=>reject(new Error('Không đọc được dữ liệu cục bộ.'));
    });}finally{db.close();}
  }
  async function write(record){
    const db=await open();
    try{return await new Promise((resolve,reject)=>{
      const tx=db.transaction(STORE,'readwrite');
      tx.objectStore(STORE).put(record);
      tx.oncomplete=()=>resolve();
      tx.onerror=()=>reject(new Error('Không lưu được dữ liệu cục bộ.'));
      tx.onabort=()=>reject(new Error('Giao dịch lưu bị hủy.'));
    });}finally{db.close();}
  }
  async function remove(){
    const db=await open();
    try{return await new Promise((resolve,reject)=>{
      const tx=db.transaction(STORE,'readwrite');
      tx.objectStore(STORE).delete(KEY);
      tx.oncomplete=()=>resolve();
      tx.onerror=()=>reject(new Error('Không xóa được kho dữ liệu.'));
    });}finally{db.close();}
  }
  async function derive(password,salt){
    return crypto.subtle.deriveKey({
      name:'PBKDF2',salt,iterations:ITERATIONS,hash:'SHA-256'
    },await crypto.subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveKey']),
    {name:'AES-GCM',length:256},false,['encrypt','decrypt']);
  }
  const verifyPassword=p=>typeof p==='string'&&p.length>=12&&p.length<=512;
  const empty=()=>({version:VERSION,accounts:[],createdAt:new Date().toISOString()});
  const aad={name:'AES-GCM',additionalData:CTX,tagLength:128};
  async function encrypt(data,key,salt){
    const iv=crypto.getRandomValues(new Uint8Array(12));
    const ciphertext=await crypto.subtle.encrypt({...aad,iv},key,encoder.encode(JSON.stringify(data)));
    return {id:KEY,version:VERSION,kdf:'PBKDF2-SHA256',iterations:ITERATIONS,
      salt:base64(salt),iv:base64(iv),ciphertext:base64(new Uint8Array(ciphertext))};
  }
  async function decrypt(record,key){
    const plaintext=await crypto.subtle.decrypt({...aad,iv:unbase64(record.iv)},key,unbase64(record.ciphertext));
    const value=JSON.parse(decoder.decode(plaintext));
    if(!value||value.version!==VERSION||!Array.isArray(value.accounts)||value.accounts.length>MAX_ACCOUNTS)
      throw Error('Kho dữ liệu không hợp lệ.');
    return value;
  }
  function validateRecord(record){
    if(!record||record.id!==KEY||record.version!==VERSION||
      record.kdf!=='PBKDF2-SHA256'||record.iterations!==ITERATIONS||
      unbase64(record.salt).length!==16||unbase64(record.iv).length!==12||
      unbase64(record.ciphertext).length<32)
      throw Error('Tệp sao lưu không đúng định dạng kho LHM.');
  }
  function requireUnlocked(){
    if(!cryptoKey||!memory)throw Error('Hãy mở khóa kho trên thiết bị trước.');
  }
  async function create(password){
    requireSecure();
    if(!verifyPassword(password))throw Error('Mật khẩu kho dữ liệu cần từ 12 ký tự.');
    if(await read())throw Error('Kho đã tồn tại. Hãy mở khóa hoặc khôi phục.');
    const salt=crypto.getRandomValues(new Uint8Array(16));
    const key=await derive(password,salt),value=empty();
    const record=await encrypt(value,key,salt);
    await write(record);cryptoKey=key;memory=value;
    return {created:true};
  }
  async function unlock(password){
    requireSecure();if(typeof password!=='string'||!password)throw Error('Nhập mật khẩu kho.');
    const record=await read();if(!record)throw Error('Chưa có kho trên thiết bị.');
    validateRecord(record);
    try{
      const key=await derive(password,unbase64(record.salt));
      const value=await decrypt(record,key);
      cryptoKey=key;memory=value;return {unlocked:true,count:value.accounts.length};
    }catch(e){cryptoKey=null;memory=null;throw Error('Mật khẩu không đúng hoặc kho dữ liệu bị hỏng.');}
  }
  async function persist(next){
    requireUnlocked();
    if(!next||!Array.isArray(next.accounts)||next.accounts.length>MAX_ACCOUNTS)
      throw Error('Số tài khoản vượt giới hạn kho cục bộ.');
    const old=await read();validateRecord(old);
    const encrypted=await encrypt(next,cryptoKey,unbase64(old.salt));
    await write(encrypted);
    memory=next;
  }
  function sanitize(value,max){
    if(typeof value!=='string'||value.length>max)throw Error('Trường dữ liệu không hợp lệ.');
    return value.trim();
  }
  let queue=Promise.resolve();
  function serial(operation){
    const next=queue.then(operation);
    queue=next.catch(()=>{});
    return next;
  }
  function upsertAccount(info){
    return serial(async()=>{
      requireUnlocked();
      if(!info||!['google','meta','tiktok'].includes(info.platform))
        throw Error('Nền tảng không hợp lệ.');
      const id=sanitize(info.accountId,128);
      if(!id)throw Error('Nhập ID tài khoản Ads.');
      const label=sanitize(info.label,150);
      const accessToken=info.accessToken==null?'':sanitize(info.accessToken,8192);
      const refreshToken=info.refreshToken==null?'':sanitize(info.refreshToken,8192);
      const existing=memory.accounts.find(x=>x.platform===info.platform&&x.accountId===id);
      const data={...memory,accounts:memory.accounts.map(x=>({...x}))};
      const item={localId:existing?.localId||crypto.randomUUID(),platform:info.platform,
        accountId:id,label,accessToken,refreshToken,
        updatedAt:new Date().toISOString()};
      if(existing){
        const index=data.accounts.findIndex(x=>x.localId===existing.localId);
        data.accounts[index]=item;
      }else{data.accounts.push(item);}
      await persist(data);return {saved:true};
    });
  }
  function listAccounts(){
    requireUnlocked();
    return memory.accounts.map(({localId,platform,accountId,label,accessToken,refreshToken,updatedAt})=>({
      localId,platform,accountId,label,
      hasAccessToken:Boolean(accessToken),hasRefreshToken:Boolean(refreshToken),updatedAt
    }));
  }
  function removeAccount(localId){
    return serial(async()=>{
      requireUnlocked();
      const data={...memory,accounts:memory.accounts.filter(x=>x.localId!==localId)};
      if(data.accounts.length===memory.accounts.length)throw Error('Không có tài khoản cần xóa.');
      await persist(data);return {removed:true};
    });
  }
  async function encryptedBackup(){
    requireUnlocked();
    const data=await read();validateRecord(data);
    // The returned object contains ONLY ciphertext; no plaintext credentials.
    return JSON.stringify({format:'lhm-ads-encrypted-backup',version:1,vault:data});
  }
  async function importBackup(raw){
    requireSecure();
    if(typeof raw!=='string'||raw.length>4_000_000)throw Error('Tệp sao lưu quá lớn.');
    const parsed=JSON.parse(raw);
    if(parsed?.format!=='lhm-ads-encrypted-backup'||parsed.version!==1)
      throw Error('Tệp sao lưu không phải của LHM Ads AI.');
    validateRecord(parsed.vault);
    // Caller must confirm destructive replacement. No server operations performed.
    cryptoKey=null;memory=null;
    await write(parsed.vault);
    return {imported:true};
  }
  async function destroy(){
    requireUnlocked();
    await remove();cryptoKey=null;memory=null;
    return {deleted:true};
  }
  function lock(){cryptoKey=null;memory=null;return {locked:true};}
  Object.defineProperty(window,'LHMDeviceVault',{
    value:Object.freeze({
      exists:async()=>Boolean(await read()),create,unlock,lock,isUnlocked:()=>Boolean(cryptoKey&&memory),
      listAccounts,upsertAccount,removeAccount,encryptedBackup,importBackup,destroy
    }),writable:false,configurable:false
  });
})();
