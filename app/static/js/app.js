const $=id=>document.getElementById(id);
const drop=$('dropzone'), file=$('file'), start=$('startBtn');
if(drop && file && start){
  drop.addEventListener('click',()=>file.click());
  ['dragenter','dragover'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.add('drag')}));
  ['dragleave','drop'].forEach(e=>drop.addEventListener(e,x=>{x.preventDefault();drop.classList.remove('drag')}));
  drop.addEventListener('drop',e=>{if(e.dataTransfer.files.length){file.files=e.dataTransfer.files;showFile()}});
  file.addEventListener('change',showFile);
}
function showFile(){if(file && file.files[0]){$('fileName').textContent=`${file.files[0].name} · ${(file.files[0].size/1024/1024).toFixed(2)} MB`;start.disabled=false}}

async function loadTemplates(){
  try{let r=await fetch('/api/templates');let data=await r.json();$('template').innerHTML='<option value="">Auto-detect</option>'+data.map(t=>`<option>${t.name}</option>`).join('')}catch(e){}
}

function reportPanel(id, engine, llmMode, confidence){
  const aiLabel = llmMode==='SMART_ANALYZER' ? 'Smart Analyzer (offline AI)' : (llmMode||'CSI LLM');
  return `<div class="report-panel mt-3">
    <h5>✓ Transformation complete</h5>
    <div class="desc">Engine: <b>${engine||'—'}</b> &middot; AI: <b>${aiLabel}</b> &middot; Confidence: <b>${Math.round((confidence||0)*100)}%</b></div>
    <div class="report-grid">
      <a href="/api/jobs/${id}/download/output"><span class="t">⬇ Cleaned dataset</span><span class="d">Target-structure output</span></a>
      <a href="/api/jobs/${id}/download/errors"><span class="t">⬇ Issue log</span><span class="d">Every excluded/flagged row</span></a>
      <a href="/api/jobs/${id}/download/reconciliation"><span class="t">⬇ Reconciliation</span><span class="d">Input vs output counts</span></a>
      <a href="/api/jobs/${id}/download/method_note"><span class="t">⬇ Method note</span><span class="d">AI use &amp; assumptions</span></a>
      <a class="pbi" href="/api/jobs/${id}/download/powerbi"><span class="t">📊 Power BI workbook</span><span class="d">Load-ready .xlsx</span></a>
      <a class="pbi" href="/api/jobs/${id}/dashboard" target="_blank"><span class="t">📈 Live dashboard</span><span class="d">Open interactive report</span></a>
    </div>
  </div>`;
}

if($('uploadForm')) $('uploadForm').addEventListener('submit',async e=>{
  e.preventDefault();if(!file.files[0])return;start.disabled=true;$('progressBox').classList.remove('d-none');$('result').innerHTML='';
  let fd=new FormData();fd.append('file',file.files[0]);fd.append('required_columns',$('requiredColumns').value);fd.append('template_name',$('template').value);
  try{
    let r=await fetch('/api/upload',{method:'POST',body:fd});let d=await r.json();
    if(!r.ok)throw new Error(d.detail||'Upload failed');
    poll(d.job_id);
  }catch(err){$('result').innerHTML=`<div class="alert alert-danger">${escapeHtml(err.message)}</div>`;start.disabled=false}
});

async function poll(id){
  try{
    let r=await fetch('/api/jobs/'+id);let j=await r.json();
    $('progress').textContent=(j.progress||0)+'%';$('bar').style.width=(j.progress||0)+'%';$('stage').textContent=j.stage||'Processing';
    if(j.status==='COMPLETED'){
      $('result').innerHTML=reportPanel(id, j.engine, j.llm_mode, j.confidence);
      start.disabled=false;loadJobs();typeof loadKpis==='function'&&loadKpis();return;
    }
    if(j.status==='FAILED'){
      $('result').innerHTML=`<div class="alert alert-danger"><b>Job failed.</b> ${escapeHtml(j.error_message||'Unknown error')}</div>`;
      start.disabled=false;loadJobs();return;
    }
    setTimeout(()=>poll(id),1200);
  }catch(e){$('result').innerHTML='<div class="alert alert-danger">Unable to read job status.</div>';start.disabled=false}
}

async function loadJobs(){
  try{
    let r=await fetch('/api/jobs');let data=await r.json();
    $('jobsBody').innerHTML=data.map(j=>`<tr>
      <td>#${j.id}</td><td>${escapeHtml(j.filename)}</td>
      <td><span class="small-pill">${j.engine||'—'}</span></td>
      <td><span class="small-pill status-${j.status}">${j.status}</span></td>
      <td>${j.row_count??'—'}</td><td>${j.output_rows??'—'}</td><td>${j.issue_count??'—'}</td>
      <td>${j.status==='COMPLETED'?`<div class="d-flex flex-wrap gap-1">
          <a class="btn btn-sm btn-outline-primary" href="/api/jobs/${j.id}/download/output">Output</a>
          <a class="btn btn-sm btn-powerbi" href="/api/jobs/${j.id}/download/powerbi">Power BI</a>
          <a class="btn btn-sm btn-outline-secondary" href="/api/jobs/${j.id}/dashboard" target="_blank">Dashboard</a>
        </div>`:''}</td>
    </tr>`).join('') || '<tr><td colspan="8" class="text-secondary">No jobs yet.</td></tr>';
  }catch(e){}
}

function escapeHtml(s){return String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]))}
if($('template')) loadTemplates();
if($('jobsBody')) loadJobs();
