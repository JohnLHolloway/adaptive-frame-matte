'use strict';
const $ = s => document.querySelector(s);
const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const csrf = $('meta[name="csrf-token"]').content;
let state, previewProfile = 'day', busy = false;
const page = document.body.dataset.page;
const swatch = (color, title='') => `<span class="swatch" style="background:${esc(color)}" title="${esc(title)}"></span>`;
const palette = colors => (colors || []).map(c => swatch(c.hex, `${c.percentage}%`)).join('');
const opts = (values, selected) => values.map(v => `<option value="${esc(v)}" ${v === selected ? 'selected' : ''}>${esc(v)}</option>`).join('');
const matteOptions = selected => (state.mattes || []).map(m => `<option value="${esc(m.id)}" ${m.id === selected ? 'selected' : ''}>${esc(m.name)}</option>`).join('');
const button = (label, action, extra='') => `<button data-action="${action}" ${extra}>${label}</button>`;
const fmt = value => value ? new Date(value).toLocaleString() : '—';
async function api(path, data={}) {
  const multipart = data instanceof FormData;
  const r = await fetch(path, {method:'POST', headers: {'X-CSRF-Token':csrf, ...(multipart ? {} : {'Content-Type':'application/json'})}, body:multipart ? data : JSON.stringify(data)});
  const result = await r.json();
  if (!r.ok) throw Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
  return result;
}
function message(text) { $('#notice').textContent = text || ''; }
async function refresh(render=true) {
  const r = await fetch('/api/state'); state = await r.json();
  $('#connection').textContent = `${state.mock ? 'Demo · ' : ''}${state.connected ? 'Connected' : 'Not connected'}${state.device?.model ? ' · '+state.device.model : ''}`;
  if (render) renderPage();
}
function preview(matte, small=false, artwork=state.artwork) {
  const room = state.rooms[previewProfile] || state.room;
  return `<div class="preview ${small ? 'small' : ''}" style="background:${esc(room?.wall_hex || '#dedbd2')}"><div class="frame" style="background:${esc(matte?.hex || '#e8e5dc')}">${artwork?.image ? `<img alt="Locally analyzed artwork" src="/media/artwork/${esc(artwork.image)}">` : '<div class="empty">Artwork image unavailable</div>'}</div></div>`;
}
function dashboard() {
  const current = state.current || {}, top = state.recommendations?.[0];
  if (!state.device?.model) return `<div class="card empty"><h2>A thoughtful frame for every artwork.</h2><p>Connect your Frame and calibrate your room to get started.</p><a class="button" href="/setup">Set up your Frame</a></div>`;
  return `<div class="two"><div class="card"><div class="row spread"><h2>On your Frame</h2><span class="badge">${esc(state.profile || 'day')} profile</span></div>
    ${preview(top?.matte)}<div class="row spread"><p>${esc(current.content_id || 'Waiting for Art Mode')}</p><div class="row">${button('Day','preview-day','class="secondary"')}${button('Night','preview-night','class="secondary"')}</div></div>
    <small>Approximate preview. Browser colors differ from the TV and your room.</small>
    <div class="row"><div class="metric">Artwork palette<b>${palette(state.artwork?.analysis?.palette)}</b></div><div class="metric">Perimeter<b>${palette(state.artwork?.analysis?.edge_palette)}</b></div></div>
    <p>${esc(state.message)}</p><div class="row">${button('Re-evaluate','evaluate','class="secondary"')}${state.mock ? button('Change demo artwork','mock-next','class="secondary"') : ''}</div></div>
    <div><div class="card"><span class="step">Recommended matte</span><h2>${esc(top?.matte.name || 'Awaiting analysis')}</h2>${top ? `<div class="score">${top.score}<small> / 100</small></div>${top.reasons.map(r => `<div class="reason">${esc(r)}</div>`).join('')}<p>${button('Apply Recommendation','apply')}</p>` : '<p>Add a room profile and a usable artwork image to see recommendations.</p>'}
    <div class="metric">Current matte<b>${esc(current.matte_id || '—')}</b></div></div>
    <div class="card"><div class="row spread"><h3>Automation ${state.settings.automation ? 'on' : 'paused'}</h3>${button(state.settings.automation ? 'Pause' : 'Resume',state.settings.automation ? 'pause' : 'resume','class="secondary"')}</div>
    <p>${swatch(state.room?.wall_hex || '#ddd')} ${esc(state.room?.descriptors?.join(' · ') || 'Room not calibrated')}</p>
    <div>${palette(state.room?.palette)}</div>${state.room?.accent_palette?.length ? `<small>Room accents</small><div>${palette(state.room.accent_palette)}</div>` : ""}<small>Art Mode: ${esc(state.artmode || 'unknown')}<br>Artwork changed: ${fmt(state.last_artwork_change)}<br>Matte changed: ${fmt(state.last_matte_change)}<br>TV communication: ${fmt(state.last_communication)}</small></div></div></div>
    ${state.recommendations?.length ? `<h2>Other ways to frame it</h2><div class="grid">${state.recommendations.slice(0,3).map(r => `<div class="card">${preview(r.matte,true)}<h3>${esc(r.matte.name)}</h3><p>${r.score} / 100</p></div>`).join('')}</div><details><summary>Inspect all candidate scores</summary>${scores()}</details>` : ''}`;
}
function scores() { return `<div class="scroll"><table><thead><tr><th>Matte</th><th>Score</th><th>Accent adjustment</th>${Object.keys(state.settings.weights).map(k=>`<th>${k}</th>`).join('')}</tr></thead><tbody>${state.recommendations.map(r=>`<tr><td>${esc(r.matte.name)}</td><td>${r.score}</td><td>${r.accent_adjustment ?? 0}</td>${Object.keys(state.settings.weights).map(k=>`<td>${r.components[k]}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`; }
function roomCards() {
 return `<div class="grid">${['day','night'].map(p=>{const r=state.rooms[p]; return `<div class="card"><span class="step">${p} room</span><h2>${r ? r.descriptors.join(' · ') : 'Just take a photo'}</h2>
  <p>Stand near your usual viewing position. Include the whole TV and some surrounding wall. The TV can keep playing normally.</p>
  <form data-form="snapshot" data-profile="${p}"><label>Take or choose a room photo<input type="file" name="file" accept="image/jpeg,image/png,image/webp" required></label><button>${r ? 'Update' : 'Use'} ${p} room photo</button><p><small>We find the TV and sample the wall automatically. No painting or tracing required.</small></p></form>
  ${r ? `<p>${swatch(r.wall_hex)} ${Math.round(r.confidence*100)}% confidence · ${r.source === 'snapshot' ? 'As photographed' : r.source === 'guided' ? 'Reference corrected' : 'Manual estimate'}</p><div><small>Wall tones</small><br>${palette(r.palette)}</div>${r.accent_palette?.length ? `<div><small>Room accents · subtle influence</small><br>${palette(r.accent_palette)}</div>` : ""}<small>${r.source === 'snapshot' ? 'An appearance estimate from this photo. Phone exposure and white balance affect the result.' : r.source === 'guided' ? 'Reference-corrected estimate; not laboratory colorimetry.' : 'Manual color estimate.'}</small>` : ''}
  ${r?.photo ? `<img class="thumb room-photo" src="/media/room/${r.photo}?v=${Date.now()}" alt="${p} room photograph"><details><summary>Review automatic wall selection</summary><p>The yellow outline marks the detected TV. Green areas are sampled; the screen and nearby objects are excluded.</p>${r.detection ? `<img class="room-photo" src="/media/room/${r.detection}?v=${Date.now()}" alt="Automatic TV and wall detection">` : ''}<p>${button('Optional: correct wall selection',`mask-${p}`,'class="secondary"')}</p></details>` : ''}
  <details><summary>Other ways to calibrate</summary><form data-form="quick" data-profile="${p}"><h3>Manual wall color</h3><div class="row"><input type="color" name="picker" value="${r?.wall_hex || '#d8d0bd'}" aria-label="Wall color picker"><input name="color" value="${r?.wall_hex || '#d8d0bd'}" pattern="#[0-9a-fA-F]{6}" aria-label="Wall HEX color"><button>Save color</button></div></form>
  <form data-form="photo" data-profile="${p}"><h3>Reference-image photograph</h3><p>Optional higher-accuracy mode: display our calibration image first, then photograph the whole TV and wall under your normal lighting.</p><input type="file" name="file" accept="image/jpeg,image/png,image/webp" required><p><button>Analyze reference photo</button></p></form></details>
 </div>`;}).join('')}</div>`;
}
function calibrationControls() {
 return `<details class="card" ${state.calibration ? "open" : ""}><summary>Optional: improve accuracy with a reference image</summary><h2>Guided reference calibration</h2><p>For higher confidence: use our original 4K sRGB reference image to reduce camera and lighting errors. The TV must already be displaying Art Mode. Automation pauses for the entire calibration session.</p><div class="row">${state.calibration ? button('Finish & restore original artwork','calibration-finish') : button('Display calibration image','calibration-start')}<a class="button secondary" href="/calibration-pattern.png" download>Download reference pattern</a></div>${state.calibration ? `<p>Calibration session: ${esc(state.calibration.phase)}. Matte used: ${esc(state.calibration.matte || 'pending')}.</p>` : ''}<p><small>This estimates appearance, not laboratory colorimetry. TV brightness, HDR, exposure, glare and phone processing remain sources of uncertainty.</small></p>
 ${Object.entries(state.owned).filter(([id,v])=>!v.deleted).map(([id])=>`<p>${button('Remove application calibration image','remove-owned',`data-id="${esc(id)}" class="secondary"`)}</p>`).join('')}</details>`;
}
function schedule() {
 const s=state.settings;
 return `<div class="card"><h2>Day & night</h2><div class="row">${button('Use Day Profile','profile-day','class="secondary"')}${button('Use Night Profile','profile-night','class="secondary"')}${button('Auto','profile-auto','class="secondary"')}</div><form data-form="schedule"><div class="grid"><label>Switching method<select name="schedule">${opts(['fixed','sun'],s.schedule)}</select></label><label>Timezone<input name="timezone" value="${esc(s.timezone)}" required></label><label>Day begins<input type="time" name="day_start" value="${esc(s.day_start)}" required></label><label>Night begins<input type="time" name="night_start" value="${esc(s.night_start)}" required></label><label>Approximate latitude (optional)<input type="number" step="any" min="-90" max="90" name="latitude" value="${s.latitude ?? ''}"></label><label>Approximate longitude (optional)<input type="number" step="any" min="-180" max="180" name="longitude" value="${s.longitude ?? ''}"></label></div><button>Save schedule</button><p><small>Sunrise/sunset is calculated locally. Location is never collected automatically. Missing night calibration stays visibly unconfigured.</small></p></form></div>`;
}
function setup() {
 return `<div class="steps"><span>1 Find your Frame</span><span>2 Pair</span><span>3 Capabilities</span><span>4 Snap your room</span></div><div class="card"><span class="step">1 / Find your Frame</span><h2>Welcome home.</h2><p>Discover your Samsung TV, or enter its LAN address. Bridge-mode containers usually need a manual address.</p><form data-form="discover"><div class="row"><input name="subnet" placeholder="Optional private subnet, e.g. 192.168.1.0/24" size="44"><button>Find Samsung TVs</button></div></form><div id="discoveries"></div><form data-form="connect"><label>TV IP address<input name="ip" placeholder="192.168.1.50" ${state.mock ? '' : 'required'}></label><button>Connect to this Frame</button></form><p><strong>2 / Pair:</strong> Samsung may display an authorization popup. Press Allow on your TV. The pairing token is stored locally and never shown here.</p></div>
 <div class="card"><span class="step">3 / Capability test</span><h2>${esc(state.device?.model || 'Waiting for connection')}</h2><p>Art Mode: ${esc(state.artmode || 'unknown')} · ${state.mattes.length} advertised matte combinations · Current artwork: ${esc(state.current?.content_id || 'unknown')}</p><p>Thumbnail: ${state.capabilities.thumbnail === undefined ? 'Not tested' : state.capabilities.thumbnail ? 'Available' : 'Unavailable'} · Art Store: ${state.capabilities.sam_thumbnail === undefined ? 'Not tested' : state.capabilities.sam_thumbnail ? 'Available' : 'Unavailable'}</p><p>Matte write and physical redraw are verified separately. A command acknowledgement alone is not a successful display test.</p>${button('Refresh capabilities','capabilities','class="secondary"')} <a href="/diagnostics">View diagnostics</a></div>
 <span class="step">4 / Snap your room</span>${roomCards()}${calibrationControls()}${schedule()}<div class="card"><p>Nighttime photography can wait until your normal evening lighting is available.</p>${button('Finish setup · add nighttime calibration later','finish-setup')}</div>`;
}
function artworks() {
 return `<div class="grid">${Object.values(state.artworks).map(a=>{const o=state.overrides[a.content_id] || {mode:'automatic'}; return `<div class="card">${a.image ? `<img class="thumb" src="/media/artwork/${esc(a.image)}" alt="Artwork">` : '<p>Image unavailable</p>'}<h3>${esc(a.content_id)}</h3><p>${palette(a.analysis?.palette)}</p><small>Seen ${fmt(a.last_seen)}<br>Last matte: ${esc(a.current_matte)}<br>Recommendation: ${esc(a.recommendation?.matte?.name || "Awaiting analysis")} ${a.recommendation ? " · "+a.recommendation.score+"/100" : ""}</small><form data-form="override" data-id="${esc(a.content_id)}"><label>Behavior<select name="mode">${opts(['automatic','force','never'],o.mode)}</select></label><label>Forced matte<select name="matte">${matteOptions(o.matte)}</select></label><button>Save override</button></form><details><summary>Provide your own local image</summary><form data-form="local-image" data-id="${esc(a.content_id)}"><input type="file" name="file" accept="image/jpeg,image/png,image/webp" required><p><button>Save local reference</button></p></form></details></div>`;}).join('') || '<div class="card">Known artwork appears here after Art Mode is displayed.</div>'}</div>`;
}
function mattes() {
 return `<p>Matte families and colors come from your TV. Some combinations depend on artwork dimensions. TV-reported and nominal colors are approximations; you can adjust a swatch below.</p><div class="grid">${state.mattes.map(m=>`<form class="card" data-form="matte" data-id="${esc(m.id)}"><h3>${swatch(m.hex)} ${esc(m.name)}</h3><small>${esc(m.source)} · ${esc(m.family)}</small><label class="inline"><input type="checkbox" name="enabled" ${m.enabled ? 'checked' : ''}>Enabled</label><label>Preference<select name="preference">${opts(['normal','preferred','avoid'],m.preference)}</select></label><details><summary>Adjust nominal color</summary><label>Appearance<input type="color" name="hex" value="${esc(m.hex)}" data-original="${esc(m.hex)}"></label></details><button class="secondary">Save</button></form>`).join('')}</div>`;
}
function strategy() {
 const s=state.settings;
 return `<div class="card"><h2>A balance that feels right</h2><p>Adaptive balances artwork, wall and room. Subtle keeps the artwork dominant. Contrast separates wall, matte and art without maximizing color difference. Gallery favors conventional neutrals.</p><form data-form="strategy"><div class="grid"><label>Strategy<select name="strategy">${opts(['Adaptive','Subtle','Contrast','Gallery'],s.strategy)}</select></label><label>Neutral preference (0–3)<input name="neutral_preference" type="number" min="0" max="3" step="0.1" value="${s.neutral_preference}"></label><label>Room accent influence (0 = ignore, 10 = stronger)<input name="accent_influence" type="number" min="0" max="10" step="1" value="${s.accent_influence}"></label><label>Minimum score improvement<input type="number" min="0" max="100" name="threshold" value="${s.threshold}"></label><label>Seconds between automatic changes<input type="number" min="0" max="86400" name="cooldown" value="${s.cooldown}"></label><label>Preferred family<input name="preferred_family" value="${esc(s.preferred_family)}" placeholder="Optional, e.g. modern"></label></div><details><summary>Adaptive scoring weights</summary><div class="grid">${Object.entries(s.weights).map(([k,v])=>`<label>${esc(k)}<input type="number" min="0" max="100" name="weight_${k}" value="${v}"></label>`).join('')}</div></details><button>Save strategy</button> ${button('Reset scoring defaults','reset','type="button" class="secondary"')}</form></div>`;
}
function history() { return `<div class="card scroll"><table><thead><tr><th>When</th><th>Artwork / room</th><th>Change</th><th>Score / mode</th><th>Reason</th></tr></thead><tbody>${state.history.map(h=>`<tr><td>${fmt(h.timestamp)}</td><td>${esc(h.artwork)}<br>${esc(h.profile)}</td><td>${esc(h.previous)} → ${esc(h.new)}<br>${esc(h.status)}</td><td>${h.score ?? '—'}<br>${esc(h.mode)}</td><td>${esc(h.reason)}</td></tr>`).join('')}</tbody></table></div>`; }
function diagnostics() { return `<div class="card"><h2>Local connection</h2><p>${esc(state.error || 'No recorded error')}</p><p>Version ${esc(state.version)} · Art Mode ${esc(state.artmode || 'unknown')} · Last communication ${fmt(state.last_communication)}</p><pre>${esc(JSON.stringify({device:state.device, capabilities:state.capabilities},null,2))}</pre><p>Event names listed above have actually been observed during this session. Polling remains active as a fallback. No cloud ambient sensor is used.</p>${button('Refresh capabilities','capabilities')}<details><summary>Advertised matte IDs</summary><pre>${esc(state.mattes.map(m=>m.id).join('\n'))}</pre></details><p>Use <code>python scripts/frame_probe.py --help</code> for the state-preserving physical test.</p></div>`; }
function settings() { const s=state.settings; return `<div class="card"><h2>Setup & calibration</h2><p>You can change TVs or recalibrate without deleting the database.</p><a class="button" href="/setup">Run setup wizard</a></div><div class="card"><h2>When an image is unavailable</h2><form data-form="fallback"><label>Behavior<select name="fallback">${opts(['retain','safe'],s.fallback)}</select></label><label>Safe default matte<select name="safe_matte">${matteOptions(s.safe_matte)}</select></label><label class="inline"><input type="checkbox" name="requires_reselect" ${s.requires_reselect ? 'checked' : ''}>Re-select current artwork after matte changes</label><p><small>Enable only after physical testing confirms your model needs it. Art Mode must be on; this never wakes the TV.</small></p><button>Save behavior</button></form></div>${schedule()}<div class="card"><h2>Privacy & security</h2><p>Room photos, pairing tokens and analysis remain in your persistent data directory. No telemetry, cloud AI or Samsung account credentials. Do not expose this UI directly to the public internet.</p></div>`; }
function renderPage() {
 const renderers = {dashboard, setup, room:()=>roomCards()+calibrationControls()+schedule(), artwork:artworks, mattes, strategy, history, diagnostics, settings};
 $('#content').innerHTML = (renderers[page] || dashboard)();
}
document.addEventListener('click', async event => {
 const b=event.target.closest('[data-action]'); if(!b || busy) return;
 const a=b.dataset.action; busy=true; b.disabled=true;
 try {
  if(a.startsWith('preview-')) {previewProfile=a.slice(8); renderPage();}
  else if(a.startsWith('mask-')) {await openMask(a.slice(5));}
  else if(a.startsWith('profile-')) {await api('/api/settings',{profile_mode:a.slice(8)}); await refresh();}
  else if(a==='finish-setup') {await api('/api/settings',{setup_complete:true}); location.href='/';}
  else if(a==='remove-owned') {await api('/api/calibration/remove',{content_id:b.dataset.id}); await refresh();}
  else if(a.startsWith('calibration-')) {message('Working with the Frame…'); await api('/api/calibration/'+a.slice(12)); await refresh(); message('Calibration session updated.');}
  else if(a==='capabilities') {await api('/api/capabilities'); await refresh();}
  else if(a==='mock-next') {await api('/api/mock/next'); await api('/api/action/evaluate'); await refresh();}
  else {const r=await api('/api/action/'+a); await refresh(); message(r.message || 'Updated.');}
 } catch(e) {message(e.message);} finally {busy=false; b.disabled=false;}
});
document.addEventListener('change', e=>{
 if(e.target.name==='picker') e.target.form.elements.color.value=e.target.value;
 if(e.target.name==='color' && /^#[a-f0-9]{6}$/i.test(e.target.value)) e.target.form.elements.picker.value=e.target.value;
});
document.addEventListener('submit', async e=>{
 const f=e.target; if(!f.dataset.form) return; e.preventDefault(); if(busy) return;
 busy=true; const submit=f.querySelector('button'); submit.disabled=true;
 const data=Object.fromEntries(new FormData(f));
 try {
  switch(f.dataset.form) {
   case 'discover': {message('Searching Samsung services…'); const found=await api('/api/discover',data); $('#discoveries').innerHTML=found.map(d=>`<p><strong>${esc(d.name)} · ${esc(d.model)}</strong> · ${esc(d.ip || 'Demo')} · Art Mode ${d.art_supported ? 'supported' : 'unknown'}</p>`).join('') || '<p>No SSDP responses. Enter your TV address, or try your private /24 subnet above.</p>'; if(found[0]?.ip) $('[data-form="connect"] input').value=found[0].ip; break;}
   case 'connect': message('Look at the TV: press Allow if Samsung displays an authorization popup.'); await api('/api/connect',data); await refresh(); message('Paired. Capability profile saved.'); break;
   case 'quick': await api(`/api/room/${f.dataset.profile}/quick`,{color:data.color}); await refresh(); break;
   case 'snapshot': {const file=f.elements.file.files[0]; message('Finding the TV and measuring the surrounding wall…'); try {await api(`/api/room/${f.dataset.profile}/snapshot`,new FormData(f)); await refresh(); message('Room profile saved. Wall sampling was automatic.');} catch(error) {if(/corners|locate|ambiguous/i.test(error.message)) await openCorners(file,f.dataset.profile); else throw error;} break;}
   case 'photo': message('Detecting reference markers and measuring the room…'); await api(`/api/room/${f.dataset.profile}/photo`,new FormData(f)); await refresh(); message('Profile saved. Review the wall mask to exclude furniture, windows and adjacent walls.'); break;
   case 'schedule': for(const k of ['latitude','longitude']) {if(data[k]==='') delete data[k]; else data[k]=Number(data[k]);} await api('/api/settings',data); await refresh(); break;
   case 'override': await api('/api/override',{...data,content_id:f.dataset.id}); await refresh(); break;
   case 'local-image': await api(`/api/artwork/${encodeURIComponent(f.dataset.id)}/image`,new FormData(f)); message('Local reference stored. Re-evaluate to analyze it.'); break;
   case 'matte': data.enabled=f.elements.enabled.checked; if(data.hex===f.elements.hex.dataset.original) delete data.hex; await api('/api/matte',{...data,id:f.dataset.id}); await refresh(); break;
   case 'strategy': {const weights={}; for(const k of Object.keys(data)) if(k.startsWith('weight_')) {weights[k.slice(7)]=Number(data[k]); delete data[k];} for(const k of ['threshold','cooldown','neutral_preference','accent_influence']) data[k]=Number(data[k]); await api('/api/settings',{...data,weights}); await refresh(); break;}
   case 'fallback': await api('/api/settings',{...data,requires_reselect:f.elements.requires_reselect.checked}); await refresh(); break;
  }
 } catch(err) {message(err.message);} finally {busy=false; submit.disabled=false;}
});
async function openMask(profile) {
 const room=state.rooms[profile];
 $('#content').innerHTML=`<div class="card"><h2>${profile} wall mask</h2><p>Green areas are sampled. Unshaded areas are excluded. The screen outline is always excluded. Paint only the wall you want measured.</p><div class="row"><label>Brush size<input id="brush" type="range" min="5" max="120" value="35"></label><label>Tool<select id="tool"><option value="add">Add wall</option><option value="erase">Erase / exclude</option></select></label><button id="save-mask">Save wall mask</button><button id="reset-mask" class="secondary">Reset automatic selection</button><a href="/room">Back to Room</a></div><div class="mask-wrap"><canvas id="mask-view"></canvas></div></div>`;
 const image=new Image(), maskImage=new Image();
 await Promise.all([new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src='/media/room/'+room.photo;}),new Promise((resolve,reject)=>{maskImage.onload=resolve;maskImage.onerror=reject;maskImage.src='/media/room/'+room.mask+'?t='+Date.now();})]);
 const canvas=$('#mask-view'), ctx=canvas.getContext('2d'), mask=document.createElement('canvas');
 canvas.width=mask.width=image.width; canvas.height=mask.height=image.height;
 const m=mask.getContext('2d'); m.drawImage(maskImage,0,0); let drawing=false;
 function render() {ctx.drawImage(image,0,0);const pixels=m.getImageData(0,0,mask.width,mask.height);for(let i=0;i<pixels.data.length;i+=4){const included=pixels.data[i]>127;pixels.data[i]=50;pixels.data[i+1]=210;pixels.data[i+2]=100;pixels.data[i+3]=included ? 90:0;} const overlay=document.createElement('canvas');overlay.width=mask.width;overlay.height=mask.height;overlay.getContext('2d').putImageData(pixels,0,0);ctx.drawImage(overlay,0,0);ctx.strokeStyle='#ffdb67';ctx.lineWidth=5;ctx.beginPath();room.corners.forEach((p,i)=>i?ctx.lineTo(...p):ctx.moveTo(...p));ctx.closePath();ctx.stroke();}
 function paint(e){const rect=canvas.getBoundingClientRect();m.fillStyle=$('#tool').value==='add'?'white':'black';m.beginPath();m.arc((e.clientX-rect.left)*canvas.width/rect.width,(e.clientY-rect.top)*canvas.height/rect.height,Number($('#brush').value),0,Math.PI*2);m.fill();render();}
 canvas.onpointerdown=e=>{drawing=true;canvas.setPointerCapture(e.pointerId);paint(e);};canvas.onpointermove=e=>{if(drawing)paint(e);};canvas.onpointerup=()=>{drawing=false;};canvas.onpointercancel=()=>{drawing=false;};render();
 $('#save-mask').onclick=async()=>{try{const blob=await new Promise(r=>mask.toBlob(r,'image/png'));const form=new FormData();form.append('file',blob,'mask.png');await api(`/api/room/${profile}/mask`,form);message('Wall mask and measured profile saved.');await refresh(false);}catch(e){message(e.message);}};
 $('#reset-mask').onclick=async()=>{try{await api(`/api/room/${profile}/reset-mask`);await refresh(false);await openMask(profile);}catch(e){message(e.message);}};
}
refresh().catch(e=>message(e.message));
setInterval(()=>{if(!busy && page==='dashboard' && !document.activeElement?.matches('input,select'))refresh().catch(()=>{});},10000);
async function openCorners(file,profile) {
 const objectURL=URL.createObjectURL(file), image=new Image();
 await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=objectURL;});
 URL.revokeObjectURL(objectURL);
 $('#content').innerHTML=`<div class="card"><h2>Help locate the TV</h2><p>We could not confidently find the frame. Tap just four corners: <strong id="corner-step">top left</strong>, then top right, bottom right, bottom left. We will sample the wall automatically.</p><div class="mask-wrap"><canvas id="corner-view"></canvas></div><p class="row"><button id="corner-reset" class="secondary">Start over</button><button id="corner-save" disabled>Use these corners</button></p></div>`;
 const canvas=$('#corner-view'),ctx=canvas.getContext('2d');const scale=Math.min(1,1600/Math.max(image.width,image.height));canvas.width=Math.round(image.width*scale);canvas.height=Math.round(image.height*scale);let points=[];
 function draw(){ctx.drawImage(image,0,0,canvas.width,canvas.height);ctx.strokeStyle='#ffdc70';ctx.fillStyle='#ffdc70';ctx.lineWidth=4;ctx.beginPath();points.forEach((p,i)=>{const x=p[0]*canvas.width,y=p[1]*canvas.height;i?ctx.lineTo(x,y):ctx.moveTo(x,y);});if(points.length===4)ctx.closePath();ctx.stroke();points.forEach(p=>{ctx.beginPath();ctx.arc(p[0]*canvas.width,p[1]*canvas.height,9,0,Math.PI*2);ctx.fill();});$('#corner-step').textContent=['top left','top right','bottom right','bottom left','done'][points.length];$('#corner-save').disabled=points.length!==4;}
 canvas.onpointerdown=e=>{if(points.length===4)return;const box=canvas.getBoundingClientRect();points.push([(e.clientX-box.left)/box.width,(e.clientY-box.top)/box.height]);draw();};
 $('#corner-reset').onclick=()=>{points=[];draw();};
 $('#corner-save').onclick=async()=>{try{const form=new FormData();form.append('file',file);form.append('corners',JSON.stringify(points));await api(`/api/room/${profile}/snapshot`,form);await refresh();message('Room profile saved. Wall sampling was automatic.');}catch(e){message(e.message);}};
 draw();message('Optional four-tap correction: no wall painting needed.');
}
