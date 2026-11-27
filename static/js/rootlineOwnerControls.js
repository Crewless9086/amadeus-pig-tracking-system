/* ROOTLINE presentation adapter. All decisions and writes remain in its backend. */
(() => {
  'use strict';
  const root = document.getElementById('rootline-controls');
  if (!root) return;
  const el = id => document.getElementById('rl-' + id);
  const api = root.dataset.api;
  const copy = value => JSON.parse(JSON.stringify(value));
  const known = value => value !== null && value !== undefined && value !== '';
  const display = value => known(value) ? String(value) : 'Unavailable';
  const human = value => display(value).replaceAll('_', ' ');
  const modeNames = {automatic:'Automatic', paused:'Paused', manual_today:'Manual for today'};
  const names = [['camp_a','Camp A','♧'],['camp_b','Camp B','♧'],['camp_c','Camp C','♧'],['camp_e','Camp E','♧'],['mixer','Mixer','↻'],['injection','Injection','◉'],['borehole','Borehole','≋'],['eskom','Eskom','ϟ']];
  const state = {devices:[], plan:null, rows:[], history:[], selected:null, drafts:new Map(), planDirty:false, planDraftRevision:null, canWrite:false, pending:{}, busy:false, editGeneration:0, csrfToken:'', generations:{}, failures:{}};
  function node(tag, value, className) { const n=document.createElement(tag); if(value !== undefined)n.textContent=value === '' ? '' : display(value); if(className)n.className=className; return n; }
  function button(label, handler, className) { const b=node('button',label,className);b.type='button';b.onclick=handler;return b; }
  function message(id, text, error=false) { el(id).textContent=text;el(id).classList.toggle('rl-error',error); }
  function at(value, timeOnly=false) {
    if (!known(value)) return 'Unavailable';
    const d=new Date(value); if(Number.isNaN(d.getTime()))return display(value);
    return new Intl.DateTimeFormat('en-ZA',{timeZone:'Africa/Johannesburg',...(timeOnly?{}:{day:'numeric',month:'short'}),hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).format(d);
  }
  function emptyRow(target, messageText, columns) { const td=node('td',messageText);td.colSpan=columns;const tr=document.createElement('tr');tr.append(td);target.replaceChildren(tr); }
  function current() { return state.devices.find(d=>d.id===state.selected); }
  function invalidate(kind) { state.editGeneration+=1; if(state.pending[kind]?.uncertain)return; delete state.pending[kind];el(kind==='plan'?'plan-review':'setting-review').hidden=true; }
  function dirtySettings() { invalidate('settings'); const d=current();if(d)state.drafts.set(d.id,collectSettings());message('detail-status','Unsaved changes. Review them before saving.'); }
  async function request(path='', body) {
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),20000);
    try {
      const response=await fetch(api+path,{method:body?'POST':'GET',credentials:'same-origin',cache:'no-store',redirect:'error',signal:controller.signal,headers:{Accept:'application/json',...(body?{'Content-Type':'application/json','X-ROOTLINE-CSRF':state.csrfToken || document.querySelector('meta[name="csrf-token"]')?.content || ''}:{})},...(body?{body:JSON.stringify(body)}:{})});
      let data;try{data=await response.json();}catch{throw new Error('ROOTLINE did not return a readable response. Refresh to check current state.');}
      if(!response.ok || data.success===false){const error=new Error(data.message||data.reason||data.error|| (response.status===401||response.status===403?'Owner access is required. Log in and refresh this page.':'ROOTLINE could not complete this request.'));error.httpStatus=response.status;error.definitive=[400,401,403,404,409,410,422].includes(response.status)&&data.readback_bound!==false;throw error;}
      return data;
    }catch(error){if(error.name==='AbortError')throw new Error('This check took too long. Refresh to check current state; no automatic retry was made.');throw error;}finally{clearTimeout(timer);}
  }
  async function load(panel) {
    const generation=(state.generations[panel]||0)+1;state.generations[panel]=generation;
    try {
      const data=await request('?panel='+encodeURIComponent(panel));if(generation!==state.generations[panel])return;
      delete state.failures[panel];
      if(data.csrf_token)state.csrfToken=data.csrf_token;
      if(typeof data.owner_can_administer==='boolean'){state.canWrite=data.owner_can_administer;el('access').hidden=state.canWrite;el('access').textContent='View only. Log in with owner access to change settings or request a run.';}
      if(data.observed_at)el('observed').textContent='Last retrieved '+at(data.observed_at)+'. Refresh to read current state.';
      if(Array.isArray(data.constraints))el('constraints').replaceChildren(...data.constraints.map(v=>node('li',typeof v==='string'?v:v.reason||v.summary,'rl-small')));
      if(panel==='forecast')renderForecast(data.forecast||{});
      if(panel==='devices'){
        state.devices=Array.isArray(data.devices)?data.devices:[];renderTiles();renderCamps();renderHistoryFilters();renderSupport();
        message('input-state',state.devices.length?'Current command evidence · refreshed '+at(data.observed_at):'Current inputs are unavailable.');
        if(state.selected)renderDetail(false);
      }
      if(panel==='plan'){
        state.plan=data.plan||{};if(!state.planDirty)state.rows=copy(state.plan.rows||[]);renderPlan();renderCamps();
      }
      if(panel==='history'){
        state.history=Array.isArray(data.history)?data.history:(data.history?.rows||[]);renderHistory();renderCamps();
        const historyStatus=typeof data.history==='object'&&!Array.isArray(data.history)?data.history.status:null;
        message('history-state',historyStatus==='unavailable'?(data.history.reason||'History is unavailable.'):((historyStatus==='partial'||data.history?.partial?'Partial history · ':'')+state.history.length+' recorded events returned'+(data.history?.period_days?' · last '+data.history.period_days+' days':'')+'.'+(historyStatus==='partial'||data.history?.partial?' Earlier records are not shown.':'')));
      }
    }catch(error){
      if(generation!==state.generations[panel])return;state.failures[panel]=error.message;
      if(panel==='forecast'){el('forecast').replaceChildren(node('p',error.message,'rl-note rl-warning'));el('weather-source').textContent='Forecast unavailable';}
      if(panel==='devices'){state.canWrite=false;message('input-state',error.message,true);renderTiles();if(state.selected)renderDetail(false);}
      if(panel==='plan'){renderPlan();message('plan-status',error.message,true);el('plan-badge').textContent='Plan unavailable';el('review-plan').disabled=true;if(!state.rows.length)emptyRow(el('plan-rows'),'Today’s plan could not be read.',7);}
      if(panel==='history'){message('history-state',error.message,true);if(!state.history.length)emptyRow(el('history-rows'),'History could not be read.',5);}
    }
  }
  async function refresh() { el('refresh').disabled=true;await Promise.allSettled(['forecast','devices','plan','history'].map(load));el('refresh').disabled=false; }
  function renderForecast(forecast) {
    const days=Array.isArray(forecast.days)?forecast.days.slice(0,3):[];
    el('weather-source').textContent=[human(forecast.status),forecast.source,forecast.forecast_run_at?at(forecast.forecast_run_at):null].filter(known).join(' · ');
    if(forecast.source_url){try{const url=new URL(forecast.source_url);if(['https:','http:'].includes(url.protocol)){const link=node('a',forecast.source||'Forecast source');link.href=url.href;link.target='_blank';link.rel='noopener noreferrer';el('weather-source').append(document.createTextNode(' · '),link);}}catch{/* Invalid attribution URL remains plain source text. */}}
    if(!days.length){el('forecast').replaceChildren(node('p',forecast.reason||'No current three-day forecast is available.','rl-note'));return;}
    el('forecast').replaceChildren(...days.map(day=>{
      const card=node('article',undefined,'rl-weather');const heading=document.createElement('div');
      const parsed=new Date(day.date+'T12:00:00+02:00');const dateLabel=Number.isNaN(parsed.getTime())?display(day.date):new Intl.DateTimeFormat('en-ZA',{timeZone:'Africa/Johannesburg',weekday:'short',day:'numeric',month:'short'}).format(parsed);
      heading.append(node('h3',dateLabel),node('span',known(day.temp_max_c)&&known(day.temp_min_c)?day.temp_max_c+'° / '+day.temp_min_c+'°':'Temperature unavailable','rl-temp'));
      const facts=document.createElement('div');facts.append(node('p',(known(day.rain_mm)?'Rain '+day.rain_mm+' mm':'Rain amount unavailable')+' · '+(known(day.rain_probability_pct)?day.rain_probability_pct+'% chance':'Chance unavailable'),'rl-small'),node('p',known(day.wind_kmh)?'Wind '+day.wind_kmh+' km/h':'Wind unavailable','rl-small rl-muted'),node('p',[day.source,day.forecast_run_at?at(day.forecast_run_at):null].filter(known).join(' · ')||'Source unavailable','rl-small rl-muted'));card.append(heading,facts);return card;
    }));
    if(forecast.reason)el('forecast').append(node('p',forecast.reason,'rl-small rl-muted'));
  }
  function renderTiles() {
    const devices=state.devices.length?state.devices:names.map(([id,name])=>({id,name,state:'Unavailable',summary:'Current input details have not been read.'}));
    el('tiles').replaceChildren(...devices.map(d=>{
      const b=button('',()=>openDevice(d.id),'rl-tile');b.setAttribute('aria-expanded',String(state.selected===d.id));b.setAttribute('aria-controls','rl-detail');b.dataset.device=d.id;b.dataset.on=String(!state.failures.devices&&d.stale!==true&&!(d.controller_availability?.offline_since&&!d.controller_availability?.recovered_at)&&known(d.observed_at)&&['on_command_accepted','controller_on_reported','observed_on'].includes(d.state));b.dataset.family=/eskom|mixer/i.test(d.id)?'power':'water';
      const title=node('span',d.name,'rl-tile-name');const symbol=node('span',/mixer/i.test(d.id)?'↻':/eskom/i.test(d.id)?'ϟ':/borehole/i.test(d.id)?'≋':'♧','rl-tile-symbol');symbol.setAttribute('aria-hidden','true');title.prepend(symbol);
      const availability=d.controller_availability;const elapsed=Number(availability?.offline_elapsed_seconds);const outage=availability?.offline_since&&!availability?.recovered_at;
      const duration=Number.isFinite(elapsed)?(elapsed<60?'less than a minute':elapsed<3600?Math.floor(elapsed/60)+' min':Math.floor(elapsed/3600)+' h '+Math.floor((elapsed%3600)/60)+' min'):'unknown duration';
      if(outage)b.append(node('span',(availability.state==='offline'?'📡 Offline for ':'📡 Connection unconfirmed · outage began ')+duration+(availability.state==='offline'?'':' ago'),'rl-small'));
      b.append(title,node('span',state.failures.devices?'Current state unavailable':human(d.state),'rl-small'),node('span',d.summary||'Summary unavailable','rl-summary'),node('span','Last recorded '+at(d.observed_at),'rl-small rl-muted'),node('span',(modeNames[d.settings?.mode]||'Mode unavailable')+' · Open details →','rl-summary'));return b;
    }));
  }
  function openDevice(id) { if(state.busy)return;if(state.pending.settings?.uncertain){message('detail-status','Check the existing request for '+(state.devices.find(d=>d.id===state.pending.settings.device_id)?.name||'this input')+' before changing input.',true);return;}state.selected=id;invalidate('settings');el('manual').hidden=true;renderDetail(true);renderTiles();el('detail-title').focus({preventScroll:true});el('detail').scrollIntoView({behavior:'smooth',block:'nearest'}); }
  function fieldInput(field,value) {
    const input=field.type==='select'||Array.isArray(field.options)?document.createElement('select'):document.createElement('input');input.dataset.key=field.key;
    if(input.tagName==='SELECT'){
      if(!known(value)){const unknown=node('option','Unavailable');unknown.value='';unknown.disabled=true;input.append(unknown);}
      (field.options||[]).forEach(option=>{const item=node('option',typeof option==='object'?option.label:human(option));item.value=typeof option==='object'?option.value:option;input.append(item);});input.value=known(value)?String(value):'';
    }else{input.type=['number','time','checkbox','text'].includes(field.type)?field.type:'text';if(input.type==='checkbox')input.checked=value===true;else input.value=known(value)?String(value):'';input.placeholder='Unavailable';if(input.type==='number'){input.step=field.step??'any';if(known(field.min))input.min=field.min;if(known(field.max))input.max=field.max;}}
    input.disabled=!state.canWrite||field.editable!==true||!!state.failures.devices;input.required=input.type!=='checkbox'&&field.editable===true&&field.required!==false;input.oninput=dirtySettings;input.onchange=dirtySettings;return input;
  }
  function collectSettings() { const fields={};el('settings').querySelectorAll('[data-key]').forEach(input=>{if(!input.disabled&&(input.required||input.value!==''||input.type==='checkbox'))fields[input.dataset.key]=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?null:Number(input.value)):input.value;});return {revision:state.drafts.get(state.selected)?.revision||current()?.settings?.revision,fields,mode:el('mode').value,scope:el('scope').value,reason:el('settings-reason').value}; }
  function renderDetail(reset=false) {
    el('detail').hidden=false;const d=current();el('detail-title').textContent=d?.name||names.find(x=>x[0]===state.selected)?.[1]||'Input';
    const settings=d?.settings||{};const draft=state.drafts.get(state.selected);const editable=state.canWrite&&!!settings.revision&&!state.failures.devices;
    const facts=[['Controller connection',d?.controller_availability?.state],['Connection checked',at(d?.controller_availability?.checked_at)],['Offline since',at(d?.controller_availability?.offline_since)],['Command state',state.failures.devices?'Unavailable':human(d?.state)],['Evidence',d?.state_basis],['Observed',at(d?.observed_at)],['Next action',typeof d?.next_action==='object'?d.next_action.summary||d.next_action.reason:d?.next_action],['Saved mode',modeNames[settings.mode]],['Settings effective',at(settings.effective_at)],['Settings expire',settings.expires_at?at(settings.expires_at):settings.scope==='ongoing'?'Ongoing':'Unavailable'],['Settings revision',settings.revision]];
    el('facts').replaceChildren(...facts.map(([label,value])=>{const row=node('div',undefined,'rl-fact');row.append(node('span',label,'rl-muted'),node('span',value));return row;}));
    for(const key of ['mode','scope']){const input=el(key);input.querySelector('option[value=""]')?.remove();const value=draft?.[key]??settings[key];if(!known(value)){const option=node('option','Unavailable');option.value='';option.disabled=true;input.prepend(option);}input.value=value||'';input.disabled=!editable||settings.editable===false;}
    el('settings').replaceChildren(...(settings.fields||[]).map(field=>{const label=node('label',field.label+(field.unit?' ('+field.unit+')':''));label.append(fieldInput(field,draft?.fields&&Object.hasOwn(draft.fields,field.key)?draft.fields[field.key]:field.value));if(field.editable!==true)label.append(node('small',field.reason||'Current limit · read only'));else if(field.required===false&&!known(field.value))label.append(node('small',field.reason||'Current plan unavailable. Leave blank to keep the current duration policy.'));else if(known(field.min)||known(field.max))label.append(node('small','Allowed: '+(field.min??'—')+' to '+(field.max??'—')+(field.unit?' '+field.unit:'')));return label;}));
    el('settings-reason').value=draft?.reason||'';el('settings-reason').disabled=!editable;
    el('dependency').textContent=settings.reason||d?.reason||'Current limits must be read before editing.';
    el('review-settings').disabled=!editable;el('reset-settings').disabled=!draft;
    for(const action of ['run','stop']){const spec=d?.actions?.[action];el(action).disabled=!state.canWrite||spec?.supported!==true||!!state.failures.devices;el(action).title=spec?.reason||'';}
    el('action-reasons').textContent=['run','stop'].filter(action=>d?.actions?.[action]?.supported!==true).map(action=>(action==='run'?'Run: ':'Stop: ')+(d?.actions?.[action]?.reason||'Current action availability is unavailable.')).join(' ');
    if(reset)message('detail-status',draft?'Your unsaved draft is retained.':'');
  }
  function renderSupport() { el('support').replaceChildren(...state.devices.filter(d=>!/camp/i.test(d.name)).map(d=>node('span',d.name+' · '+(typeof d.next_action==='string'?d.next_action:d.summary||'Next action unavailable')))); }
  function markPlanDirty() {if(!state.planDirty)state.planDraftRevision=state.plan?.revision;state.planDirty=true;invalidate('plan');el('plan-badge').textContent='Unsaved changes · today only';message('plan-status','');renderPlanOverview();}
  function runEvidence(row) { return state.plan?.rows?.find(current=>current.id===row.id)||{}; }
  function renderPlanOverview() {
    const rows=state.rows;const unavailable=!!state.failures.plan;
    const labels={running:'Running · ON accepted',completed:'Done',stopped:'Stopped',pending:'Waiting',unknown:'Status unknown',unavailable:'Status unavailable'};
    const counts={running:0,completed:0,pending:0,stopped:0,unknown:0,unavailable:0,skipped:0};
    el('plan-journey').replaceChildren(...rows.map((row,index)=>{
      const evidence=runEvidence(row);const status=unavailable?'unavailable':Object.hasOwn(labels,evidence.run_status)?evidence.run_status:'unknown';
      if(row.skip)counts.skipped++;if(Object.hasOwn(counts,status)&&!(row.skip&&status==='pending'))counts[status]++;
      const card=button('',()=>openDevice(row.device_id),'rl-run-card');card.dataset.status=status;
      card.setAttribute('aria-label','Open '+row.name+' run details');
      const top=node('span',undefined,'rl-run-top');top.append(node('span',String(index+1).padStart(2,'0'),'rl-run-number'),node('span',row.name,'rl-run-name'));
      const badge=node('span',evidence.run_status_label&&!unavailable?evidence.run_status_label:labels[status],'rl-run-status');
      card.append(top,badge,node('span',row.skip?'Skipped in today’s plan':display(row.duration_minutes)+' minutes planned','rl-small'));
      card.append(node('span',state.planDirty?'Draft · timing checked on review':row.start_at&&row.end_at?at(row.start_at,true)+' – '+at(row.end_at,true):'Window unavailable','rl-small rl-muted'));
      card.append(node('span',unavailable?'Refresh to read current run evidence':evidence.run_observed_at?'Recorded '+at(evidence.run_observed_at):evidence.run_reason||'Current run evidence unavailable','rl-small rl-muted'),node('span','Details →','rl-run-link'));
      return card;
    }));
    el('plan-progress').textContent=!rows.length?'Today’s run status is not available.':unavailable?'Current plan could not be refreshed.':counts.completed+' done · '+counts.running+' running · '+counts.pending+' waiting'+(counts.skipped?' · '+counts.skipped+' skipped in plan':'')+(counts.stopped?' · '+counts.stopped+' stopped':'')+((counts.unknown+counts.unavailable)?' · '+(counts.unknown+counts.unavailable)+' unknown':'');
  }
  function renderPlan() {
    renderPlanOverview();
    const plan=state.plan||{};el('plan-badge').textContent=state.planDirty?'Unsaved changes · today only':human(plan.status);
    el('plan-explanation').textContent=[plan.operating_date?'Operating day '+plan.operating_date:'',plan.reason].filter(known).join(' · ');
    const canEdit=state.canWrite&&!!plan.revision&&!state.failures.plan;
    el('review-plan').disabled=!canEdit||!state.rows.some(r=>r.editable===true);el('reset-plan').disabled=!state.planDirty;
    if(!state.rows.length){emptyRow(el('plan-rows'),plan.reason||'No saved plan is available for today.',7);el('plan-total').textContent='';return;}
    el('plan-rows').replaceChildren(...state.rows.map((row,i)=>{
      const tr=document.createElement('tr');tr.dataset.skipped=String(row.skip===true);const editable=canEdit&&row.editable===true;
      const order=document.createElement('td');const wrap=node('div',undefined,'rl-order');
      [['↑',-1],['↓',1]].forEach(([label,delta])=>{const b=button(label,()=>{const j=i+delta;[state.rows[i],state.rows[j]]=[state.rows[j],state.rows[i]];state.rows.forEach((r,k)=>r.order=k+1);markPlanDirty();renderPlan();});b.disabled=!editable||i+delta<0||i+delta>=state.rows.length||state.rows[i+delta]?.editable!==true;b.setAttribute('aria-label','Move '+row.name+(delta<0?' earlier':' later'));wrap.append(b);});order.append(wrap);
      const window=node('td',row.skip?'Skipped':state.planDirty?'Rechecked on review':row.start_at&&row.end_at?at(row.start_at,true)+' – '+at(row.end_at,true):'When eligible','rl-window');
      const duration=document.createElement('td');const number=document.createElement('input');number.type='number';number.min='1';number.step='1';if(known(row.maximum_duration_minutes))number.max=row.maximum_duration_minutes;number.value=known(row.duration_minutes)?row.duration_minutes:'';number.disabled=!editable;number.required=true;number.className='rl-duration';number.setAttribute('aria-label',row.name+' duration in minutes');number.oninput=()=>{row.duration_minutes=number.value===''?null:Number(number.value);markPlanDirty();};duration.append(number);
      const priority=document.createElement('td');const select=document.createElement('select');select.disabled=!editable;select.setAttribute('aria-label',row.name+' priority');if(!known(row.priority)){const option=node('option','Unavailable');option.value='';option.disabled=true;select.append(option);}['high','normal','low'].forEach(value=>{const option=node('option',human(value));option.value=value;select.append(option);});select.value=row.priority||'';select.onchange=()=>{row.priority=select.value;markPlanDirty();};priority.append(select);
      const reason=document.createElement('td');const input=document.createElement('input');input.className='rl-reason';input.maxLength=500;input.value=row.reason||'';input.disabled=!editable;input.required=true;input.setAttribute('aria-label',row.name+' reason');input.oninput=()=>{row.reason=input.value;markPlanDirty();};reason.append(input);
      const today=document.createElement('td');const skip=button(row.skip?'Include':'Skip',()=>{row.skip=!row.skip;markPlanDirty();renderPlan();});skip.disabled=!editable;skip.setAttribute('aria-label',(row.skip?'Include ':'Skip ')+row.name+' today');today.append(skip);const camp=node('td',undefined,'rl-plan-camp');camp.append(node('span',row.name));const evidence=runEvidence(row);const status=state.failures.plan?'unavailable':evidence.run_status||'unknown';const badge=node('span',state.failures.plan?'Status unavailable':evidence.run_status_label||'Status unknown','rl-run-status');badge.dataset.status=status;camp.append(badge);tr.append(order,camp,window,duration,priority,reason,today);return tr;
    }));
    const included=state.rows.filter(r=>!r.skip);el('plan-total').textContent=(included.every(r=>Number.isFinite(r.duration_minutes))?included.reduce((sum,r)=>sum+r.duration_minutes,0)+' planned camp minutes':'Planned duration unavailable')+' · actual starts depend on availability';
  }
  function renderCamps() {
    const camps=state.devices.filter(d=>/^camp /i.test(d.name));
    el('camps').replaceChildren(...(camps.length?camps:names.slice(0,4).map(([id,name])=>({id,name}))).map(d=>{
      const card=node('article',undefined,'rl-camp');const row=state.plan?.rows?.find(r=>r.device_id===d.id);const records=state.history.filter(h=>h.device_id===d.id);const summary=d.run_summary;
      card.append(node('h3',d.name),node('p',row?(row.skip?'Skipped today':display(row.duration_minutes)+' minutes planned'):'Today’s plan unavailable'),node('p',summary?.summary||d.summary||'Run summary unavailable','rl-small rl-muted'),node('p',records.length?'Latest: '+records[0].summary+' · '+at(records[0].at):'No activity in the returned history.','rl-small rl-muted'),button('View runs',()=>historyFor(d.id)));return card;
    }));
  }
  function renderHistoryFilters() {const value=el('history-filter').value;const all=node('option','All inputs');all.value='';el('history-filter').replaceChildren(all,...state.devices.map(d=>{const option=node('option',d.name);option.value=d.id;return option;}));const plan=node('option','Day plan');plan.value='plan';el('history-filter').append(plan);el('history-filter').value=value;}
  function renderHistory() {
    const input=el('history-filter').value;const kind=el('history-kind').value;
    const rows=state.history.filter(row=>(!input||row.device_id===input||input==='plan'&&/plan/i.test(row.kind))&&(!kind||(kind==='changes')===/setting|policy|plan|mode/i.test(row.kind)));
    if(!rows.length){emptyRow(el('history-rows'),'No matching records in the returned history.',5);return;}
    el('history-rows').replaceChildren(...rows.map(row=>{const tr=document.createElement('tr');[at(row.at),state.devices.find(d=>d.id===row.device_id)?.name||row.device_name||(/plan/i.test(row.kind)?'Day plan':human(row.device_id)),human(row.kind),[row.summary,row.status?human(row.status):null].filter(known).join(' · '),row.actor||'Unavailable'].forEach(value=>tr.append(node('td',value)));return tr;}));
  }
  function showTab(which,focus=false) {['day','history'].forEach(name=>{el(name).hidden=name!==which;el(name+'-tab').setAttribute('aria-selected',String(name===which));el(name+'-tab').tabIndex=name===which?0:-1;});if(focus)el(which+'-tab').focus();}
  function historyFor(id) {el('history-filter').value=id;renderHistory();showTab('history');el('history').scrollIntoView({behavior:'smooth',block:'start'});}
  function key() { return crypto.randomUUID(); }
  async function preview(kind,body) {
    if(state.busy)return;if(Object.values(state.pending).some(p=>p.uncertain)){message(kind==='plan'?'plan-status':'detail-status','An earlier request has an uncertain result. Use Check same request in its review before submitting another.',true);return;}const slot=kind==='plan'?'plan':'settings';const status=kind==='plan'?'plan-status':'detail-status';invalidate(slot);const editGeneration=state.editGeneration;state.busy=true;message(status,'Checking the proposed change with ROOTLINE…');
    try {
      const data=await request('/preview',{kind,...body,idempotency_key:key()});if(editGeneration!==state.editGeneration)throw new Error('Your draft changed during review. Review the latest changes again.');const p=data.preview;if(!p?.id||!p?.digest)throw new Error(data.message||'ROOTLINE did not return an applicable review. Nothing has been saved.');
      state.pending[slot]={...p,kind,device_id:body.device_id,applyKey:key()};renderReview(slot);message(status,'Review the checked change below. Nothing has been applied yet.');
    }catch(error){message(status,error.message,true);}finally{state.busy=false;}
  }
  function renderReview(slot) {
    const p=state.pending[slot];const container=el(slot==='plan'?'plan-review':'setting-review');container.hidden=false;container.replaceChildren(node('h3',p.kind==='run'?'Review one-off run request':p.kind==='stop'?'Review stop request':slot==='plan'?'Review today’s plan':'Check your setting changes'));
    const list=document.createElement('ul');(p.changes||[]).forEach(change=>list.append(node('li',change.label+': '+display(change.before)+' → '+display(change.after))));if(p.device_id)container.append(node('p','For '+(state.devices.find(d=>d.id===p.device_id)?.name||p.device_id),'rl-small'));container.append(list,node('p','Effective: '+at(p.effective_at)+' · Review expires: '+at(p.expires_at),'rl-small rl-muted'));
    if(p.effective_until)container.append(node('p','This change ends: '+at(p.effective_until),'rl-small rl-muted'));
    (p.warnings||[]).forEach(w=>container.append(node('p',typeof w==='string'?w:w.message||w.reason,'rl-note rl-warning')));
    if(slot==='plan')container.append(node('p','Today only. Current availability and all existing operating limits still apply.','rl-small rl-muted'));
    if(p.kind==='run'||p.kind==='stop')container.append(node('p','This submits a request to ROOTLINE. The current command outcome is shown after the runtime processes it.','rl-small rl-muted'));
    const actions=node('div',undefined,'rl-pills');actions.append(button(p.uncertain?'Check same request':p.kind==='run'||p.kind==='stop'?'Confirm request':'Save reviewed changes',()=>apply(slot),'rl-primary'),...(p.uncertain?[]:[button('Keep editing',()=>invalidate(slot))]));container.append(actions);if(p.uncertain)container.append(node('p','The previous response was uncertain. Checking uses the same request identity, so the backend can reconcile it without creating another command.','rl-note rl-warning'));
  }
  async function apply(slot) {
    const p=state.pending[slot];if(!p||state.busy)return;state.busy=true;root.inert=true;const status=slot==='plan'?'plan-status':'detail-status';const container=el(slot==='plan'?'plan-review':'setting-review');container.querySelectorAll('button').forEach(b=>b.disabled=true);message(status,'Submitting the reviewed change…');
    try {
      const data=await request('/apply',{preview_id:p.id,preview_digest:p.digest,idempotency_key:p.applyKey});
      if(data.readback_bound!==true)throw new Error(data.message||'The result is not confirmed by current records. Your draft is retained. Refresh before trying again.');
      p.uncertain=false;if(p.kind==='settings')state.drafts.delete(p.device_id);if(p.kind==='plan'){state.planDirty=false;state.planDraftRevision=null;}invalidate(slot);el('manual').hidden=true;
      await Promise.allSettled(['devices','plan','history'].map(load));
      const description=(p.kind==='run'||p.kind==='stop')?'Request '+human(data.status):'Saved · revision '+display(data.revision);
      message(status,description+' · effective '+at(data.effective_at)+(data.message?' · '+data.message:''));
    }catch(error){if(error.definitive){delete state.pending[slot];container.hidden=true;await Promise.allSettled(['devices','plan','history'].map(load));message(status,error.message+' Your draft is retained. Discard it to load current values, or review after resolving the conflict.',true);}else{p.uncertain=true;state.pending[slot]=p;await Promise.allSettled(['devices','plan','history'].map(load));renderReview(slot);message(status,error.message+' Your draft and request identity are retained. Check the same request before submitting another.',true);}}
    finally{state.busy=false;root.inert=false;}
  }
  el('refresh').onclick=refresh;
  el('close').onclick=()=>{if(state.busy||state.pending.settings?.uncertain)return;const id=state.selected;state.selected=null;el('detail').hidden=true;invalidate('settings');renderTiles();[...el('tiles').children].find(b=>b.dataset.device===id)?.focus();};
  el('mode').onchange=()=>{if(el('mode').value==='manual_today')el('scope').value='today';dirtySettings();};el('scope').onchange=()=>{if(el('mode').value==='manual_today')el('scope').value='today';dirtySettings();};el('settings-reason').oninput=dirtySettings;
  el('reset-settings').onclick=()=>{state.drafts.delete(state.selected);invalidate('settings');renderDetail(true);message('detail-status','Draft discarded. Current saved settings shown.');};
  el('settings-form').onsubmit=event=>{event.preventDefault();if(!event.currentTarget.reportValidity())return;const d=current();if(!d)return;const values=collectSettings();state.drafts.set(d.id,values);preview('settings',{device_id:d.id,expected_revision:values.revision,reason:values.reason,changes:{fields:values.fields,mode:values.mode,scope:values.scope}});};
  for(const action of ['run','stop'])el(action).onclick=()=>{if(state.busy)return;invalidate('settings');el('manual').hidden=false;el('manual').dataset.action=action;el('manual-title').textContent=(action==='run'?'One-off run request · ':'Stop request · ')+current().name;el('manual-note').textContent=current().actions[action].reason||(action==='run'?'ROOTLINE uses the current plan and limits for this request.':'An accepted request does not yet prove an OFF command was accepted.');el('manual-reason').value='';el('manual-reason').focus();};
  el('manual').onsubmit=event=>{event.preventDefault();if(!event.currentTarget.reportValidity())return;const d=current();preview(event.currentTarget.dataset.action,{device_id:d.id,expected_revision:d.settings?.revision,reason:el('manual-reason').value,changes:{}});};el('manual-cancel').onclick=()=>{el('manual').hidden=true;invalidate('settings');};el('manual-reason').oninput=()=>invalidate('settings');
  el('history-input').onclick=()=>historyFor(state.selected);
  el('reset-plan').onclick=()=>{state.rows=copy(state.plan?.rows||[]);state.planDirty=false;state.planDraftRevision=null;invalidate('plan');renderPlan();message('plan-status','Draft discarded. Current saved plan shown.');};
  el('review-plan').onclick=()=>{if([...el('plan-rows').querySelectorAll('input,select')].some(input=>!input.reportValidity()))return;preview('plan',{expected_revision:state.planDraftRevision||state.plan.revision,reason:'Owner adjustment to today’s irrigation plan',changes:{rows:state.rows.map(({id,order,duration_minutes,priority,reason,skip})=>({id,order,duration_minutes,priority,reason,skip:skip===true}))}});};
  for(const tab of ['day','history']){el(tab+'-tab').onclick=()=>showTab(tab);el(tab+'-tab').onkeydown=event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();showTab(event.key==='Home'?'day':event.key==='End'?'history':tab==='day'?'history':'day',true);}};}
  el('history-filter').onchange=renderHistory;el('history-kind').onchange=renderHistory;
  window.addEventListener('beforeunload',event=>{if(state.planDirty||state.drafts.size||Object.values(state.pending).some(p=>p.uncertain)){event.preventDefault();event.returnValue='';}});
  el('date').textContent=new Intl.DateTimeFormat('en-ZA',{timeZone:'Africa/Johannesburg',weekday:'long',day:'numeric',month:'long'}).format(new Date());
  renderTiles();renderCamps();refresh();
})();
