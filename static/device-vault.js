/* LHM Ads AI — 100% on-device encrypted Ads account vault (browser).
 * Never calls fetch, localStorage, sessionStorage or posts a credential to LHM.
 * Threat model: protects storage at rest; DOES NOT protect against injected scripts,
 * a compromised browser, device malware or lost storage keys.
 */
'use strict';
(() => {
  const DATABASE='lhm-ads-device-only-v1';
  const STORE='vaults', KEYRING='deviceKeys', VERSION=1, DB_VERSION=2, MAX_ACCOUNTS=100;
  let KEY='default';
  const cloudPwa=Boolean(document.getElementById('lhm-local-workspace'));
  let namespaceSet=!cloudPwa;
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
    if(!namespaceSet)throw Error('Đăng nhập Google và mua gói để mở kho riêng.');
    return new Promise((resolve,reject)=>{
      const req=indexedDB.open(DATABASE,DB_VERSION);
      req.onupgradeneeded=()=>{
        if(!req.result.objectStoreNames.contains(STORE))req.result.createObjectStore(STORE,{keyPath:'id'});
        if(!req.result.objectStoreNames.contains(KEYRING))req.result.createObjectStore(KEYRING,{keyPath:'id'});
      };
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
  async function deviceKey(){
    if(!cloudPwa||!namespaceSet)throw Error('Cần đăng nhập tài khoản Google hợp lệ.');
    const db=await open();
    try{
      const existing=await new Promise((resolve,reject)=>{
        const req=db.transaction(KEYRING,'readonly').objectStore(KEYRING).get(KEY);
        req.onsuccess=()=>resolve(req.result?.key||null);
        req.onerror=()=>reject(Error('Không đọc được khóa bảo mật thiết bị.'));
      });
      if(existing)return existing;
      // The key is NON-EXTRACTABLE, never sent to Cloudflare. A separate recovery
      // password is only requested when exporting/importing a backup.
      const key=await crypto.subtle.generateKey({name:'AES-GCM',length:256},false,['encrypt','decrypt']);
      await new Promise((resolve,reject)=>{
        const tx=db.transaction(KEYRING,'readwrite');
        tx.objectStore(KEYRING).put({id:KEY,key});
        tx.oncomplete=resolve;tx.onerror=()=>reject(Error('Không lưu được khóa thiết bị.'));
      });
      return key;
    }finally{db.close();}
  }
  async function autoUnlock(){
    requireSecure();
    if(!cloudPwa||!namespaceSet)throw Error('Chưa có Gmail đăng nhập.');
    if(cryptoKey&&memory)return {unlocked:true};
    const record=await read();
    if(record && record.kdf!=='DEVICE-KEY-AES256')return {legacy_password_required:true};
    const key=await deviceKey();
    if(record){
      const value=await decrypt(record,key);
      cryptoKey=key;memory=value;return {unlocked:true,count:value.accounts.length};
    }
    const value=empty();
    await write(await encrypt(value,key,null));
    cryptoKey=key;memory=value;return {created:true,unlocked:true};
  }
  async function derive(password,salt){
    return crypto.subtle.deriveKey({
      name:'PBKDF2',salt,iterations:ITERATIONS,hash:'SHA-256'
    },await crypto.subtle.importKey('raw',encoder.encode(password),'PBKDF2',false,['deriveKey']),
    {name:'AES-GCM',length:256},false,['encrypt','decrypt']);
  }
  const verifyPassword=p=>typeof p==='string'&&p.length>=12&&p.length<=512;
  const empty=()=>({version:VERSION,accounts:[],reports:[],budgetRules:[],createdAt:new Date().toISOString()});
  const aad={name:'AES-GCM',additionalData:CTX,tagLength:128};
  async function encrypt(data,key,salt){
    const iv=crypto.getRandomValues(new Uint8Array(12));
    const ciphertext=await crypto.subtle.encrypt({...aad,iv},key,encoder.encode(JSON.stringify(data)));
    return salt===null
      ? {id:KEY,version:VERSION,kdf:'DEVICE-KEY-AES256',iv:base64(iv),
         ciphertext:base64(new Uint8Array(ciphertext))}
      : {id:KEY,version:VERSION,kdf:'PBKDF2-SHA256',iterations:ITERATIONS,
         salt:base64(salt),iv:base64(iv),ciphertext:base64(new Uint8Array(ciphertext))};
  }
  async function decrypt(record,key){
    const plaintext=await crypto.subtle.decrypt({...aad,iv:unbase64(record.iv)},key,unbase64(record.ciphertext));
    const value=JSON.parse(decoder.decode(plaintext));
    if(!value||value.version!==VERSION||!Array.isArray(value.accounts)||value.accounts.length>MAX_ACCOUNTS)
      throw Error('Kho dữ liệu không hợp lệ.');
    value.reports=Array.isArray(value.reports)?value.reports:[];
    value.budgetRules=Array.isArray(value.budgetRules)?value.budgetRules:[];
    if(value.reports.length>2000||value.budgetRules.length>MAX_ACCOUNTS)
      throw Error('Kho dữ liệu vượt giới hạn an toàn.');
    return value;
  }
  function validateRecord(record){
    if(!record||record.id!==KEY||record.version!==VERSION||
      !(record.kdf==='DEVICE-KEY-AES256'||
       (record.kdf==='PBKDF2-SHA256'&&record.iterations===ITERATIONS&&unbase64(record.salt).length===16))||
      unbase64(record.iv).length!==12||unbase64(record.ciphertext).length<32)
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
    if(!next||!Array.isArray(next.accounts)||next.accounts.length>MAX_ACCOUNTS||
       !Array.isArray(next.reports)||next.reports.length>2000||
       !Array.isArray(next.budgetRules)||next.budgetRules.length>MAX_ACCOUNTS)
      throw Error('Số tài khoản vượt giới hạn kho cục bộ.');
    const old=await read();validateRecord(old);
    const encrypted=await encrypt(next,cryptoKey,old.kdf==='DEVICE-KEY-AES256'?null:unbase64(old.salt));
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
      const currency=info.currency==null?(existing?.currency||'VND'):sanitize(info.currency,3).toUpperCase();
      if(!/^[A-Z]{3}$/.test(currency))throw Error('Mã tiền tệ phải có 3 chữ cái.');
      const data={...memory,accounts:memory.accounts.map(x=>({...x}))};
      const item={localId:existing?.localId||crypto.randomUUID(),platform:info.platform,
        accountId:id,label,currency,accessToken,refreshToken,
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
    return memory.accounts.map(({localId,platform,accountId,label,currency,accessToken,refreshToken,updatedAt})=>({
      localId,platform,accountId,label,currency:currency||'VND',
      hasAccessToken:Boolean(accessToken),hasRefreshToken:Boolean(refreshToken),updatedAt
    }));
  }
  function removeAccount(localId){
    return serial(async()=>{
      requireUnlocked();
      const data={...memory,accounts:memory.accounts.filter(x=>x.localId!==localId),
        reports:memory.reports.filter(x=>x.localId!==localId),
        budgetRules:memory.budgetRules.filter(x=>x.localId!==localId)};
      if(data.accounts.length===memory.accounts.length)throw Error('Không có tài khoản cần xóa.');
      await persist(data);return {removed:true};
    });
  }
  // Offline-only imports. These rows are NEVER represented as API-verified live data.
  function importDailyReport(localId,rows){
    return serial(async()=>{
      requireUnlocked();
      const account=memory.accounts.find(a=>a.localId===localId);
      if(!account)throw Error('Không tìm thấy tài khoản trên thiết bị.');
      if(!Array.isArray(rows)||rows.length<1||rows.length>366)
        throw Error('CSV phải chứa từ 1 đến 366 ngày.');
      const seen=new Set(),validated=[];
      for(const raw of rows){
        if(!raw||typeof raw.date!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}$/.test(raw.date))
          throw Error('Ngày báo cáo phải theo YYYY-MM-DD.');
        const dt=new Date(raw.date+'T00:00:00Z');
        if(!Number.isFinite(dt.getTime())||dt.toISOString().slice(0,10)!==raw.date||seen.has(raw.date))
          throw Error('CSV có ngày sai hoặc trùng nhau.');
        seen.add(raw.date);
        const currency=String(raw.currency||'').toUpperCase();
        if(currency!==(account.currency||'VND'))throw Error('Sai đơn vị tiền tệ của tài khoản.');
        const values=['spend','clicks','impressions'].map(k=>Number(raw[k]));
        if(values.some(n=>!Number.isFinite(n)||n<0||n>1e12))
          throw Error('Số liệu CSV phải là số không âm và hợp lệ.');
        if(!Number.isInteger(values[1])||!Number.isInteger(values[2]))
          throw Error('Clicks và impressions phải là số nguyên.');
        validated.push({localId,date:raw.date,currency,
          spend:values[0],clicks:values[1],impressions:values[2],
          source:'manual_csv',updatedAt:new Date().toISOString()});
      }
      const retained=memory.reports.filter(x=>x.localId!==localId);
      const latest=validated.sort((a,b)=>b.date.localeCompare(a.date));
      const next={...memory,reports:retained.concat(latest)};
      if(next.reports.length>2000)throw Error('Đã đạt tối đa 2.000 ngày báo cáo cục bộ.');
      await persist(next);
      return {imported:latest.length,source:'manual_csv'};
    });
  }
  function listDailyReports(localId){
    requireUnlocked();
    if(localId&&!memory.accounts.some(x=>x.localId===localId))throw Error('Không có tài khoản.');
    return memory.reports.filter(x=>!localId||x.localId===localId)
      .map(({localId,date,currency,spend,clicks,impressions,source,updatedAt})=>
        ({localId,date,currency,spend,clicks,impressions,source,updatedAt}))
      .sort((a,b)=>b.date.localeCompare(a.date));
  }
  function setDailyBudget(localId,threshold,enabled=true){
    return serial(async()=>{
      requireUnlocked();
      if(!memory.accounts.some(x=>x.localId===localId))throw Error('Không có tài khoản.');
      if(typeof threshold!=='number'||!Number.isFinite(threshold)||threshold<=0||threshold>1e12)
        throw Error('Ngưỡng ngân sách phải là số dương.');
      const rules=memory.budgetRules.filter(x=>x.localId!==localId);
      rules.push({localId,threshold,enabled:Boolean(enabled),updatedAt:new Date().toISOString()});
      await persist({...memory,budgetRules:rules});
      return {saved:true};
    });
  }
  function listDailyBudgets(){
    requireUnlocked();
    return memory.budgetRules.map(x=>({...x}));
  }
  function listLocalAlerts(){
    requireUnlocked();
    const accounts=new Map(memory.accounts.map(x=>[x.localId,x]));
    const rules=new Map(memory.budgetRules.filter(x=>x.enabled).map(x=>[x.localId,x]));
    return memory.reports.filter(x=>{
      const rule=rules.get(x.localId);
      return rule&&x.spend>rule.threshold&&accounts.has(x.localId);
    }).map(x=>({
      localId:x.localId,date:x.date,currency:x.currency,spend:x.spend,
      threshold:rules.get(x.localId).threshold,
      label:accounts.get(x.localId).label,
      source:'manual_csv',note:'Phát hiện từ CSV đã nhập, KHÔNG phải cảnh báo realtime.'
    })).sort((a,b)=>b.date.localeCompare(a.date)).slice(0,30);
  }
  async function encryptedBackup(recoveryPassword){
    requireUnlocked();
    let data=await read();validateRecord(data);
    // Non-extractable browser device keys cannot travel to another machine.
    // Re-encrypt the backup with an explicit recovery passphrase, ONLY on export.
    if(data.kdf==='DEVICE-KEY-AES256'){
      if(!verifyPassword(recoveryPassword))throw Error('Mật khẩu sao lưu cần tối thiểu 12 ký tự.');
      const salt=crypto.getRandomValues(new Uint8Array(16));
      data=await encrypt(memory,await derive(recoveryPassword,salt),salt);
    }
    return JSON.stringify({format:'lhm-ads-encrypted-backup',version:1,vault:data});
  }
  async function importBackup(raw,recoveryPassword){
    requireSecure();
    if(typeof raw!=='string'||raw.length>4_000_000)throw Error('Tệp sao lưu quá lớn.');
    const parsed=JSON.parse(raw);
    if(parsed?.format!=='lhm-ads-encrypted-backup'||parsed.version!==1)
      throw Error('Tệp sao lưu không phải của LHM Ads AI.');
    validateRecord(parsed.vault);
    // Caller must confirm destructive replacement. No server operations performed.
    if(cloudPwa&&parsed.vault.kdf==='PBKDF2-SHA256'){
      if(!verifyPassword(recoveryPassword))throw Error('Cần mật khẩu bản sao lưu (tối thiểu 12 ký tự).');
      const oldKey=await derive(recoveryPassword,unbase64(parsed.vault.salt));
      const value=await decrypt(parsed.vault,oldKey);
      const key=await deviceKey();
      await write(await encrypt(value,key,null));
      cryptoKey=key;memory=value;
      return {imported:true,unlocked:true};
    }
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
  function setNamespace(customerId){
    if(typeof customerId!=='string'||!/^[0-9a-f-]{36}$/i.test(customerId))throw Error('Invalid customer workspace ID');
    if(KEY!=='google:'+customerId)lock();
    KEY='google:'+customerId;namespaceSet=true;
  }
  Object.defineProperty(window,'LHMDeviceVault',{
    value:Object.freeze({
      setNamespace,autoUnlock,exists:async()=>Boolean(await read()),create,unlock,lock,isUnlocked:()=>Boolean(cryptoKey&&memory),
      listAccounts,upsertAccount,removeAccount,importDailyReport,listDailyReports,
      setDailyBudget,listDailyBudgets,listLocalAlerts,encryptedBackup,importBackup,destroy
    }),writable:false,configurable:false
  });
})();
