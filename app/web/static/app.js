'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const csrf = $('meta[name="csrf-token"]').content;
let state, busy = false, lastChoice = null;
let advanced = localStorage.getItem('frame-advanced') === 'true';
let tvId = sessionStorage.getItem('frame-tv') || 'primary';
let library = {q:'', behavior:'all', page:1}, artPage = {items:[],total:0,page:1,pages:1};
let matteView = 'colors', matteQuery = '', matteFamily = 'all', mattePage = 1;
const mediaURL = (category,file) => `/media/${category}/${encodeURIComponent(file)}?tv=${encodeURIComponent(tvId)}`;
const styleInfo = family => ({modernthin:'Thin border', modern:'Medium border', modernwide:'Wide border',shadowbox:'Inset artwork with shadow depth',none:'No matte',flexible:'Device-controlled flexible layout',panoramic:'Panoramic layout',triptych:'Three-panel layout',mix:'Mixed layout',squares:'Square-panel layout'}[family] || 'Device-defined layout');
const page = document.body.dataset.page;
const swatch = (color, title='') => `<span class="swatch" style="background:${esc(color)}" title="${esc(title)}"></span>`;
const palette = colors => (colors || []).map(c => swatch(c.hex, `${c.percentage}%`)).join('');
const opts = (values, selected) => values.map(v => `<option value="${esc(v)}" ${v === selected ? 'selected' : ''}>${esc(v)}</option>`).join('');
const matteOptions = selected => (state.mattes || []).map(m => `<option value="${esc(m.id)}" ${m.id === selected ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
const button = (label, action, extra='') => `<button data-action="${action}" ${extra}>${label}</button>`;
const fmt = value => value ? new Date(value).toLocaleString() : '—';
async function api(path, data={}) {
  const multipart = data instanceof FormData;
  const r = await fetch(path, {method:'POST', headers: {'X-CSRF-Token':csrf, 'X-Frame-ID':tvId, ...(multipart ? {} : {'Content-Type':'application/json'})}, body:multipart ? data : JSON.stringify(data)});
  const result = await r.json();
  if (!r.ok) throw Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
  return result;
}
function message(text) { $('#notice').textContent = text || ''; }
async function refresh(render=true) {
  const requestedTV=tvId;
  const r = await fetch('/api/state', {headers:{'X-Frame-ID':requestedTV}});
  if (!r.ok) {if (r.status===404 && tvId!=='primary') {tvId='primary';sessionStorage.removeItem('frame-tv');return refresh(render);} throw Error('Unable to load TV');}
  const loaded=await r.json();if(requestedTV!==tvId)return;state=loaded;
  $('.tv-picker').hidden = state.televisions.length < 2;
  $('#tv-select').innerHTML = state.televisions.map(t=>`<option value="${esc(t.id)}" ${t.id===tvId?'selected':''}>${esc(t.name)}</option>`).join('');
  if (page==='artwork') {
    const query=new URLSearchParams({...library,size:24});
    const result=await fetch('/api/artworks?'+query,{headers:{'X-Frame-ID':tvId}});
    const loadedArt=await result.json();if(requestedTV!==tvId)return;artPage=loadedArt;
  }
  $('#connection').textContent = `${state.mock ? 'Demo · ' : ''}${state.connected ? 'Connected' : 'Not connected'}${state.device?.model ? ' · '+state.device.model : ''}`;
  if (render) renderPage();
}
function preview(matte, small=false, artwork=state.artwork) {
  return `<div class="preview ${small ? 'small' : ''}" style="background:#dedbd2"><div class="frame" data-family="${esc(matte?.family || 'modern')}" style="background:${esc(matte?.hex || '#e8e5dc')}">${artwork?.image ? `<div class="matte-window"><img alt="Locally analyzed artwork" src="${mediaURL('artwork',artwork.image)}"></div>` : '<div class="empty">Artwork image unavailable</div>'}</div></div>`;
}
function choiceButtons(matte) {
 if(state.settings.color_mode==='fixed')return '<a href="/strategy">Change fixed color in Preferences</a>';
 return button('Use this','choose-matte',`data-matte="${esc(matte.id)}"`);
}
function automationSummary() {
 if (!state.connected) return 'Your Frame is disconnected. Check that it is on and connected to your network.';
 if (state.artmode!=='on') return 'Ready when your Frame returns to Art Mode.';
 if (!state.settings.automation) return 'Automatic colors are paused. You can still choose a border below.';
 if (state.current_override?.mode==='never') return 'This artwork is set to keep its current border.';
 if (state.settings.color_mode==='fixed') return 'Using '+state.settings.fixed_color+' for every artwork.';
 if (state.current_override?.mode==='force') return 'Keeping your saved border for this artwork.';
 if (state.current_override?.mode==='never') return 'This artwork is set to keep its current border.';
 if (state.message?.includes('Never modify')) return 'This artwork is set to keep its current border.';
 return `Adapting colors automatically${state.settings.preferred_family_only ? ' · Keeping your '+state.settings.preferred_family.replace(/^./,c=>c.toUpperCase())+' style' : ''}.`;
}
function choiceFollowup() {
 if (!lastChoice || lastChoice.tv!==tvId || lastChoice.content!==state.current?.content_id) return '';
 return `<div class="card"><p>Using ${esc(lastChoice.name)}.</p>${button('Keep for this artwork','remember-choice','class="secondary"')} <small>Optional: keep this choice as artwork changes.</small></div>`;
}
function dashboard() {
 const current=state.current || {}, fixed=state.settings.color_mode==='fixed';
 const fixedMatte=state.mattes.find(m=>m.color===state.settings.fixed_color&&(!state.settings.preferred_family||m.family===state.settings.preferred_family));
 const top=fixed && fixedMatte ? {matte:fixedMatte,reasons:['Used for every artwork while fixed color is on']} : state.recommendations?.[0];
 if (!state.device?.model) return `<div class="card empty"><h2>A thoughtful frame for every artwork.</h2><p>Connect your Frame to get started.</p><a class="button" href="/setup">Set up your Frame</a></div>`;
 const attention=!state.connected;
 return `<div class="card"><div class="row spread"><div><h2>${state.settings.automation?(fixed?'Fixed color':'Automatic colors'):'Automation paused'}</h2><p>${esc(automationSummary())}</p>${attention?'<a href="/televisions">Check your TV connection</a>':''}</div>${button(state.settings.automation?'Pause':'Resume',state.settings.automation?'pause':'resume','class="secondary"')}</div></div>${choiceFollowup()}
 <div class="two"><div class="card"><div class="row spread"><h2>On your Frame</h2><span class="badge">Artwork only</span></div>${preview(state.mattes.find(m=>m.id===current.matte_id))}<p>${esc(state.mattes.find(m=>m.id===current.matte_id)?.name || 'Waiting for artwork')}</p><small>Approximate preview. Colors on your TV may look different.</small></div>
 <div class="card"><span class="step">${fixed?'Your fixed color':'Suggested for your artwork'}</span><h2>${esc(top?.matte.name || 'Waiting for a recommendation')}</h2>${top?`<p>${esc(top.reasons.slice(0,2).map(r=>r.replace('Harmony with the artwork perimeter','Works with the colors at the artwork’s edges').replace('Harmony with the artwork palette','Complements the artwork’s colors').replace('Restrained chroma keeps the artwork dominant','Quiet colors let the artwork stand out').replace('Balanced lightness transition','Balances light and dark tones')).join('. '))}.</p>${top.matte.id===current.matte_id?'<p>Already on your Frame.</p>':choiceButtons(top.matte)}`:'<p>An available artwork image is needed to suggest a border.</p>'}<p>${button('Refresh suggestion','evaluate','class="secondary"')}</p></div></div>
 ${state.settings.color_mode==='automatic' && state.recommendations?.length>1?`<details><summary>Try another color</summary><div class="grid">${state.recommendations.slice(1,4).map(r=>`<div class="card">${preview(r.matte,true)}<h3>${esc(r.matte.name)}</h3>${choiceButtons(r.matte)}</div>`).join('')}</div></details>`:''}
 <details class="advanced-only"><summary>Analysis and connection details</summary><p>${esc(state.message)}</p><p>${esc(current.content_id)}</p>${palette(state.artwork?.analysis?.palette)}<p>Last TV communication: ${fmt(state.last_communication)}</p>${state.recommendations?.length?scores():''}</details>${state.mock?button('Change demo artwork','mock-next','class="secondary"'):''}`;
}
function scores() { return `<div class="scroll"><table><thead><tr><th>Matte</th><th>Score</th><th>Frame finish</th>${Object.keys(state.settings.weights).map(k=>`<th>${k}</th>`).join('')}</tr></thead><tbody>${state.recommendations.map(r=>`<tr><td>${esc(r.matte.name)}${choiceButtons(r.matte)}</td><td>${r.score}</td><td>${r.finish_adjustment ?? 0}</td>${Object.keys(state.settings.weights).map(k=>`<td>${r.components[k]}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`; }
function setup() {
 return `<div class="card"><h2>Find your Frame</h2><p>Discover your TV or enter its network address.</p><form data-form="discover"><label>Optional network range<input name="subnet" placeholder="192.168.1.0/24"></label><button>Find Samsung TVs</button></form><div id="discoveries"></div><form data-form="connect"><label>TV address<input name="ip" placeholder="192.168.1.50" ${state.mock?'':'required'}></label><button>Connect to this Frame</button></form><p>Press Allow if your TV asks to connect. Your pairing stays saved here.</p></div><div class="card"><h2>Choose your look</h2><p>Once connected, choose your border style and either automatic colors or one fixed color.</p><a class="button" href="/strategy">Open Preferences</a>${button('Finish setup','finish-setup','class="secondary"')}</div>`;
}
function artworks() {
 return `<form class="card row" data-form="art-filter"><label>Search artwork ID<input name="q" maxlength="100" value="${esc(library.q)}" placeholder="Search your library"></label><label>Behavior<select name="behavior">${opts(['all','automatic','force','never'],library.behavior)}</select></label><button>Search</button></form><p>${artPage.total} artworks · Page ${artPage.page} of ${artPage.pages}</p><div class="row">${button('Previous','art-prev',`class="secondary" ${artPage.page<=1?'disabled':''}`)}${button('Next','art-next',`class="secondary" ${artPage.page>=artPage.pages?'disabled':''}`)}</div><div class="grid">${artPage.items.map(a=>{const o=a.override; return `<div class="card">${a.image ? `<img class="thumb" loading="lazy" src="${mediaURL('artwork',a.image)}" alt="Artwork">` : '<p>Image unavailable</p>'}<h3>${esc(a.content_id)}</h3><p>${palette(a.analysis?.palette)}</p><small>Seen ${fmt(a.last_seen)}<br>Last matte: ${esc(a.current_matte)}<br>Recommendation: ${esc(a.recommendation?.matte?.name || "Awaiting analysis")} ${a.recommendation ? " · "+a.recommendation.score+"/100" : ""}</small><form data-form="override" data-id="${esc(a.content_id)}"><label>Behavior<select name="mode">${opts(['automatic','force','never'],o.mode)}</select></label><label>Forced matte<select name="matte">${matteOptions(o.matte)}</select></label><button>Save override</button></form><details><summary>Provide your own local image</summary><form data-form="local-image" data-id="${esc(a.content_id)}"><input type="file" name="file" accept="image/jpeg,image/png,image/webp" required><p><button>Save local reference</button></p></form></details></div>`;}).join('') || '<div class="card">Known artwork appears here after Art Mode is displayed.</div>'}</div>`;
}
function styleControl() {
 const s=state.settings;
 return `<form data-form="frame-style"><label>Frame style<select name="preferred_family"><option value="">Let the app choose</option>${[...new Set(state.mattes.map(m=>m.family))].map(f=>`<option value="${esc(f)}" ${s.preferred_family===f?'selected':''}>${esc(f==='none'?'No border':f.replace('modernthin','Modern thin').replace('modernwide','Modern wide').replace('shadowbox','Shadowbox'))} — ${esc(styleInfo(f))}</option>`).join('')}</select></label><label class="inline"><input type="checkbox" name="preferred_family_only" ${s.preferred_family_only?'checked':''}>Keep this style and only adapt the color</label><button>Save frame style</button></form>`;
}
function mattes() {
 const current=state.mattes.find(m=>m.id===state.current?.matte_id);
 const colors=[...new Set(state.mattes.filter(m=>m.family!=='none').map(m=>m.color))];
 return `<div class="two"><div class="card"><h2>Your frame</h2>${preview(current,true)}<p>${esc(current?.name || 'Waiting for your TV')}</p><small>Approximate preview of the current border.</small></div><div class="card"><h2>Choose the look you like</h2><p>Keep a favorite border style while the color adapts to your artwork.</p>${styleControl()}</div></div><div class="card"><h2>Your TV's colors</h2><p>The app chooses from these colors automatically. You can try another recommendation from the Dashboard.</p><div class="color-palette">${colors.map(c=>{const m=state.mattes.find(m=>m.color===c);return `<div>${swatch(m.hex)}<span>${esc(c)}</span></div>`;}).join('')}</div></div>${advanced?`<details><summary>Advanced color and style preferences</summary>${advancedMattes()}</details>`:''}`;
}
function advancedMattes() {
 const found=state.mattes.filter(m=>(matteFamily==='all'||m.family===matteFamily) && `${m.name} ${m.family} ${m.color}`.toLowerCase().includes(matteQuery.toLowerCase()));
 const field=matteView==='styles'?'family':'color';
 let items=matteView==='combinations'?found:[...new Set(found.map(m=>m[field]))].map(value=>({value,rows:state.mattes.filter(m=>m[field]===value)}));
 const pages=Math.max(1,Math.ceil(items.length/24));mattePage=Math.min(mattePage,pages);
 const count=items.length;items=items.slice((mattePage-1)*24,mattePage*24);
 return `<div class="card"><h2>Styles, colors, and depth</h2><p>Your TV exposes ${new Set(state.mattes.map(m=>m.family)).size} styles and ${new Set(state.mattes.filter(m=>m.family!=='none').map(m=>m.color)).size} colors. These are the choices advertised by this TV’s local Art API. Its supported matte command selects a style/color ID; it does not expose arbitrary HEX colors or border widths.</p><p>Custom appearance values below improve local scoring and previews; they do not create a new TV matte color. Width and built-in shadow depth are selected through supported styles. Previews are schematic, not measurements; multi-panel layouts are labeled but not reproduced.</p><form data-form="matte-filter" class="row"><label>View<select name="view">${opts(['colors','styles','combinations'],matteView)}</select></label><label>Search<input name="q" value="${esc(matteQuery)}" maxlength="100"></label><label>Style<select name="family">${opts(['all',...new Set(state.mattes.map(m=>m.family))],matteFamily)}</select></label><button>Filter</button></form></div><p>${count} results · Page ${mattePage} of ${pages}</p><div class="row">${button('Previous','matte-prev',`class="secondary" ${mattePage<=1?'disabled':''}`)}${button('Next','matte-next',`class="secondary" ${mattePage>=pages?'disabled':''}`)}</div><div class="grid">${items.map(item=>{
 if(matteView==='combinations'){const m=item;return `<form class="card" data-form="matte" data-id="${esc(m.id)}"><h3>${swatch(m.hex)} ${esc(m.name)}</h3><small>${esc(m.source)} · ${esc(styleInfo(m.family))}</small><label class="inline"><input type="checkbox" name="enabled" ${m.enabled?'checked':''}>Enabled</label><label>Preference<select name="preference">${opts(['normal','preferred','avoid'],m.preference)}</select></label><details><summary>Custom measured appearance</summary><input type="color" name="hex" value="${esc(m.hex)}" data-original="${esc(m.hex)}"></details><button class="secondary">Save this combination</button></form>`;}
 const rows=item.rows,m=rows[0], prefs=[...new Set(rows.map(r=>r.preference))];
 return `<form class="card" data-form="matte-group" data-field="${field}" data-value="${esc(item.value)}"><h3>${swatch(m.hex)} ${esc(item.value)}</h3>${matteView==='styles'?preview(rows.find(r=>r.color==='polar')||m,true):''}<p>${matteView==='styles'?esc(styleInfo(item.value)):esc(m.source)} · ${rows.length} combinations</p><label class="inline"><input type="checkbox" name="enabled" ${rows.every(r=>r.enabled)?'checked':''}>Enable all matching combinations</label><label>Preference for this ${field}<select name="preference">${opts(['normal','preferred','avoid'],prefs.length===1?prefs[0]:'normal')}</select></label>${prefs.length>1?'<small>Individual combinations have mixed preferences.</small>':''}${field==='color' && item.value!=='none'?`<details><summary>Custom measured appearance</summary><p>Calibrate how this supported color appears. Applies across its styles.</p><input type="color" name="calibration_picker" value="${esc(m.hex)}" aria-label="Color appearance"><label>Measured HEX<input name="hex" value="${esc(m.hex)}" data-original="${esc(m.hex)}" pattern="#[0-9a-fA-F]{6}"></label></details>`:''}<button class="secondary">Save ${field} preferences</button></form>`;
 }).join('')}</div>`;
}
function televisions() {
 return `<div class="card"><h2>Your Frames</h2><p>Each TV has its own pairing, preferences, artwork choices and history. Every configured TV keeps its own automation running even when you view another.</p><a class="button" href="/setup">Discover / pair selected TV</a></div><div class="grid">${state.televisions.map(t=>`<div class="card"><h3>${esc(t.name)}</h3><p>${esc(t.model||'Not paired yet')} · ${t.connected?'Connected':'Not connected'} · Automation ${t.automation?'on':'paused'}</p>${button(t.id===tvId?'Selected':'Select TV','tv-select',`data-id="${esc(t.id)}" ${t.id===tvId?'disabled':''}`)}</div>`).join('')}</div><div class="two"><form class="card" data-form="tv-add"><h2>Add another TV</h2><label>Room or TV name<input name="name" required maxlength="80" placeholder="Bedroom Frame"></label><button>Add TV and open setup</button></form><form class="card" data-form="tv-name"><h2>Name selected TV</h2><label>Name<input name="name" required maxlength="80" value="${esc(state.televisions.find(t=>t.id===tvId)?.name)}"></label><button>Save name</button></form></div>`;
}

function strategy() {
 const s=state.settings, colors=[...new Set(state.mattes.filter(m=>m.enabled&&m.family!=='none'&&(!s.preferred_family||m.family===s.preferred_family)).map(m=>m.color))];
 return `<div class="card"><h2>Your border style</h2>${styleControl()}</div><form class="card" data-form="strategy"><h2>Matte color</h2><label>Choose colors<select name="color_mode">${[['automatic','Automatically for each painting'],['fixed','Always use one color']].map(([v,t])=>`<option value="${v}" ${s.color_mode===v?'selected':''}>${t}</option>`).join('')}</select></label><label data-fixed-controls>Fixed color<select name="fixed_color"><option value="">Choose a color</option>${opts(colors,s.fixed_color)}</select></label><p>A fixed color applies to every artwork, even without a thumbnail. Never modify exceptions are respected. Pause on Home stops all automatic changes.</p><label>Physical frame finish<select name="frame_finish">${[['unspecified','No preference'],['white','White'],['black','Black'],['light_wood','Light wood'],['dark_wood','Dark wood'],['warm_metal','Warm metal'],['cool_metal','Cool metal']].map(([v,t])=>`<option value="${v}" ${s.frame_finish===v?'selected':''}>${t}</option>`).join('')}</select></label><small>This describes the physical trim around your TV. It gently influences automatic choices; it never changes a fixed color.</small><label data-auto-controls>Automatic look<select name="strategy">${opts(['Gallery','Adaptive','Subtle','Contrast'],s.strategy)}</select></label><p>Gallery favors quiet, light neutrals that support the painting.</p><details class="advanced-only"><summary>Fine tuning</summary><label>Neutral preference<input name="neutral_preference" type="number" min="0" max="3" step="0.1" value="${s.neutral_preference}"></label><label>Minimum score improvement<input name="threshold" type="number" min="0" max="100" value="${s.threshold}"></label><label>Seconds between automatic changes<input name="cooldown" type="number" min="0" max="86400" value="${s.cooldown}"></label>${Object.entries(s.weights).map(([k,v])=>`<label>${esc(k)} weight<input name="weight_${k}" type="number" min="0" max="100" value="${v}"></label>`).join('')}</details><button>Save preferences</button></form>`;
}
function history() { return `<div class="card scroll"><table><thead><tr><th>When</th><th>Artwork</th><th>Change</th><th>Score / mode</th><th>Reason</th></tr></thead><tbody>${state.history.map(h=>`<tr><td>${fmt(h.timestamp)}</td><td>${esc(h.artwork)}</td><td>${esc(h.previous)} → ${esc(h.new)}<br>${esc(h.status)}</td><td>${h.score ?? '—'}<br>${esc(h.mode)}</td><td>${esc(h.reason)}</td></tr>`).join('')}</tbody></table></div>`; }
function diagnostics() { return `<div class="card"><h2>Local connection</h2><p>${esc(state.error || 'No recorded error')}</p><p>Version ${esc(state.version)} · Art Mode ${esc(state.artmode || 'unknown')} · Last communication ${fmt(state.last_communication)}</p><pre>${esc(JSON.stringify({device:state.device, capabilities:state.capabilities},null,2))}</pre><p>Event names listed above have actually been observed during this session. Polling remains active as a fallback. No cloud ambient sensor is used.</p>${button('Refresh capabilities','capabilities')}<details><summary>Advertised matte IDs</summary><pre>${esc(state.mattes.map(m=>m.id).join('\n'))}</pre></details><p>Use <code>python scripts/frame_probe.py --help</code> for the state-preserving physical test.</p></div>`; }
function settings() { const s=state.settings; return `<div class="card"><h2>Manage your setup</h2><div class="settings-links"><a href="/televisions">Your TVs & discovery</a><a href="/artwork">Artwork library & saved choices</a><a href="/mattes">Frame styles & color catalog</a><a href="/history">Recent changes</a><a href="/diagnostics">Connection & troubleshooting</a></div></div><div class="card"><h2>Make it yours</h2><label class="inline"><input id="advanced-toggle" type="checkbox" ${advanced?'checked':''}>Show advanced controls</label><p>Extra color tuning, detailed scores, and troubleshooting. The defaults work well for most artwork.</p></div><div class="card"><h2>TV setup</h2><p>You can change TVs or reconnect without deleting the database.</p><a class="button" href="/setup">Run setup wizard</a></div><div class="card advanced-only"><h2>When an image is unavailable</h2><form data-form="fallback"><label>Behavior<select name="fallback">${opts(['retain','safe'],s.fallback)}</select></label><label>Safe default matte<select name="safe_matte">${matteOptions(s.safe_matte)}</select></label><label class="inline"><input type="checkbox" name="requires_reselect" ${s.requires_reselect ? 'checked' : ''}>Re-select current artwork after matte changes</label><p><small>Enable only after physical testing confirms your model needs it. Art Mode must be on; this never wakes the TV.</small></p><button>Save behavior</button></form></div><div class="card"><h2>Privacy & security</h2><p>Pairing tokens and artwork analysis remain in your persistent data directory. No telemetry, cloud AI or Samsung account credentials. Do not expose this UI directly to the public internet.</p></div>`; }
function renderPage() {
 const renderers = {dashboard, setup, televisions, artwork:artworks, mattes, strategy, history, diagnostics, settings};
 document.body.classList.toggle('advanced',advanced);
 $('#content').innerHTML = (renderers[page] || dashboard)();
 updateColorControls();
}
document.addEventListener('click', async event => {
 const b=event.target.closest('[data-action]'); if(!b || busy) return;
 const a=b.dataset.action; busy=true; b.disabled=true;
 try {
  if(a==='tv-select') {tvId=b.dataset.id;sessionStorage.setItem('frame-tv',tvId);library.page=1;await refresh();}
  else if(a==='choose-matte') {const choice={tv:tvId,content:state.current.content_id,matte:b.dataset.matte,name:state.mattes.find(m=>m.id===b.dataset.matte)?.name || 'your choice'};await api('/api/recommendations/apply',{content_id:choice.content,matte_id:choice.matte,remember:false});lastChoice=choice;await refresh();message('Border updated.');}
  else if(a==='remember-choice') {if(!lastChoice || lastChoice.tv!==tvId)throw Error('Choose a border first');await api('/api/recommendations/apply',{content_id:lastChoice.content,matte_id:lastChoice.matte,remember:true});lastChoice=null;await refresh();message('Kept for this artwork. You can change this in Settings → Artwork library & saved choices.');}
  else if(a==='art-prev'||a==='art-next') {library.page=artPage.page+(a==='art-next'?1:-1);await refresh();}
  else if(a==='matte-prev'||a==='matte-next') {mattePage+=a==='matte-next'?1:-1;renderPage();}
  else if(a==='discovered-connect') {const input=$('[data-form="connect"] input');input.value=b.dataset.ip;input.scrollIntoView({behavior:'smooth',block:'center'});message('TV selected. Use Connect to pair.');}
  else if(a==='finish-setup') {await api('/api/settings',{setup_complete:true}); location.href='/';}
  else if(a==='capabilities') {await api('/api/capabilities'); await refresh();}
  else if(a==='mock-next') {await api('/api/mock/next'); await api('/api/action/evaluate'); await refresh();}
  else {const r=await api('/api/action/'+a); await refresh(); message(r.message || 'Updated.');}
 } catch(e) {message(e.message);} finally {busy=false; b.disabled=false;}
});
function updateColorControls(){const mode=document.querySelector('[name="color_mode"]')?.value;document.querySelectorAll('[data-fixed-controls]').forEach(e=>e.hidden=mode!=='fixed');document.querySelectorAll('[data-auto-controls]').forEach(e=>e.hidden=mode==='fixed');}
document.addEventListener('change', async e=>{
 if(e.target.name==='color_mode')updateColorControls();
 if(e.target.id==='advanced-toggle'){advanced=e.target.checked;localStorage.setItem('frame-advanced',String(advanced));renderPage();return;}
 if(e.target.id==='tv-select') {if(busy){e.target.value=tvId;return;}tvId=e.target.value;sessionStorage.setItem('frame-tv',tvId);library.page=1;await refresh();return;}
 if(e.target.name==='calibration_picker') e.target.form.elements.hex.value=e.target.value;
 if(e.target.name==='picker') e.target.form.elements.color.value=e.target.value;
 if(e.target.name==='color' && /^#[a-f0-9]{6}$/i.test(e.target.value)) e.target.form.elements.picker.value=e.target.value;
});
document.addEventListener('submit', async e=>{
 const f=e.target; if(!f.dataset.form) return; e.preventDefault(); if(busy) return;
 busy=true; const submit=f.querySelector('button'); submit.disabled=true;
 const data=Object.fromEntries(new FormData(f));
 try {
  switch(f.dataset.form) {
   case 'frame-style': await api('/api/settings',{preferred_family:data.preferred_family,preferred_family_only:f.elements.preferred_family_only.checked});await refresh();message('Frame style saved.');break;
   case 'tv-add': {const created=await api('/api/televisions',data);tvId=created.id;sessionStorage.setItem('frame-tv',tvId);location.href='/setup';break;}
   case 'tv-name': await api('/api/television/name',data);await refresh();break;
   case 'art-filter': library={...data,page:1};await refresh();break;
   case 'matte-filter': matteView=data.view;matteQuery=data.q;matteFamily=data.family;mattePage=1;renderPage();break;
   case 'matte-group': {delete data.calibration_picker;data.enabled=f.elements.enabled.checked;if(f.elements.hex && data.hex===f.elements.hex.dataset.original)delete data.hex;await api('/api/mattes/bulk',{...data,field:f.dataset.field,value:f.dataset.value});await refresh();break;}
   case 'discover': {message('Searching Samsung services…'); const found=await api('/api/discover',data); $('#discoveries').innerHTML=found.map(d=>`<p><strong>${esc(d.name)} · ${esc(d.model)}</strong> · ${esc(d.ip || 'Demo')} · Art Mode ${d.art_supported ? 'supported' : 'unknown'} ${d.ip?button('Choose this TV','discovered-connect',`data-ip="${esc(d.ip)}" class="secondary"`):''}</p>`).join('') || '<p>No TV found. Enter its network address, or try the optional network search above.</p>'; if(found[0]?.ip) $('[data-form="connect"] input').value=found[0].ip; break;}
   case 'connect': message('Look at the TV: press Allow if Samsung displays an authorization popup.'); await api('/api/connect',data); await refresh(); message('Paired. Capability profile saved.'); break;
   case 'override': await api('/api/override',{...data,content_id:f.dataset.id}); await refresh(); break;
   case 'local-image': await api(`/api/artwork/${encodeURIComponent(f.dataset.id)}/image`,new FormData(f)); message('Local reference stored. Re-evaluate to analyze it.'); break;
   case 'matte': data.enabled=f.elements.enabled.checked; if(data.hex===f.elements.hex.dataset.original) delete data.hex; await api('/api/matte',{...data,id:f.dataset.id}); await refresh(); break;
   case 'strategy': {const weights={}; for(const k of Object.keys(data)) if(k.startsWith('weight_')) {weights[k.slice(7)]=Number(data[k]); delete data[k];} for(const k of ['threshold','cooldown','neutral_preference']) data[k]=Number(data[k]); await api('/api/settings',{...data,weights}); await refresh(); message('Preferences saved.'); break;}
   case 'fallback': await api('/api/settings',{...data,requires_reselect:f.elements.requires_reselect.checked}); await refresh(); break;
  }
 } catch(err) {message(err.message);} finally {busy=false; submit.disabled=false;}
});
refresh().catch(e=>message(e.message));
setInterval(()=>{if(!busy && page==='dashboard' && !document.activeElement?.matches('input,select'))refresh().catch(()=>{});},10000);
