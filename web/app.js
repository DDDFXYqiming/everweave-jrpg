// Web 客户端只负责表现与输入，所有变化交给权威运行时提交。
const $ = id => document.getElementById(id);
const T = 28;
let state = {}, busy = false, walking = false, cancelled = false, shown = false, pollBusy = false;
let rendered = '', artKey = '', generated = new Map(), art = {}, lastFocus = '', seq = -1;
let timings = [], soundOn = false, audioContext, music, musicKey = '', lastAudio = 0;
let settingsSource='';
const images = new Map(), spriteCache = new Map();
const canvas = $('map'), ctx = canvas.getContext('2d');
ctx.imageSmoothingEnabled = false;

function el(tag, text, className) {
  const n = document.createElement(tag); if (text !== undefined) n.textContent = text;
  if (className) n.className = className; return n;
}
function error(message = '') { $('error').textContent = message; $('error').hidden = !message; }
function button(parent, label, action, enabled = true, hint = '') {
  const b = el('button', label); b.disabled = !enabled; b.title = hint;
  if (hint) b.append(el('small', hint));
  b.addEventListener('click', action); parent.append(b); return b;
}
async function request(path, data) {
  const start = performance.now(), headers = { 'X-Everweave-Web': '1' };
  const options = { headers, credentials: 'same-origin', cache: 'no-store' };
  if (data !== undefined) {
    options.method = 'POST'; headers['Content-Type'] = 'application/json';
    headers['X-Request-ID'] = crypto.randomUUID(); options.body = JSON.stringify(data);
  }
  const response = await fetch(path, options), result = await response.json();
  if (!response.ok || result.error) throw new Error(result.error || `HTTP ${response.status}`);
  if (data !== undefined) { timings.push(performance.now() - start); timings = timings.slice(-100); }
  accept(result); return result;
}
function accept(next) {
  if (next.instance_id !== state.instance_id) { seq = -1; rendered = ''; settingsSource=''; }
  if (next.snapshot_sequence < seq) return;
  seq = next.snapshot_sequence; state = next;
  $('connection').textContent = busy ? '行动中…' : '本机已连接 · 自动保存';
  render();
}
async function post(path, data) {
  if (busy) return false;
  busy = true; error();
  try { await request(path, data); return true; }
  catch (e) { cancelled = true; error(`${e.message}。状态会重新同步，动作不会自动重发。`); return false; }
  finally { busy = false; }
}
const act = data => post('/action', data);
async function poll() {
  if (pollBusy || busy) return;
  pollBusy = true;
  try { await request('/state'); }
  catch (e) { $('connection').textContent = '正在重新连接…'; error(e.message); }
  finally { pollBusy = false; }
}

function generation() {
  const d = state.director || {}, tasks = d.active_tasks || [];
  $('pause').hidden = !state.started;
  $('pause').textContent = d.paused ? '恢复后续生成' : '暂停后续生成';
  const labels = { campaign: '规划章节', region: '制作地区', reaction: '回应行动', direction: '统筹旅途' };
  const phase = { generating: '生成', repairing: '修复', validating: '校验', semantic_review: '语义审查', retrying: '连接补试' };
  $('generation-status').textContent = tasks.length ? tasks.map(t => `${labels[t.kind] || t.kind} · ${t.name} · ${phase[t.phase] || t.phase} ${Math.round(t.elapsed_seconds)} 秒`).join('\n') :
    d.failed_tasks?.length ? '有内容准备失败，可查看原因并定向重试。' : d.error || (!state.started ? '尚未开始' : d.paused ? '生成已暂停，现有内容仍可继续游玩。' : !state.region ? '正在准备生成任务…' : '已就绪，等待新的旅途进展。');
  const failures = d.failed_tasks || [], budgetFull=d.calls>=d.max_calls, signature = JSON.stringify([failures,budgetFull]);
  if ($('failures').dataset.signature !== signature) {
    $('failures').dataset.signature = signature; $('failures').replaceChildren();
    for (const f of failures) button($('failures'), `重试：${f.name}`, () => post('/retry', { target: f.target, kind: f.kind }), !budgetFull, f.message);
  }
  const sorted = [...timings].sort((a,b) => a-b);
  $('diagnostics').textContent = [
    `${state.configuration?.model || d.model || '尚未配置'} / ${state.configuration?.reasoning_effort || d.reasoning_effort || ''}`,
    `本次服务请求 ${d.calls || 0} / ${state.configuration?.max_calls || d.max_calls || 0} · 输入 ${d.input_tokens || 0} · 输出 ${d.output_tokens || 0} · 推理 ${d.reasoning_tokens || 0}`,
    `交付 ${d.accepted || 0} · 校验拒绝 ${d.rejected || 0} · 过期 ${d.stale || 0} · 修复 ${d.repair_calls || 0}`,
    `预取 ${d.prefetch_ready || 0} / ${d.prefetch_total || 0} · 活动模型请求 ${d.active_model_requests || 0}`,
    `Jev 请求 ${d.jev_requests || 0} · 凭据状态 ${state.configuration?.jev?.reason || '可用'}`,
    `最近动作 ${timings.length} 次 · 浏览器往返中位 ${sorted.length ? Math.round(sorted[Math.floor(sorted.length/2)]) : 0} ms`,
    ...tasks.map(t => `${t.name}：${JSON.stringify(t.components || {})}；剩余 ${t.deadline_remaining} 秒`),
    ...(d.task_history || []).slice(-8).map(t => `${t.kind} ${t.target} ${t.status} · ${t.elapsed_seconds}s · 请求 ${t.request_seconds}s · 校验 ${t.validation_seconds}s`)
  ].join('\n');
  if(state.configuration){
    const source=JSON.stringify([state.configuration.model,state.configuration.reasoning_effort,state.configuration.max_calls]);
    if(source!==settingsSource){$('settings-model').value=state.configuration.model;$('settings-effort').value=state.configuration.reasoning_effort;$('settings-budget').value=state.configuration.max_calls;settingsSource=source;}
  }
  $('apply-settings').disabled=!state.started || tasks.length>0 || busy;
}
function render() {
  generation();
  document.title=`${state.title || '未写之境'} · ${state.configuration?.reasoning_effort || 'high'} · Everweave`;
  $('authorization').textContent = state.subscription?.ready ? 'ChatGPT 已连接 · 可选择 Luna 模型' : '在线模式需要完成 ChatGPT 订阅授权。';
  $('login').hidden = !!state.subscription?.ready;
  $('continue').hidden = !state.started;
  $('start').disabled = !!state.started || ($('mode').value === 'live' && !state.subscription?.ready);
  const sub = state.subscription || {};
  if (sub.user_code) {
    $('login-info').replaceChildren(el('p', `授权码：${sub.user_code}`));
    const link = el('a', '打开 ChatGPT 授权页'); link.href = sub.verification_url; link.target = '_blank'; link.rel = 'noreferrer'; $('login-info').append(link);
  }
  if (!shown && state.started) shown = true;
  $('welcome').hidden = shown; $('game').hidden = !shown;
  const waiting=state.ui?.kind==='pending_exit' ? JSON.stringify([state.director?.paused,state.director?.error,state.director?.failed_tasks?.find(f=>f.target===state.ui.target),!!state.director?.active_tasks?.find(t=>t.target===state.ui.target)]) : '';
  const signature = `${state.epoch}:${state.version}:${state.ui?.ready}:${state.frontier?.map(x=>x.ready).join(',')}:${waiting}`;
  if (signature === rendered) return; rendered = signature;
  const r = state.region, p = state.player || {};
  $('place').textContent = r?.name || '世界正在成形';
  $('chapter').textContent = state.campaign?.title || state.title || '旅途中';
  $('objective').textContent = state.campaign?.goal || state.quests?.find(q=>q.status==='active')?.description || '观察周围的人与物，寻找下一步的线索。';
  $('description').textContent = r?.description || '';
  $('resources').replaceChildren();
  const resources = state.game_spec?.resources || ['hp','mp','gold'].filter(k=>p[k]!==undefined).map(k=>({label:{hp:'生命',mp:'魔力',gold:'金币'}[k],value:p[k],max:p['max_'+k]}));
  for (const resource of resources) { const n = el('div', resource.label, 'resource'); n.append(el('strong', `${resource.value}${resource.max ? ' / '+resource.max : ''}`)); $('resources').append(n); }
  $('map-placeholder').hidden = !!r;
  $('coordinates').textContent = r ? `${r.width} × ${r.height} · 位置 ${p.x}, ${p.y}` : '尚未落地';
  if (r) {
    if (canvas.width !== r.width*T || canvas.height !== r.height*T) { canvas.width = r.width*T; canvas.height = r.height*T; ctx.imageSmoothingEnabled = false; }
    const identity = JSON.stringify(r.visuals || {});
    if (identity !== artKey) { artKey = identity; art = r.visuals || {}; generated = new Map(); spriteCache.clear(); prepareArt(); }
    const focus = `${r.id}:${p.x}:${p.y}`;
    if (focus !== lastFocus) {
      lastFocus = focus; $('map-scroll').scrollLeft = p.x*T - $('map-scroll').clientWidth/2; $('map-scroll').scrollTop = p.y*T - $('map-scroll').clientHeight/2;
    }
  }
  renderInteraction(); renderObjects(); renderInventory();
  $('journal').replaceChildren(...(state.journal || []).slice(-10).map(t=>el('li',t)));
  $('quests').replaceChildren();
  for (const q of state.quests || []) {
    const line=el('p',`${{active:'进行中',complete:'已完成',failed:'未完成'}[q.status] || q.status} · ${q.name}`);
    line.append(el('small',q.description,'muted'));$('quests').append(line);
  }
  for (const n of document.querySelectorAll('[data-move],#interact,#actions,#wait')) n.disabled = !r || !!state.battle || !!state.game_over || !!Object.keys(state.ui || {}).length;
  updateAudio();
}
function renderInteraction() {
  const ui = state.ui || {}, battle = state.battle;
  $('interaction').hidden = !battle && !Object.keys(ui).length && !state.game_over;
  $('dialogue').replaceChildren(); $('choices').replaceChildren();
  if (battle) {
    $('interaction-title').textContent = `${battle.name} · ${battle.hp} / ${battle.max_hp}`;
    for (const line of battle.log || []) $('dialogue').append(el('p', line));
    const options = battle.authored ? (state.available_actions || []).map(a=>({...a,move:'rule:'+a.id})) : [{label:'攻击',move:'attack'},{label:'技能',move:'skill'},{label:'防御',move:'defend'},{label:'药剂',move:'potion'}];
    for (const a of options) button($('choices'), a.label, ()=>act({op:'combat',move:a.move}), a.enabled!==false, a.blocked_reason || a.description || '');
    button($('choices'), '撤退', ()=>act({op:'combat',move:'flee'})); return;
  }
  $('interaction-title').textContent = ui.title || (state.game_over ? '这段旅途已经结束' : '');
  for (const line of ui.lines || []) $('dialogue').append(el('p', line));
  if(ui.kind==='pending_exit' && !ui.ready){
    const d=state.director || {},failed=d.failed_tasks?.find(f=>f.kind==='region'&&f.target===ui.target),full=d.calls>=d.max_calls,active=d.active_tasks?.some(t=>t.kind==='region'&&t.target===ui.target);
    if(failed || !active && (full || d.paused)){
      $('interaction-title').textContent=failed?'地区准备失败':full?'生成预算已用完':'生成已暂停';
      $('dialogue').replaceChildren(el('p',failed?.message || (full?'可在生成设置中调整请求上限后继续。':'恢复后续生成后再准备这个地区。')));
    }
    if(failed)button($('choices'),'重试这个地区',()=>post('/retry',{target:ui.target,kind:'region'}),!full);
  }
  if (ui.kind === 'actions') for (const a of ui.actions || []) button($('choices'), a.label, ()=>act({op:'content_action',id:a.id}), a.enabled!==false, a.enabled===false ? a.blocked_reason : (a.description!==a.label ? a.description : ''));
  if (ui.kind === 'dialogue') for (const a of ui.choices || []) button($('choices'), a.text, ()=>act({op:'choice',id:a.id}));
  if (ui.kind === 'shop') for (const a of ui.goods || []) button($('choices'), `${a.name} · ${a.price} 金币`, ()=>act({op:'buy',id:a.id}), true, a.description);
  if (ui.kind === 'pending_exit') button($('choices'), ui.ready ? '进入下一地区' : '下一地区尚未准备好', ()=>act({op:'enter_exit'}), !!ui.ready);
  if (Object.keys(ui).length) button($('choices'), ui.kind==='message' ? '继续' : '关闭交互', ()=>act({op:'close'}));
}
function visibleObjects() { return (state.region?.entities || []).filter(e=>!e.spent); }
function distance(a, p) { return Math.min(...cells(a).map(([x,y])=>Math.abs(x-p.x)+Math.abs(y-p.y))); }
function renderObjects() {
  $('objects').replaceChildren(); if (!state.region) return;
  const labels = {npc:'人物',object:'物件',enemy:'敌人',exit:'出口',chest:'宝箱',shrine:'休息点'};
  const objects = visibleObjects().sort((a,b)=>distance(a,state.player)-distance(b,state.player));
  for (const e of objects) {
    const ready = state.frontier?.find(f=>f.id===e.target)?.ready;
    const detail = `${e.actor_id ? '人物' : labels[e.kind] || e.kind} · ${distance(e,state.player)} 格${e.alerted ? ' · 已警戒' : ''}${e.locked ? ' · '+e.blocked_reason : ''}${e.kind==='exit' && ready===false ? ' · 准备中' : ''}`;
    const b = button($('objects'), `前往并交互：${e.name}`, ()=>go(e.id), !state.battle && !state.game_over && !Object.keys(state.ui || {}).length, detail);
    if (e.kind==='enemy') b.classList.add('danger');
  }
}
function renderInventory() {
  $('inventory').replaceChildren(); $('abilities').replaceChildren();
  for (const item of state.inventory || []) {
    const row = el('div',undefined,'item'), info = el('div',`${item.name} ×${item.quantity}`);
    info.append(el('div',item.description,'muted')); row.append(info);
    button(row, item.usable?.label || '使用', ()=>act({op:'use',id:item.id}), !!item.usable?.enabled, item.usable?.blocked_reason || ''); $('inventory').append(row);
  }
  if (!state.inventory?.length) $('inventory').append(el('p','暂时没有随身物品。','muted'));
  for (const a of state.available_actions || []) if (a.scope==='explore' && a.target==='player') button($('abilities'), a.label, ()=>act({op:'invoke',id:a.id}), a.enabled && !Object.keys(state.ui || {}).length, a.blocked_reason || a.description);
}

function cells(e) { const [w,h] = e.footprint || [1,1], out=[]; for(let y=0;y<h;y++) for(let x=0;x<w;x++) out.push([e.x+x,e.y-y]); return out; }
function route(target) {
  const r=state.region, p=state.player, occupied=new Set();
  for (const e of [...(r.props || []),...r.entities]) if (!e.spent && e.solid) for(const [x,y] of cells(e)) occupied.add(`${x},${y}`);
  const start=`${p.x},${p.y}`, prev=new Map([[start,null]]), q=[[p.x,p.y]], goals=new Set();
  for(const [x,y] of cells(target)) for(const [dx,dy] of [[0,0],[1,0],[-1,0],[0,1],[0,-1]]) goals.add(`${x+dx},${y+dy}`);
  for(let head=0;head<q.length;head++) {
    const [x,y]=q[head], key=`${x},${y}`;
    if (goals.has(key)) { const path=[];let at=key;while(prev.get(at)!==null){path.push(at.split(',').map(Number));at=prev.get(at);} return path.reverse(); }
    for(const [dx,dy] of [[1,0],[-1,0],[0,1],[0,-1]]) {
      const nx=x+dx,ny=y+dy,k=`${nx},${ny}`;
      if(nx<0||ny<0||nx>=r.width||ny>=r.height||prev.has(k)||occupied.has(k)||[2,3].includes(r.tiles[ny][nx]))continue;
      prev.set(k,key);q.push([nx,ny]);
    }
  }
  return null;
}
function eventSignature(s) {
  const p={...s.player};delete p.x;delete p.y;delete p.facing;
  const objects=(s.region?.entities || []).filter(e=>e.kind!=='enemy'||e.alerted||distance(e,s.player)<=6);
  return JSON.stringify([s.region?.id,p,s.inventory,s.quests,s.journal,objects,s.game_over]);
}
async function go(id) {
  if (walking || busy) return;
  walking=true;cancelled=false;$('stop-walk').hidden=false;error();let steps=0;
  try {
    while(steps<200 && !cancelled) {
      if(state.battle || Object.keys(state.ui || {}).length || state.game_over)break;
      const target=visibleObjects().find(e=>e.id===id);if(!target)break;
      const path=route(target);
      if(path===null){$('walk-status').textContent='暂时没有可通行的路线，请先观察附近的门和机关。';return;}
      if(!path.length){await act({op:'interact',id});$('walk-status').textContent=`已抵达，执行了 ${steps} 步正常移动。`;return;}
      const [x,y]=path[0],before=eventSignature(state);
      if(!await act({op:'move',dx:x-state.player.x,dy:y-state.player.y}))return;
      steps++;$('walk-status').textContent=`正在前往 ${target.name} · 已走 ${steps} 步`;
      if(state.player.x!==x||state.player.y!==y||eventSignature(state)!==before)break;
      await new Promise(resolve=>setTimeout(resolve,45));
    }
    $('walk-status').textContent=`已停下 · ${steps} 步。请查看刚发生的事件。`;
  } finally {walking=false;$('stop-walk').hidden=true;}
}

function color(value,palette) { return typeof value==='string' && value.startsWith('#') ? value : palette?.[value] || '#b9d2c3'; }
async function imageAsset(id) {
  if(!images.has(id)) images.set(id,new Promise((resolve,reject)=>{const img=new Image();img.onload=()=>resolve(img);img.onerror=()=>reject(new Error('素材读取失败：'+id));img.src='/media/'+encodeURIComponent(id);}));
  return images.get(id);
}
async function compile(recipe,palette,frame) {
  if(recipe.material) return compile(recipe.base || {size:[16,16],layers:[['rect',0,0,16,16,'ground']]},palette,frame);
  let base=recipe.asset ? await imageAsset(recipe.asset) : null;
  const size=recipe.size || (base ? [base.width,base.height] : [16,16]);
  const c=document.createElement('canvas');c.width=size[0];c.height=size[1];const g=c.getContext('2d');g.imageSmoothingEnabled=false;
  if(base){g.save();if(recipe.flip_x){g.translate(c.width,0);g.scale(-1,1);}g.drawImage(base,0,0);g.restore();}
  for(const part of recipe.parts || []){
    const im=await imageAsset(part.asset),[x,y]=part.at || [0,0],scale=part.scale||1;
    g.save();g.translate(x+(part.flip_x?im.width*scale:0),y);g.scale(part.flip_x?-scale:scale,scale);g.drawImage(im,0,0);g.restore();
  }
  const layers=frame===undefined ? recipe.layers || [] : recipe.frames?.[frame] || recipe.layers || [];
  for(const command of layers){
    const [op,a,b,d,e,f]=command;
    if(op==='poly'){g.fillStyle=color(b,palette);g.beginPath();a.forEach(([x,y],i)=>i?g.lineTo(x,y):g.moveTo(x,y));g.closePath();g.fill();}
    else {g.fillStyle=color(f,palette);if(op==='ellipse'){g.beginPath();g.ellipse(a+d/2,b+e/2,d/2,e/2,0,0,Math.PI*2);g.fill();}else g.fillRect(a,b,d,e);}
  }
  if(recipe.tint){g.globalCompositeOperation='source-atop';g.globalAlpha=.25;g.fillStyle=recipe.tint;g.fillRect(0,0,c.width,c.height);}
  return c;
}
async function prepareArt() {
  const key=artKey, source=art;
  for(const [name,recipe] of Object.entries(source.sprites || {})){
    try{const frames=[];for(let f=0;f<(recipe.frames?.length || 1);f++)frames.push(await compile(recipe,source.palette,recipe.frames?.length?f:undefined));
      if(key===artKey)generated.set(name,{frames,ms:recipe.frame_ms || 250});}
    catch(e){console.warn(e.message);}
  }
}
function texture(key,ms) {const alias=art.bindings?.[key] || key, value=generated.get(alias);return value?.frames[Math.floor(ms/value.ms)%value.frames.length];}
function draw(ms) {
  const r=state.region,p=state.player;
  if(r&&shown){
    const palette=r.visuals?.palette || {}, colors=['ground','path','water','wall','path'];
    ctx.clearRect(0,0,canvas.width,canvas.height);
    for(let y=0;y<r.height;y++)for(let x=0;x<r.width;x++){
      const type=r.tiles[y][x],t=texture(r.surfaces?.[y]?.[x],ms);
      if(t)ctx.drawImage(t,x*T,y*T,T,T);else{ctx.fillStyle=color(palette[colors[type]] || ['#344d42','#7a7560','#284755','#1d2c32','#b79c6f'][type],palette);ctx.fillRect(x*T,y*T,T,T);}
      if(type===3){ctx.fillStyle='#0003';ctx.fillRect(x*T,y*T+T-3,T,3);}
    }
    const objects=[...(r.props||[]).filter(e=>!e.spent),...visibleObjects(),{id:'player',kind:'player',x:p.x,y:p.y,sprite:'hero',name:'你'}].sort((a,b)=>a.y-b.y);
    for(const e of objects){
      const [w,h]=e.footprint||[1,1],x=(e.x+w/2)*T,y=(e.y+1)*T;
      const key=e.sprite || ({player:'hero',npc:'npc',object:'object',enemy:'enemy',chest:'item',exit:'portal'}[e.kind] || e.kind),t=texture(key,ms);
      if(t)ctx.drawImage(t,Math.round(x-t.width*T/32),Math.round(y-t.height*T/16),t.width*T/16,t.height*T/16);
      else {ctx.fillStyle=e.kind==='player'?'#f4d68d':e.kind==='exit'?'#81cdbb':e.kind==='enemy'?'#dc817d':'#abc6ae';ctx.fillRect(e.x*T+6,(e.y-h+1)*T+5,w*T-12,h*T-6);}
      if(e.id==='player'||e.kind==='exit'||e.alerted){ctx.strokeStyle=e.alerted?'#f79885':'#e4d6a6';ctx.lineWidth=2;ctx.strokeRect(e.x*T+2,(e.y-h+1)*T+2,w*T-4,h*T-4);}
      if(e.name && (e.kind==='player'||e.kind==='exit'||distance(e,p)<5)){
        const label=e.kind==='player'?'你':e.name;ctx.font='12px "Microsoft YaHei",sans-serif';const width=ctx.measureText(label).width;ctx.fillStyle='#0d1919df';ctx.fillRect(x-width/2-4,y+2,width+8,18);ctx.fillStyle='#f5edda';ctx.fillText(label,x-width/2,y+15);
      }
    }
  }
  setTimeout(()=>requestAnimationFrame(draw),50);
}

function playSource(source,loop=false) {
  if(!soundOn || !source)return;
  if(source.asset){const a=new Audio('/media/'+encodeURIComponent(source.asset));a.volume=source.volume??.45;a.loop=loop;a.play().catch(()=>{});return a;}
  audioContext ||= new AudioContext();
  const synth=source.synth;
  if(synth){const osc=audioContext.createOscillator(),gain=audioContext.createGain();osc.type=synth.wave==='noise'?'triangle':synth.wave;osc.frequency.value=synth.frequency;gain.gain.value=.06*(source.volume??1);osc.connect(gain).connect(audioContext.destination);osc.start();osc.stop(audioContext.currentTime+synth.duration);return;}
  if(source.score){
    for(const voice of source.score.voices){let at=audioContext.currentTime;for(const [note,beats] of voice.notes){const duration=beats*60/source.score.bpm;if(note){const osc=audioContext.createOscillator(),gain=audioContext.createGain();osc.type=voice.wave;osc.frequency.value=440*2**((note-69)/12);gain.gain.setValueAtTime((voice.gain??.1)*.35,at);gain.gain.exponentialRampToValueAtTime(.001,at+duration);osc.connect(gain).connect(audioContext.destination);osc.start(at);osc.stop(at+duration);}at+=duration;}}
  }
  if(source.layers)for(const layer of source.layers)playSource(layer);
}
function updateAudio() {
  const audio=state.region?.audio,source=audio?.music?.[state.region?.music_override || (state.battle?'combat':'explore')] || audio?.music?.explore;
  const key=JSON.stringify(source || {});
  if(soundOn && key!==musicKey){music?.pause();musicKey=key;music=playSource(source,true);}
  for(const event of state.audio_events || [])if(event.seq>lastAudio){if(lastAudio)playSource(event.sound);lastAudio=event.seq;}
}

$('start').onclick=async()=>{const offline=$('mode').value==='demo';const ok=await post('/start',{setting:$('setting').value,provider:offline?'chat_completions':'chatgpt_subscription',offline,model:offline?'demo':$('model').value,reasoning_effort:$('effort').value,max_calls:Number($('budget').value),hybrid_content:true,parallel_region:true,jev_enabled:!!state.configuration?.jev?.ready,task_timeout_seconds:900,max_transport_retries:1,language:'zh'});if(ok){shown=true;rendered='';render();}};
$('continue').onclick=()=>{shown=true;rendered='';render();};
$('mode').onchange=()=>{rendered='';render();};
$('login').onclick=()=>post('/subscription/login',{});
$('pause').onclick=()=>state.director?.mode==='not_configured' ? post('/configure',state.configuration) : post('/pause',{paused:!state.director?.paused});
$('apply-settings').onclick=()=>post('/configure',{...state.configuration,model:$('settings-model').value,reasoning_effort:$('settings-effort').value,max_calls:Number($('settings-budget').value)});
$('sound').onclick=()=>{soundOn=!soundOn;$('sound').textContent=soundOn?'静音':'开启声音';if(!soundOn){music?.pause();audioContext?.suspend();musicKey='';}else{audioContext?.resume();updateAudio();}};
$('stop-walk').onclick=()=>{cancelled=true;};
$('interact').onclick=()=>act({op:'interact'});$('actions').onclick=()=>act({op:'actions'});$('wait').onclick=()=>act({op:'wait'});
for(const b of document.querySelectorAll('[data-move]'))b.onclick=()=>{const [dx,dy]=b.dataset.move.split(',').map(Number);act({op:'move',dx,dy});};
document.addEventListener('keydown',e=>{
  if(['INPUT','TEXTAREA','SELECT'].includes(e.target.tagName)||e.ctrlKey||e.altKey||e.metaKey||e.repeat||walking)return;
  const key=e.key.toLowerCase(),move={w:[0,-1],arrowup:[0,-1],s:[0,1],arrowdown:[0,1],a:[-1,0],arrowleft:[-1,0],d:[1,0],arrowright:[1,0]}[key];
  if(move){e.preventDefault();act({op:'move',dx:move[0],dy:move[1]});}
  else if(key==='e'||key===' '){e.preventDefault();act({op:'interact'});}else if(key==='f')act({op:'actions'});else if(key==='.')act({op:'wait'});else if(key==='escape'){cancelled=true;if(state.ui?.kind)act({op:'close'});}
});
canvas.addEventListener('click',e=>{if(!state.region)return;const box=canvas.getBoundingClientRect(),x=(e.clientX-box.left)/T,y=(e.clientY-box.top)/T;const target=visibleObjects().find(o=>cells(o).some(([cx,cy])=>Math.abs(cx+.5-x)<.7&&Math.abs(cy+.5-y)<.7));if(target)go(target.id);});
await poll();setInterval(poll,900);requestAnimationFrame(draw);
