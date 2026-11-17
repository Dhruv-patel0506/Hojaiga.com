

/* ============================== helpers ============================== */
const $=id=>document.getElementById(id);
const clamp=(v,a,b)=>Math.min(b,Math.max(a,v));
const sum=a=>a.reduce((x,y)=>x+y,0);
const mean=a=>a.length?sum(a)/a.length:NaN;
const prod=a=>a.reduce((x,y)=>x*y,1);
const uniq=a=>[...new Set(a)];
const sd=(a,ddof=1)=>{const m=mean(a);return Math.sqrt(sum(a.map(x=>(x-m)**2))/(a.length-ddof))};
const fmt=(x,d=3)=>{if(x===null||x===undefined||!isFinite(x))return String(x);const p=10**d;let v=Math.round(x*p)/p;return Object.is(v,-0)?'0':String(v)};
const pct=(x,d=1)=>fmt(x*100,d)+'%';
const esc=s=>String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const log2=x=>Math.log(x)/Math.LN2;
function entropy(counts){const n=sum(counts);return -sum(counts.filter(c=>c>0).map(c=>{const p=c/n;return p*log2(p)}))}
function gini(counts){const n=sum(counts);return 1-sum(counts.map(c=>{const p=c/n;return p*p}))}
const F=(k,v,cls='')=>`<div class="fact ${cls}"><span>${k}</span><b>${v}</b></div>`;

function chips(host,items,current,onclick,cls=''){
  const el=$(host); if(!el)return;
  el.innerHTML=items.map(([id,label,sub])=>
    `<button class="chip ${cls}" data-v="${id}" aria-pressed="${String(id===current)}">${label}${sub?`<small>${sub}</small>`:''}</button>`).join('');
  el.onclick=e=>{const b=e.target.closest('.chip'); if(!b)return; onclick(b.dataset.v)};
}
function press(host,val){
  const el=$(host); if(!el)return;
  [...el.querySelectorAll('.chip')].forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.v===String(val))));
}
const nums=s=>String(s).replace(/[^0-9.,eE+-]/g,' ').split(/[,\s]+/).filter(x=>x!=='').map(Number).filter(isFinite);
function parseMat(s){ // "2,2;4,1" -> [[2,2],[4,1]]
  const rows=String(s).split(/[;\n]/).map(r=>nums(r)).filter(r=>r.length);
  if(!rows.length)return null;
  const n=rows[0].length; if(rows.some(r=>r.length!==n))return null;
  return rows;
}
function matHTML(m,cls=''){
  if(!m)return '<span class="hint">not a rectangle</span>';
  return `<div class="tbl">${m.map(r=>`<div class="trow">${r.map(v=>`<div class="tc ${cls}">${fmt(v,4)}</div>`).join('')}</div>`).join('')}</div>`;
}
const T=(m)=>m[0].map((_,c)=>m.map(r=>r[c]));
function matMul(A,B){const n=A.length,m=B[0].length,k=A[0].length;
  return Array.from({length:n},(_,i)=>Array.from({length:m},(_,j)=>sum(Array.from({length:k},(_,t)=>A[i][t]*B[t][j]))));}
function det(M){const n=M.length; if(n===1)return M[0][0]; if(n!==M.length||M.some(r=>r.length!==n))return NaN;
  return M.reduce((d,_,j)=>d+((j%2?-1:1)*M[0][j]*det(M.map((r,i)=>i===0?null:r).filter(Boolean).map(r=>[...r.slice(0,j),...r.slice(j+1)]))),0);}
function inv2(M){const d=det(M); if(!isFinite(d)||d===0)return null;
  return [[M[1][1]/d,-M[0][1]/d],[-M[1][0]/d,M[0][0]/d]];}

/* svg plot helpers ---------------------------------------------------- */
function plotSVG(w,h,box,inner,items=[]){ // box = {x0,x1,y0,y1}
  const P=(x,y)=>[w*( (x-box.x0)/(box.x1-box.x0) ), h*(1-(y-box.y0)/(box.y1-box.y0))];
  return `<svg viewBox="0 0 ${w} ${h}" role="img">${inner}</svg>`;
}
function axes(w,h,b,step=1){
  const X=v=>w*((v-b.x0)/(b.x1-b.x0)), Y=h*(1-(v-b.y0)/(b.y1-b.y0));
  let s='';
  for(let v=Math.ceil(b.y0);v<=b.y1;v+=step) s+=`<line x1="0" y1="${Y(v)}" x2="${w}" y2="${Y(v)}" class="axline" opacity=".5"/>`;
  for(let v=Math.ceil(b.x0);v<=b.x1;v+=step) s+=`<line x1="${X(v)}" y1="0" x2="${X(v)}" y2="${h}" class="axline" opacity=".5"/>`;
  return s;
}
const axX=w=>v=>w*((v)/w);
function scaleFn(b,w){return v=>w*((v-b[0])/(b[1]-b[0]))}
function curvePath(pts,W,H,b){ // pts = [[x,y],...]
  const sx=scaleFn(b.x,W), sy=v=>H*(1-(v-b.y0)/(b.y1-b.y0));
  return pts.map(([x,y],i)=>`${i?'L':'M'}${sx(x).toFixed(1)} ${sy(y).toFixed(1)}`).join(' ');
}
function say(id,msg){const el=$(id); if(el)el.innerHTML=msg}

/* theme + copy -------------------------------------------------------- */
(()=>{const b=$('themeBtn'); let t=localStorage.getItem('ml-theme')||'';
  if(t)document.documentElement.setAttribute('data-theme',t);
  b.onclick=()=>{const cur=document.documentElement.getAttribute('data-theme')||
    (matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light');
    const next=cur==='dark'?'light':'dark'; document.documentElement.setAttribute('data-theme',next);
    localStorage.setItem('ml-theme',next)};
})();
document.querySelectorAll('.copyB').forEach(b=>b.onclick=()=>{
  const pre=b.closest('.codebox').querySelector('pre');
  navigator.clipboard.writeText(pre.innerText).then(()=>{b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1200)})
    .catch(()=>{b.textContent='ctrl+c';});
});

/* ============================== 01 · PYTHON ============================== */
(()=>{
  const host='pyPresets';
  chips(host,[['10 + 5 * 2','10 + 5 * 2','multiply first'],['(10 + 5) * 2','(10+5) * 2','brackets win'],
    ['10 % 3','10 % 3','remainder'],['10 // 3','10 // 3','floor divide'],['2 ** 10','2 ** 10','power'],
    ['10 / 4','10 / 4','true divide -> float']], '10 + 5 * 2', v=>{$('pyExpr').value=v;run()});
  $('pyExpr').oninput=run;
  function run(){
    const raw=$('pyExpr').value;
    let v=null,err='';
    try{ if(!/^[-+*/%(). 0-9]+$/.test(raw)) throw 0; v=Function('"use strict";return('+raw.replace(/%/g,'%').replace(/\/\/(\d)/g,'/$1')+')')(); }
    catch(e){ err='only digits and + - * / % ( ) are allowed here'; }
    $('pyEval').innerHTML = err? F('careful',err,'bad') :
      F('result',fmt(v,4),'hot')+F('type',Number.isInteger(v)?'int':'float')+
      F('Python precedence','** then * / % then + -');
  }
  const rs=$('rStart'),rp=$('rStop'),rk=$('rStep');
  function rng(){
    const a=+rs.value,b=+rp.value,s=+rk.value;
    const out=[]; if(s!==0){ for(let i=a;s>0?i<b:i>b;i+=s){ out.push(i); if(out.length>40)break } }
    $('rOut').innerHTML=`<div class="trow">${out.length?out.map(v=>`<div class="tc ${v===a?'on':''}">${v}</div>`).join(''):'<div class="tc off">empty</div>'}</div>`;
    $('rHint').innerHTML=`<code>range(${a}, ${b}${s!==1?', '+s:''})</code> → ${out.length} values. ${out.length?`first <b>${out[0]}</b>, last <b>${out[out.length-1]}</b>, and <b>${b} is never printed</b>.`:'the stop is already passed — a loop that runs zero times.'}`;
  }
  [rs,rp,rk].forEach(i=>i.oninput=rng); rng();
  const sl=$('ageSl');
  function gate(){
    const a=+sl.value;
    const row=(k,val,expr)=>F(k,val?'True':'False',val?'good':'bad')+'<span class="hint" style="display:block">'+expr+'</span>';
    $('ageFacts').innerHTML=`<div style="display:contents">${
      F('age',a)+' '+F('age > 10',a>10?'True':'False',a>10?'good':'bad')+
      F('age < 30',a<30?'True':'False',a<30?'good':'bad')+
      F('age>10 and age<13',(a>10&&a<13)?'True':'False',(a>10&&a<13)?'good':'bad')+
      F('age>10 or age<30',(a>10||a<30)?'True':'False',(a>10||a<30)?'good':'bad')+
      F('not (age>10)',!(a>10)?'True':'False')}</div>`;
  }
  sl.oninput=gate; gate();
})();

/* ============================== 02 · NUMPY ============================== */
(()=>{
  let op='info';
  const OPS=[['info','ndim / shape / size'],['axis0','sum axis=0'],['axis1','sum axis=1'],['add','a + a'],
    ['mul','a * a'],['sqrt','np.sqrt'],['reshape','reshape'],['max','max / min / mean'],['std','std / mean'],['transpose','a.T'],['ravel','ravel']];
  chips('npOps',OPS,'info',v=>{op=v;run();press('npOps',v)});
  $('npSrc').oninput=run;
  function run(){
    const A=parseMat($('npSrc').value);
    if(!A){$('npStage').innerHTML='<span class="hint">use rows separated by ; and values by , e.g. [[1,2,3],[3,4,5]] → "1,2,3;3,4,5"</span>';return}
    const n=A.length,m=A[0].length,flat=A.flat();
    let stage='',facts='',why='';
    const show=(M,lab)=>`<div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">${lab}</span>${matHTML(M)}</div>`;
    if(op==='info'){
      stage=show(A,'a')+`<div class="arrow">→</div>${show(T(A),'a.T')}`;
      facts=F('a.ndim',n===1?1:2)+F('a.shape',`(${n}, ${m})`)+F('a.size',flat.length)+F('a.dtype','int64')+
            F('axis 0 = down the columns',n)+F('axis 1 = along the rows',m);
      why='Shape is (rows, columns) — the order everyone gets wrong. Size is rows×columns, and dtype is one type for the whole block.';
    } else if(op==='axis0'||op==='axis1'){
      const down=op==='axis0';
      const r=down? A[0].map((_,c)=>sum(A.map(row=>row[c]))) : A.map(sum);
      stage=show(A,'a')+`<div class="arrow">→</div><div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">${down?'axis=0 : '+n+' rows collapse into 1':'axis=1 : '+m+' columns collapse into 1'}</span><div class="tbl"><div class="trow">${r.map(v=>`<div class="tc on">${v}</div>`).join('')}</div></div></div>`;
      facts=r.map((v,i)=>F((down?'col ':'row ')+i,v)).join('');
      why=down?'axis=0 adds straight down: column 0 gives 1+3=4, column 1 gives 2+4=6, column 2 gives 3+5=8 — the instructor\'s [4 6 8].':'axis=1 adds along each row: 1+2+3=6 and 3+4+5=12 — his [ 6 12]. "rows are called axis one and columns are called axis 0".';
    } else if(op==='add'||op==='mul'){
      const r=A.map(r=>r.map(v=>op==='add'?v+v:v*v));
      stage=show(A,'a')+`<div class="arrow">${op==='add'?'+':'*'}</div>${show(r,'a '+op)} `;
      facts=F('element-wise',op==='add'?'doubled':'squared')+F('no loop needed','a + a')+' '+F('first cell',`${A[0][0]} → ${r[0][0]}`);
      why='NumPy applies the operator to every cell at once: 1+1=2, 2+2=4, 3+3=6 … which is why a1+a2 beats a Python for-loop.';
    } else if(op==='sqrt'){
      const r=A.map(r=>r.map(v=>Math.sqrt(v)));
      stage=show(A,'a')+`<div class="arrow">√</div>${show(r,'np.sqrt(a)')}`;
      facts=A.flat().slice(0,6).map((v,i)=>F('√'+v,fmt(Math.sqrt(v),3))).join('');
      why='His list read straight off the screen: 1, 1.414, 1.732, 2, 2.236.';
    } else if(op==='reshape'){
      const ok=flat.length%2===0?[[flat.length/2,2],[2,flat.length/2],[1,flat.length],[flat.length,1]].filter(([r,c])=>r*c===flat.length):[];
      stage=show(A,'a (2×'+m+')')+ok.map(([r,c])=>`<div class="arrow">↦</div>${show(Array.from({length:r},(_,i)=>flat.slice(i*c,i*c+c)),'reshape('+r+','+c+')')}`).join('');
      facts=F('cells stay put',flat.length)+F('order','row-major (C)')+F('same size required',flat.length);
      why='Reshape does not move a single value — it only changes how the flat line of cells is folded. 4×2 becomes 2×4 with the same 1,2,3,3,4,5 in the same order.';
    } else if(op==='max'){
      stage=show(A,'a');
      facts=F('np.max',Math.max(...flat))+F('np.min',Math.min(...flat))+F('np.sum',sum(flat))+F('np.mean',fmt(mean(flat),4))+F('np.median',fmt([...flat].sort((x,y)=>x-y)[Math.floor(flat.length/2)],4));
      why='All of these take an axis argument too: np.max(a, axis=1) is the biggest value in every row.';
    } else if(op==='std'){
      stage=show(A,'a');
      facts=F('mean μ',fmt(mean(flat),4))+F('std (ddof=0)',fmt(sd(flat,0),4))+F('var (ddof=0)',fmt(sd(flat,0)**2,4))+
        F('std (ddof=1)',fmt(sd(flat,1),4))+F('np.std(a)',fmt(sd(flat,0),4));
      why='NumPy defaults to the POPULATION formula (divide by N); pandas defaults to the SAMPLE one (divide by N−1). That ddof difference is a classic silent bug.';
    } else if(op==='transpose'){
      stage=show(A,'a')+`<div class="arrow">T</div>${show(T(A),'a.T / flip')}`;
      facts=F('before',`(${n}, ${m})`)+F('after',`(${m}, ${n})`)+F('first row becomes','first column');
      why='"You convert the rows into columns... it helps you flip the dimensions" — his reason for doing it before PCA, to turn a column vector into a row.';
    } else {
      stage=show(A,'a')+`<div class="arrow">→</div>${show([flat],'a.ravel()')}`;
      facts=F('ndim 2 → 1',flat.length+' cells')+F('shape',`(${flat.length},)`);
      why='Flattening is what you do before feeding an image to a model: a 2×7 grid becomes one row of 14 numbers.';
    }
    $('npStage').innerHTML=stage; $('npFacts').innerHTML=facts; say('npWhy',why);
  }
  run();
  /* speed demo */
  const n=1000;
  const mk=()=>Array.from({length:n},(_,i)=>i);
  function time(fn,times){const s=performance.now();for(let k=0;k<times;k++)fn();return (performance.now()-s)/times}
  const listAdd=()=>{let out=[];const L=mk();for(let i=0;i<n;i++)out.push(L[i]+L[i]);return out};
  const vecAdd=()=>{const L=new Float64Array(mk());const B=new Float64Array(mk());const o=new Float64Array(n);for(let i=0;i<n;i++)o[i]=L[i]+B[i];return o};
  function bars(){
    const tl=time(listAdd,40), tv=time(vecAdd,40);
    const mx=Math.max(tl,tv);
    $('npSpeed').innerHTML=
      `<div style="width:100%;display:flex;flex-direction:column;gap:8px">
       <div><span class="lbl">python list + for-loop</span><div style="height:22px;background:var(--bad);border-radius:6px;width:${(tl/mx*100).toFixed(1)}%;min-width:60px"></div></div>
       <div><span class="lbl">ndarray a1 + a2 (this page)</span><div style="height:22px;background:var(--c);border-radius:6px;width:${(tv/mx*100).toFixed(1)}%;min-width:60px"></div></div>
       <p class="hint">Measured live in your browser on ${n} numbers. In the video the same experiment on his machine read <b>208 ms for the list</b> versus <b>67 ms for the array</b> — and he also pointed out that <code>l1 + l2</code> does not even add them, it concatenates.</p></div>`;
  }
  bars();
})();

/* ============================== 03 · PANDAS ============================== */
(()=>{
  let cols=['PassengerId','Survived','Pclass','Age','Fare','Cabin','Embarked'];
  const rows=8;
  let gridData=Array.from({length:rows},(_,i)=>cols.map((c,j)=>{
    if(c==='PassengerId')return i+1;
    if(c==='Survived')return [1,0,0,1,0,1,0,1][i];
    if(c==='Pclass')return [3,1,3,1,3,1,2,3][i];
    if(c==='Age')return [22,38,26,35,NaN,14,58,NaN][i];
    if(c==='Fare')return [7.25,71.28,7.92,53.1,8.05,30.07,9.85,21][i];
    if(c==='Cabin')return [NaN,'C85',NaN,'C123',NaN,NaN,'E46',NaN][i];
    return ['S','C','S','S','Q','C','S',''] [i];
  }));
  let action='inspect';
  const A=[['inspect','inspect'],['isnull','isnull()'],['sum','isnull().sum()'],['dropna','dropna()'],['fillna0','fillna(0)'],['fillmean','fillna(mean)'],['dropcol','drop(Cabin)'],['dummies','get_dummies(sex)']];
  chips('pdActions',A,'inspect',v=>{action=v;run();press('pdActions',v)});
  function tbl(mat,heads,markNull){
    return `<div class="tbl"><div class="trow">${heads.map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>`+
      mat.map(r=>`<div class="trow">${r.map(v=>{
        const isN=v===null||v===undefined||v===''||(typeof v==='number'&&isNaN(v));
        if(markNull) return `<div class="tc ${isN?'r':'off'}">${isN?'True':'False'}</div>`;
        return `<div class="tc ${isN?'r':''}">${isN?'NaN':esc(v)}</div>`}).join('')}</div>`).join('')+'</div>';
  }
  function run(){
    let m=gridData.map(r=>[...r]), heads=[...cols], mark=false, facts='', why='';
    if(action==='isnull'){m=m.map(r=>r.map(v=>Number.isNaN(v)||v===null||v===''||v===undefined));mark=true;
      facts=F('what pandas uses','np.nan')+F('returned','True / False')+F('True means','the value is missing');
      why='isnull() never changes the frame — it hands you a same-shaped frame of booleans. False = fine, True = hole.'; }
    else if(action==='sum'){const c=cols.map((h,j)=>gridData.filter(r=>Number.isNaN(r[j])||r[j]===null||r[j]==='').length);
      facts=c.map((v,i)=>v?F(cols[i]+' missing',v,'bad'):F(cols[i]+' missing','0')).join('');
      why='Counting the Trues down each column is how you find out that Cabin is unusable and Age only needs a patch.'; }
    else if(action==='dropna'){const b=m.length;m=m.filter(r=>!r.some(v=>Number.isNaN(v)||v===null||v===''||v===undefined));
      facts=F('rows before',b)+F('rows after',m.length)+F('rows lost',b-m.length,'bad');
      why='Safe but destructive: one hole deletes the whole record. On Titanic that would throw away most of your data.'; }
    else if(action==='fillna0'){m=m.map(r=>r.map(v=>Number.isNaN(v)?0:v));
      facts=F('holes patched',gridData.flat().filter(v=>Number.isNaN(v)).length)+F('value used','0');
      why='Filling Age with 0 invents babies. Fill with something the column can actually mean.'; }
    else if(action==='fillmean'){const f=cols.map((h,j)=>{const good=m.map(r=>r[j]).filter(v=>Number.isFinite(v));return good.length?mean(good):0});
      m=m.map(r=>r.map((v,j)=>Number.isNaN(v)?+f[j].toFixed(2):v));
      facts=cols.map((h,j)=>F(h+' mean used',Number.isFinite(m[0][j])?fmt(m.flat()[j],2):'-')).join('');
      why='His choice for Age — and even better, the mean <em>within each Pclass</em>, because class 1 and 2 passengers were older than class 3.'; }
    else if(action==='dropcol'){heads=cols.filter(c=>c!=='Cabin');m=m.map(r=>r.filter((_,j)=>cols[j]!=='Cabin'));
      facts=F('columns before',cols.length)+F('after',heads.length)+F('call','drop(["Cabin"], axis=1, inplace=True)');
      why='axis=1 means "along the columns" = drop a column. Forgetting axis=1 is the most common pandas error there is.'; }
    else if(action==='dummies'){const sex=m.map(r=>['male','female','female','female','male','female','male','female'][r[0]-1]);
      heads=[...cols,'male'];m=m.map((r,i)=>[...r,sex[i]==='male'?1:0]);
      facts=F('one hot','sex -> male column')+F('drop_first=True','keeps one column only')+F('1 =','male')+F('0 =','female','good');
      why='Logistic regression only eats numbers. Keep both male and female and you get the dummy trap — the two columns add up to 1, so one of them is redundant.'; }
    else{facts=F('shape',`${gridData.length} × ${cols.length}`)+F('dtypes','int64 / float64 / object')+F('nulls',gridData.flat().filter(v=>Number.isNaN(v)).length,'bad');
      why='Click any cell to toggle its NaN, then run the repairs in order. That sequence — look, count, drop or fill, encode — is the first half of every ML notebook.';}
    $('pdStage').innerHTML=tbl(m,heads,mark);
    $('pdFacts').innerHTML=facts; say('pdWhy',why);
  }
  $('pdStage').onclick=e=>{const c=e.target.closest('.tc'); if(!c)return;
    const rowsE=[...$('pdStage').querySelectorAll('.trow')]; const ri=rowsE.indexOf(c.parentElement);
    if(ri<1||action!=='inspect')return; const ci=[...c.parentElement.children].indexOf(c);
    const v=gridData[ri-1][ci]; if(typeof v==='number'&&!Number.isNaN(v))gridData[ri-1][ci]=NaN;
    else if(Number.isNaN(v)){const heads=cols; gridData[ri-1][ci]=heads[ci]==='Age'?30:heads[ci]==='Cabin'?'B01':heads[ci]==='Survived'?0:heads[ci]==='Pclass'?3:heads[ci]==='Fare'?10:'S'}
    run();};
  run();
  /* describe */
  const hp=[62,93,95,115,110,145,130,150,120,100,88,95,105,130,145,120];
  const s=[...hp].sort((a,b)=>a-b);
  const q=p=>{const i=(s.length-1)*p/100,lo=Math.floor(i),hi=Math.ceil(i);return s[lo]+(s[hi]-s[lo])*(i-lo)};
  $('pdDesc').innerHTML=`<div class="trow">${['count','mean','std','min','25%','50%','75%','max'].map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>
   <div class="trow">${[s.length,fmt(mean(s),3),fmt(sd(s,1),3),s[0],fmt(q(25),2),fmt(q(50),2),fmt(q(75),2),s[s.length-1]].map(v=>`<div class="tc">${v}</div>`).join('')}</div>`;
})();

/* ============================== 04 · MATPLOTLIB ============================== */
(()=>{
  let kind='line', style='default', lw=3, explode=10;
  chips('mtKind',[['line','plot'],['scatter','scatter'],['bar','bar'],['hist','hist'],['pie','pie'],['sub','subplot 211/212']],kind,v=>{kind=v;press('mtKind',v);run()});
  chips('mtStyle',[['default','no style'],['seaborn','seaborn-v0_8'],['ggplot','ggplot'],['fivethirtyeight','fivethirtyeight']],style,v=>{style=v;press('mtStyle',v);run()});
  ['mtX1','mtY1','mtX2','mtY2'].forEach(i=>$(i).oninput=run);
  $('mtLw').oninput=e=>{lw=+e.target.value;$('mtLwV').textContent=lw+' pt';run()};
  $('mtExp').oninput=e=>{explode=+e.target.value;$('mtExpV').textContent='(0, '+explode/100+', 0, 0)';run()};
  const C=v=>getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  function parse(id){return nums($(id).value)}
  function run(){
    const x=parse('mtX1'),y=parse('mtY1'),x2=parse('mtX2'),y2=parse('mtY2');
    const cols=[C('--a'),C('--b'),C('--c'),C('--d'),C('--e')];
    const boxStyle=style==='default'?'':'<rect width="100%" height="100%" fill="'+C('--'+({seaborn:'a',ggplot:'b',fivethirtyeight:'c'}[style]||'a'))+'" opacity="0.05"/>';
    let out='',code='',facts='';
    if(kind==='line'||kind==='scatter'){
      const W=460,H=260,pad=34, xmax=Math.max(...x,...x2,1), ymax=Math.max(...y,...y2,1), ymin=Math.min(...y,...y2,0);
      const X=v=>pad+(W-2*pad)*(v/xmax), Y=v=>H-pad-(H-2*pad)*((v-ymin)/(ymax-ymin||1));
      let g=boxStyle+`<line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" class="axline"/><line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H-pad}" class="axline"/>`;
      for(let i=0;i<=4;i++){const vy=ymin+(ymax-ymin)*i/4;g+=`<text x="4" y="${Y(vy)+3}" class="axlab">${vy.toFixed(0)}</text>`}
      if(kind==='line'){g+=`<path d="${x.map((v,i)=>`${i?'L':'M'}${X(v)} ${Y(y[i])}`).join(' ')}" fill="none" stroke="${cols[0]}" stroke-width="${lw}" stroke-linecap="round"/>`;
        g+=`<path d="${x2.map((v,i)=>`${i?'L':'M'}${X(v)} ${Y(y2[i])}`).join(' ')}" fill="none" stroke="${cols[1]}" stroke-width="${lw}" stroke-dasharray="6 4"/>`;
        code=`import matplotlib.pyplot as plt\n\nx, y   = [${x}], [${y}]\nx2, y2 = [${x2}], [${y2}]\n\nplt.plot(x, y,  color='${cols[0]}', linewidth=${lw}, label='y')\nplt.plot(x2, y2, color='${cols[1]}', linewidth=${lw}, linestyle='--', label='y2')\nplt.title('Info'); plt.xlabel('x-axis'); plt.ylabel('y-axis')\nplt.legend(); plt.grid(True)\nplt.show()`;}
      else{g+=x.map((v,i)=>`<circle cx="${X(v)}" cy="${Y(y[i])}" r="${lw+2}" fill="${cols[0]}" opacity=".85"/>`).join('')+x2.map((v,i)=>`<circle cx="${X(v)}" cy="${Y(y2[i])}" r="${lw}" fill="${cols[1]}" opacity=".85"/>`).join('');
        code=`plt.scatter(x, y, color='blue', s=${(lw*20)|0}, label='first')\nplt.scatter(x2, y2, color='green', s=${(lw*14)|0}, label='second')\nplt.title('Info'); plt.xlabel('x-axis'); plt.ylabel('y-axis'); plt.legend()`;}
      g+=`<text x="${pad}" y="16" class="axlab" font-size="12">${style==='default'?'':style}</text>`+
         `<rect x="${W-100}" y="${pad-18}" width="8" height="8" fill="${cols[0]}"/><text x="${W-88}" y="${pad-11}" class="axlab">y</text>`+
         `<rect x="${W-60}" y="${pad-18}" width="8" height="8" fill="${cols[1]}"/><text x="${W-48}" y="${pad-11}" class="axlab">y2</text>`;
      out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="matplotlib ${kind} chart">${g}</svg>`;
      facts=F('points',x.length+x2.length)+F('x range',`${Math.min(...x,...x2)} – ${xmax}`)+F('y range',`${ymin} – ${ymax}`)+F('linewidth',lw);
    } else if(kind==='bar'){
      const W=460,H=260,pad=34,ymax=Math.max(...y,...y2,1),n=y.length+y2.length;
      const bw=(W-2*pad)/n*0.8;
      let g=boxStyle+`<line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" class="axline"/>`;
      y.forEach((v,i)=>{const Xx=pad+i*2*bw*1.25+bw*0.2;g+=`<rect x="${Xx}" y="${H-pad-(H-2*pad)*v/ymax}" width="${bw}" height="${(H-2*pad)*v/ymax}" fill="${cols[0]}"/>`;});
      y2.forEach((v,i)=>{const Xx=pad+(i*2+1)*bw*1.25+bw*0.2;g+=`<rect x="${Xx}" y="${H-pad-(H-2*pad)*v/ymax}" width="${bw}" height="${(H-2*pad)*v/ymax}" fill="${cols[1]}"/>`;});
      g+=x.map((v,i)=>`<text x="${pad+(i*2+0.7)*bw*1.25}" y="${H-pad+14}" class="axlab">${v}</text>`).join('');
      out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="bar chart">${g}</svg>`;
      code=`plt.bar(x,  y,  color='green', width=0.8, label='y')\nplt.bar(x2, y2, color='orange', width=0.8, label='y2')\nplt.title('Info'); plt.xlabel('x-axis'); plt.ylabel('y-axis'); plt.legend()`;
      facts=F('bar width','0.8')+F('groups',n)+F('tallest',ymax);
    } else if(kind==='hist'){
      const all=[...x,...y,...x2,...y2], lo=Math.min(...all), hi=Math.max(...all), bins=6;
      const c=Array(bins).fill(0); all.forEach(v=>c[Math.min(bins-1,Math.floor((v-lo)/((hi-lo)/bins||1)))]++);
      const W=460,H=260,pad=34,ymax=Math.max(...c,1);
      let g=boxStyle; c.forEach((v,i)=>{const bw=(W-2*pad)/bins;g+=`<rect x="${pad+i*bw}" y="${H-pad-(H-2*pad)*v/ymax}" width="${bw-3}" height="${(H-2*pad)*v/ymax}" fill="${cols[0]}" opacity=".85"/>`});
      g+=`<line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}" class="axline"/>`;
      out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="histogram">${g}</svg>`;
      code=`plt.hist(data, bins=${bins}, figsize=(10, 5))\nplt.title('Distribution'); plt.xlabel('value'); plt.ylabel('count')\n\n# one histogram per column of the frame:\ndf.hist(figsize=(10, 5))`;
      facts=F('values',all.length)+F('bins',bins)+F('peak bin',Math.max(...c));
    } else if(kind==='pie'){
      const v=[25,29.2,8.3,37.5], L=['class 1','class 2','class 3','unknown'], tot=sum(v);
      let a=-Math.PI/2, g=''; const cx=150,cy=130,r=95;
      v.forEach((val,i)=>{const ang=val/tot*2*Math.PI, a2=a+ang, big=ang>Math.PI?1:0;
        const ex=i===1?explode/100:0, mx=(Math.cos(a)+Math.cos(a2))/2*ex*r, my=(Math.sin(a)+Math.sin(a2))/2*ex*r;
        g+=`<path d="M${cx+mx} ${cy+my} L${cx+mx+r*Math.cos(a)} ${cy+my+r*Math.sin(a)} A${r} ${r} 0 ${big} 1 ${cx+mx+r*Math.cos(a2)} ${cy+my+r*Math.sin(a2)} Z" fill="${cols[i]}" stroke="${C('--card')}" stroke-width="2"/>`;
        g+=`<text x="${cx+mx+r*0.68*Math.cos(a+ang/2)}" y="${cy+my+r*0.68*Math.sin(a+ang/2)}" class="axlab" text-anchor="middle" fill="#fff">${(val).toFixed(1)}%</text>`;
        a=a2});
      g+=L.map((l,i)=>`<rect x="290" y="${60+i*24}" width="10" height="10" fill="${cols[i]}"/><text x="306" y="${69+i*24}" class="axlab">${l}</text>`).join('');
      out=`<svg viewBox="0 0 440 260" role="img" aria-label="pie chart with an exploded slice">${g}</svg>`;
      code=`plt.pie(vals, labels=L,\n      explode=(0, ${(explode/100).toFixed(2)}, 0, 0),\n      autopct='%1.1f%%', startangle=90)\nplt.title('Share by class')`;
      facts=F('slices',v.length)+F('explode',(explode/100).toFixed(2))+F('startangle','90°')+F('autopct','1 decimal');
    } else {
      const W=460,H=300, half=H/2;
      const t1=Array.from({length:50},(_,i)=>i*0.1), t2=Array.from({length:25},(_,i)=>i*0.2);
      const X=(v,mx)=>34+(W-60)*(v/mx), Y=v=>half-14-(half-40)*v;
      let g=`<rect x="4" y="4" width="${W-8}" height="${half-10}" fill="${C('--paper')}" stroke="${C('--line')}" rx="8"/>
             <rect x="4" y="${half+4}" width="${W-8}" height="${half-10}" fill="${C('--paper')}" stroke="${C('--line')}" rx="8"/>`;
      g+=`<path d="${t1.map((v,i)=>`${i?'L':'M'}${X(v,5)} ${Y(Math.sin(v))+ (0)}`).join(' ')}" fill="none" stroke="${cols[0]}" stroke-width="2"/>`;
      g+=`<path d="${t2.map((v,i)=>`${i?'L':'M'}${X(v,5)} ${half+26-(half-40)*Math.sin(v)*-1 - (half-40)*Math.sin(v)*2 + (half-40)*(1-Math.sin(v))}`).join(' ')}" fill="none" stroke="${cols[1]}" stroke-width="2" stroke-dasharray="5 4"/>`;
      g+=`<text x="10" y="18" class="axlab">subplot(2, 1, 1) — t = 0..5 step 0.1</text><text x="10" y="${half+18}" class="axlab">subplot(2, 1, 2) — t = 0..5 step 0.2</text>`;
      out=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="two subplots of sine and cosine">${g}</svg>`;
      code=`t1 = np.arange(0, 5, 0.1)   # 50 points
t2 = np.arange(0, 5, 0.2)   # 25 points, coarser

plt.figure(figsize=(6, 4))
plt.subplot(211); plt.plot(t1, np.sin(t1))
plt.subplot(212); plt.plot(t2, np.cos(t2), 'g--')`;
      facts=F('grid','2 rows × 1 col')+F('211','top-left')+F('212','bottom')+F('step','0.1 vs 0.2');
    }
    $('mtStage').innerHTML=out; $('mtCode').textContent=code; $('mtFacts').innerHTML=facts;
  }
  $('mtLwV').textContent='3 pt'; $('mtExpV').textContent='(0, 0.1, 0, 0)';
  run();
})();


/* ============================== 06 · THE LOOP ============================== */
(()=>{
  const S=[['train','1 · training data set','labelled rows go in'],['algo','2 · algorithm learns','the mapping is fitted'],
    ['model','3 · a model exists','predictor ready'],['predict','4 · new input','duck or not duck?'],['check','5 · score accuracy','is it good enough?'],
    ['again','6 · not acceptable','retrain on more data'],['ok','6 · acceptable','deploy it']];
  let i=-1;
  chips('mlSteps',[['next','Next step ▸'],['reset','Reset']], 'next', ()=>{i=(i+1)%S.length; if(i===6&&false)i=0; render()});
  $('mlSteps').onclick=e=>{const b=e.target.closest('.chip');if(!b)return; if(b.dataset.v==='reset'){i=-1;render()} else {i=(i+1)%S.length;render()}};
  function render(){
    $('mlLoop').innerHTML=`<div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:center;width:100%">${
      S.map(([id,l],k)=>`<div class="card" style="min-width:150px;${k===i?'outline:3px solid var(--fill);outline-offset:1px':''}"><h4 style="font-size:.95rem">${l}</h4><p>${
        ['891 Titanic rows / 14 tennis rows / 569 breast-cancer rows','linear, logistic, tree, SVM…','the trained thing that answers questions',
         'a row the model has never seen','accuracy / precision / recall / R²','feed it more data or change the algorithm',
         'into an app, a notebook, a Flask endpoint'][k]}</p></div>`).join('')}</div>`;
    say('mlStepWhy', i<0?'Press next and each stage lights up in order. This is the frame he repeats before every algorithm: train → predict → evaluate → retrain.'
      :`<b>${S[i][1]}</b> — ${['"the training data set that is fed to the model is labelled"','the algorithm is what you pick in station 12','a model is the thing you save; an algorithm is the recipe','"the prediction is evaluated for accuracy"','acceptable → deploy; not acceptable → train again on more data','this is the loop that never really ends'][Math.min(i,5)]}`);
  }
  render();
})();

/* ============================== 07 · SORT THE PROBLEMS ============================== */
(()=>{
  const P=[['price','Predict the price of a house from size, location and age','regression','a continuous quantity'],
    ['spam','Decide whether an email is spam or not spam','classification','categorical: spam / not spam'],
    ['seg','Group streaming viewers into similar audiences with no labels given','clustering','no output column at all'],
    ['fraud','Flag groups of fraudulent transactions from raw behaviour','clustering','he uses this as the fraud-cluster example'],
    ['med','Estimate a new customer\'s annual medical expenditure','regression','a number in dollars'],
    ['img','Say duck or not duck on a new photo','classification','labelled pictures in, label out'],
    ['stock','Forecast the next stock price','regression','continuous over time'],
    ['basket','Find which products are bought together','clustering','unsupervised association (Apriori)'],
    ['car','Self-driving car learning from rewards and −50 penalties','other','reinforcement, not one of the three'],
    ['xray','Label few X-rays, learn from thousands unlabelled','other','semi-supervised']];
  const B=[['regression','Regression'],['classification','Classification'],['clustering','Clustering'],['other','Neither / hybrid']];
  let picked=null, right=0, tried=0; const done=new Set(); const res={};
  const bucketHTML=()=>B.map(([id,l])=>`<button class="chip" data-v="${id}">${l}</button>`).join('');
  function render(){
    $('tgBuckets').innerHTML=bucketHTML();
    $('tgBuckets').onclick=e=>{const b=e.target.closest('.chip'); if(!b||!picked)return;
      const want=P.find(p=>p[0]===picked)[2]; tried++;
      const ok=b.dataset.v===want; if(ok){right++;done.add(picked)}
      res[picked]=ok?'ok':'no';
      say('tgWhy', ok?`<b>Right.</b> ${P.find(p=>p[0]===picked)[3]} — that is why it is ${want}.`
        :`Not this one. He files "${P.find(p=>p[0]===picked)[1].slice(0,34)}…" under <b>${want}</b>: ${P.find(p=>p[0]===picked)[3]}.`);
      picked=null; renderCards();};
    $('tgScore').innerHTML=F('score',`${right} / ${tried}`,right&&right===tried?'good':(tried&&right<tried?'bad':''))+F('cards left',P.length-done.size);
  }
  function renderCards(){
    $('tgCards').innerHTML=P.map(([id,q,cat])=>{
      const r=res[id];
      return `<div class="card" data-card="${id}" style="${r==='ok'?'border-color:var(--good)':r==='no'?'border-color:var(--bad);opacity:.65':'cursor:pointer'}${picked===id?';outline:3px solid var(--fill);outline-offset:1px':''}">
        <span class="tag ${(cat==='clustering'?'unsup':cat==='other'?'rl':'sup')}">${id}</span><p>${q}</p>
        ${r?`<p style="color:var(--muted)"><small>answer: <b>${cat}</b></small></p>`:''}</div>`}).join('');
    [...$('tgCards').querySelectorAll('.card')].forEach(c=>c.onclick=()=>{
      if(res[c.dataset.card])return; picked=c.dataset.card; renderCards(); say('tgWhy','Now choose the family above.');});
  }
  render(); renderCards();
})();

/* ============================== 08 · LINEAR ALGEBRA ============================== */
(()=>{
  let op='add';
  chips('laOps',[['add','A + B'],['sub','A − B'],['mul','A @ B'],['scalar','k · A'],['dot','dot product'],['proj','projection'],['det','determinant'],['inv','inverse'],['transpose','transpose'],['eig','eigen']],op,v=>{op=v;press('laOps',v);run()});
  ['laA','laB'].forEach(i=>$(i).oninput=run); $('laK').oninput=run;
  function run(){
    const A=parseMat($('laA').value)||[[2,2],[4,1]], B=parseMat($('laB').value)||[[2,3],[1,4]], k=+$('laK').value;
    $('laKv').textContent='k = '+k;
    let stage='',facts='',why='';
    const sh=(M,l,c='')=>`<div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">${l}</span>${matHTML(M,c)}</div>`;
    if(op==='add'||op==='sub'){
      const R=A.map((r,i)=>r.map((v,j)=>op==='add'?v+B[i][j]:v-B[i][j]));
      stage=sh(A,'A')+`<div class="arrow">${op==='add'?'+':'−'}</div>`+sh(B,'B')+`<div class="arrow">=</div>`+sh(R,'result','tot');
      facts=F('rule','corresponding elements')+F('A[0][0]'+op+B[0][0],R[0][0])+F('order stays',`${A.length}×${A[0].length}`);
      why=op==='add'?'His slide numbers: 2+2=4, 2+3=5, 4+1=5, 1+4=5. Same shape in, same shape out.'
        :'His numbers again: 2−2=0, 2−3=−1, 4−1=3, 1−4=−3. "Simple."';
    } else if(op==='mul'){
      if(A[0].length!==B.length){stage=sh(A,'A')+sh(B,'B');facts=F('blocked','cols(A) ≠ rows(B)','bad');why='"The number of rows in matrix one has to be equal to the number of columns in matrix 2" — he reads it the other way round on purpose: the inner sizes must match.'}
      else{const R=matMul(A,B);
        stage=sh(A,'A')+`<div class="arrow">×</div>`+sh(B,'B')+`<div class="arrow">=</div>`+sh(R,'A @ B','tot');
        facts=F('row1 · col1',`${A[0][0]}×${B[0][0]} + ${A[0][1]}×${B[1][0]} = ${R[0][0]}`)+
              F('row1 · col2',`${A[0][0]}×${B[0][1]} + ${A[0][1]}×${B[1][1]} = ${R[0][1]}`)+
              F('result',R.flat().join(' '))+F('inner rule','(m×n)(n×p) → m×p');
        why='His worked answer: 2×2+2×1=6, 2×3+2×4=14, 4×2+1×1=9, 4×3+1×4=16 → [[6 14] [9 16]]. Rows of the first against columns of the second.';}
    } else if(op==='scalar'){
      const R=A.map(r=>r.map(v=>v*k));
      stage=sh(A,'A')+`<div class="arrow">${k}×</div>`+sh(R,'k · A',k<0?'r':'on');
      facts=F('k',k)+F('growth',k>1?'longer':k===0?'a point':k<0?('flipped & '+(Math.abs(k)>1?'longer':'shorter')):(k===1?'unchanged':'shorter'))+F('direction',k<0?'reversed':'same');
      why='"a positive scalar will make the vector grow, a negative one shrinks it and flips it" — his −k demo pointed the arrow the other way.';
    } else if(op==='dot'||op==='proj'){
      const v1=[A[0][0],A[0][1]??0], v2=[B[0][0],B[0][1]??1];
      const d=sum(v1.map((x,i)=>x*v2[i])), len2=sum(v2.map(x=>x*x)), scale=len2?d/len2:0;
      const foot=v2.map(x=>x*scale);
      stage=`<div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">${op==='dot'?'dot product = work done by both':'projection of v₁ onto v₂'}</span>
        <svg viewBox="0 0 300 220" role="img" aria-label="vector projection"><line x1="10" y1="200" x2="290" y2="200" class="axline"/><line x1="150" y1="10" x2="150" y2="210" class="axline"/>
        ${[[v1,'var(--a)','v₁'],[v2,'var(--b)','v₂'],foot.length&&op==='proj'?[foot,'var(--c)','proj']:''].filter(Array.isArray).map(([v,c,l])=>{
          const x=150+v[0]*12, y=200-v[1]*12; return `<line x1="150" y1="200" x2="${x}" y2="${y}" stroke="${c}" stroke-width="4"/><text x="${x+5}" y="${y}" class="axlab" fill="${c}">${l}</text>`}).join('')}
        ${op==='proj'?`<line x1="${150+v1[0]*12}" y1="${200-v1[1]*12}" x2="${150+foot[0]*12}" y2="${200-foot[1]*12}" stroke="var(--muted)" stroke-dasharray="4 3"/>`:''}</svg></div>`;
      facts=F('v₁',[...v1])+F('v₂',[...v2])+F('v₁ · v₂',fmt(d,3),'hot')+
        F('‖v₁‖',fmt(Math.hypot(...v1),3))+F('angle',fmt(Math.acos(clamp(d/(Math.hypot(...v1)*Math.hypot(...v2)||1),-1,1))*180/Math.PI,1)+'°')+
        (op==='proj'?F('projection',`[${fmt(foot[0],3)}, ${fmt(foot[1],3)}]`)+F('length',fmt(Math.hypot(...foot),3)):'');
      why=op==='dot'?'Add the paired products — the sum he calls the dot product. Perpendicular vectors give exactly 0, which is the test for "no relation at all".'
        :'"If I know all about v₂ but nothing about v₁, projecting v₁ onto v₂ extracts the information v₁ carries in a direction I already understand." That sentence is PCA in one line.';
    } else if(op==='det'){
      const d=det(A), d2=det(B);
      stage=sh(A,'A')+sh([[A[0][0],A[0][1]],[A[1]??[0,0],A[1]?A[1][1]:0]],'2×2 form')+`<div class="arrow">→</div><div class="tc tot" style="font-size:1.3rem">${fmt(d,3)}</div>`;
      facts=F('det(A)',fmt(d,3),'hot')+F('det(B)',fmt(d2,3))+F('adjugate swap','a↔d, flip signs of b,c')+F('invertible?',d!==0?'yes':'no — singular','bad')+
        F('area meaning',fmt(Math.abs(d),3)+' units²');
      why='The determinant is "the scalar value of that particular matrix", and the reason it matters is that it tells you whether an inverse exists and gives you the eigenvalues.';
    } else if(op==='inv'){
      const I=inv2(A);
      stage=sh(A,'A')+`<div class="arrow">⁻¹</div>`+(I?sh(I,'A⁻¹','tot')+`<div class="arrow">·</div>`+sh(A,'A⁻¹ @ A = I','on'):'<span class="hint">no inverse</span>');
      const d=det(A);
      facts=F('det',fmt(d,3))+F('formula','(1/det)·[[d,−b],[−c,a]]')+F('A⁻¹ entries',I?I.flat().map(v=>fmt(v,4)).join(' '):'—');
      why='His picture: "I walked 50 m forward and 50 m back — total distance 100 m but I am where I started." The inverse is the walk-back, and A·A⁻¹ is the identity, the "nothing happened" matrix. For his 4x+3y=−3 / −10x−2y=5 pair the determinant is 22 and the inverse is (1/22)·[[−2,−3],[10,4]], which gives y = −5.';
    } else if(op==='transpose'){
      stage=sh(A,'A')+`<div class="arrow">T</div>`+sh(T(A),'A.T','on');
      facts=F('shape before',`${A.length}×${A[0].length}`)+F('after',`${A[0].length}×${A.length}`)+F('first column became','first row');
      why='"You convert the rows into columns. It helps you flip the dimensionality" — he does it to turn a column of 200–300 values into a row before drawing the PCA vectors.';
    } else {
      const tr=traceEig(A);
      stage=sh(A,'A')+`<div class="arrow">→</div><div class="tbl"><div class="trow">${tr.vals.map(v=>`<div class="tc ${v.im?'r':'tot'}">${fmt(v.re,3)}${v.im?' ± '+fmt(v.im,3)+'i':''}</div>`).join('')}</div></div>`+
        `<div style="display:flex;flex-direction:column;gap:6px"><span class="lbl">eigenvectors</span>${tr.vecs.map(v=>matHTML([v])).join('')}</div>`;
      facts=tr.vals.map((v,i)=>F('λ'+(i+1),fmt(v.re,3)+(v.im?` ± ${fmt(v.im,3)}i`:''))).join('')+
        F('trace = Σλ',fmt(A[0][0]+(A[1]?A[1][1]:0),3))+F('det = Πλ',fmt(det(A),3));
      why='Eigenvalues add up to the trace and multiply to the determinant — that is how you check your arithmetic. A direction whose arrow only stretches is an eigenvector, and the stretch factor is its eigenvalue.';
    }
    $('laStage').innerHTML=stage; $('laFacts').innerHTML=facts; say('laWhy',why);
  }
  function traceEig(A){
    const n=A.length; if(n!==2||A[1].length!==2) return {vals:[{re:NaN}],vecs:[]};
    const a=A[0][0],b=A[0][1],c=A[1][0],d=A[1][1];
    const t=a+d, dl=t*t-4*(a*d-b*c);
    if(dl<0) return {vals:[{re:t/2,im:Math.sqrt(-dl)/2},{re:t/2,im:-Math.sqrt(-dl)/2}],vecs:[[1,0],[0,1]]};
    const s=Math.sqrt(dl), l1=(t+s)/2, l2=(t-s)/2;
    const vec=l=>{ if(b) return [1,(l-a)/b]; if(c) return [(l-d)/c,1]; return [1,0] };
    return {vals:[{re:l1},{re:l2}],vecs:[vec(l1),vec(l2)]};
  }
  /* row echelon */
  const RE=[
    {t:'start',m:[[2,1,-1,2],[1,3,2,1],[1,1,1,2]],w:'His system: 2x + y − z = 2 · x + 3y + 2z = 1 · x + y + z = 2. The augmented matrix is the four columns you see.'},
    {t:'R1 / 2',m:[[1,0.5,-0.5,1],[1,3,2,1],[1,1,1,2]],w:'Step 1: make the leading entry of row 1 a 1. "R1 divided by 2 — we get 1, 1/2, −1/2 and 1."'},
    {t:'R2 − R1',m:[[1,0.5,-0.5,1],[0,2.5,2.5,0],[1,1,1,2]],w:'Step 2: kill the x-term in row 2.'},
    {t:'R3 − R1',m:[[1,0.5,-0.5,1],[0,2.5,2.5,0],[0,0.5,1.5,1]],w:'Step 3: same for row 3. Now column 1 is clean except the top.'},
    {t:'R2 · 2/5',m:[[1,0.5,-0.5,1],[0,1,1,0],[0,0.5,1.5,1]],w:'Step 4: make row 2 lead with a 1.'},
    {t:'R1 − ½R2',m:[[1,0,-1,1],[0,1,1,0],[0,0.5,1.5,1]],w:'Step 5: clean upward too — that is what makes it reduced.'},
    {t:'R3 − ½R2',m:[[1,0,-1,1],[0,1,1,0],[0,0,1,1]],w:'Step 6: the staircase is now visible — 1, then 1 to its right, then 1 again.'},
    {t:'R1 + R3',m:[[1,0,0,2],[0,1,1,0],[0,0,1,1]],w:'Step 7.'},
    {t:'R2 − R3',m:[[1,0,0,2],[0,1,0,-1],[0,0,1,1]],w:'Step 8: identity on the left. Read the answer straight off the last column: x = 2, y = −1, z = 1.'},
  ];
  let ri=0;
  chips('reSteps',RE.map((s,i)=>[String(i),i===0?'start':s.t]),'0',v=>{ri=+v;render()});
  function render(){
    $('reStage').innerHTML=matHTML(RE[ri].m.map(r=>r.map(v=>Math.round(v*1000)/1000)),)+
      `<div class="hint" style="margin-top:6px">solution so far: ${ri>=8?'x = 2, y = −1, z = 1':ri>=7?'x = 2, z = 1, y follows':'keep eliminating'}</div>`;
    say('reWhy',`<b>${RE[ri].t}</b> — ${RE[ri].w}`);
    press('reSteps',String(ri));
  }
  render();
  /* eigen probe */
  function eig(){
    const M=parseMat($('egM').value)||[[2,0],[0,1]], ang=+$('egAng').value;
    $('egAngV').textContent=ang+'°';
    const v=[Math.cos(ang*Math.PI/180),Math.sin(ang*Math.PI/180)];
    const w=[M[0][0]*v[0]+M[0][1]*v[1], M[1][0]*v[0]+M[1][1]*v[1]];
    const sc=1.15, cx=220, cy=130, R=Math.hypot(...v), W=Math.hypot(...w);
    const arrow=(x,y,c,l,dash)=>`<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}" stroke="${c}" stroke-width="4" ${dash?'stroke-dasharray="7 5"':''}/>
      <circle cx="${x}" cy="${y}" r="5" fill="${c}"/><text x="${x+8}" y="${y-6}" class="axlab" fill="${c}">${l}</text>`;
    const par=Math.abs(w[0]*v[1]-w[1]*v[0])<0.02;
    $('egSvg').innerHTML=`<line x1="10" y1="${cy}" x2="430" y2="${cy}" class="axline"/><line x1="${cx}" y1="8" x2="${cx}" y2="252" class="axline"/>`+
      arrow(cx+R*80*sc,cy-R*80*sc,'var(--a)','v',(false))+
      arrow(cx+w[0]*80*sc,cy-w[1]*80*sc,par?'var(--c)':'var(--b)','M·v')+
      (par?`<text x="14" y="24" class="axlab" fill="var(--c)" font-size="13">parallel — this is an eigenvector, λ = ${fmt(W/R,3)}</text>`
           :`<text x="14" y="24" class="axlab" fill="var(--b)" font-size="13">bent by ${fmt(Math.abs(Math.atan2(w[1],w[0])-Math.atan2(v[1],v[0]))*180/Math.PI,1)}° — not an eigenvector</text>`);
    say('egWhy','Drag the angle until the two arrows line up. Every angle where the output stays on the input line is an eigenvector, and how much it grew is the eigenvalue. M = [[2,0],[0,1]] stretches x by 2 and leaves y alone — so its eigenvectors are exactly the two axes, which is why PCA loves this matrix.');
  }
  $('egAng').oninput=eig; $('egM').oninput=eig; eig();
  run();
})();

/* ============================== 09 · CALCULUS ============================== */
(()=>{
  const FN={ '3x^2':x=>3*x*x, '3x^2 + 5x':x=>3*x*x+5*x, 'x^3':x=>x**3, '2x':x=>2*x };
  const D={ '3x^2':x=>6*x, '3x^2 + 5x':x=>6*x+5, 'x^3':x=>3*x*x, '2x':()=>2 };
  let f='3x^2';
  chips('dvFn',Object.keys(FN).map(k=>[k,k,'→ '+({'3x^2':'6x','3x^2 + 5x':'6x+5','x^3':'3x²','2x':'2'})[k]]),f,v=>{f=v;press('dvFn',v);run()});
  $('dvDx').oninput=run; $('dvX').oninput=run;
  function run(){
    const dx=+$('dvDx').value, x0=+$('dvX').value, W=460,H=250;
    const F=FN[f], Dv=D[f];
    const bx=[-3,4], lo=Math.min(F(-3),F(4)), hi=Math.max(F(-3),F(4));
    const sx=v=>(v-bx[0])/(bx[1]-bx[0])*W, sy=v=>H-20-((v-lo)/(hi-lo))*(H-40);
    const pts=Array.from({length:130},(_,i)=>{const x=bx[0]+(bx[1]-bx[0])*i/129;return [sx(x),sy(F(x))]});
    const y0=F(x0), y1=F(x0+dx), slope=(y1-y0)/dx, m=Dv(x0);
    const line=(xv)=>y0+slope*(xv-x0);
    const lp=[[sx(bx[0]),sy(line(bx[0]))],[sx(bx[1]),sy(line(bx[1]))]];
    $('dvSvg').innerHTML=`<line x1="0" y1="${sy(0)}" x2="${W}" y2="${sy(0)}" class="axline"/>
      <line x1="${sx(0)}" y1="0" x2="${sx(0)}" y2="${H}" class="axline"/>
      <path d="M${pts.map(p=>p.join(' ')).join(' L').replace(/ L L/,' L')}" fill="none" stroke="var(--a)" stroke-width="3"/>
      <line x1="${lp[0][0]}" y1="${lp[0][1]}" x2="${lp[1][0]}" y2="${lp[1][1]}" stroke="var(--b)" stroke-width="2" stroke-dasharray="6 4"/>
      <circle cx="${sx(x0)}" cy="${sy(y0)}" r="5" fill="var(--a)"/><circle cx="${sx(x0+dx)}" cy="${sy(y1)}" r="5" fill="var(--b)"/>
      <text x="${sx(x0)+8}" y="${sy(y0)-8}" class="axlab">(x, f(x))</text><text x="${sx(x0+dx)+8}" y="${sy(y1)-8}" class="axlab">(x+Δx, f(x+Δx))</text>
      <text x="8" y="16" class="axlab">f(x) = ${f}</text>`;
    $('dvFacts').innerHTML=F('Δx',fmt(dx,2))+F('secant slope',fmt(slope,4))+F("f'(x) exact",fmt(m,4),'hot')+F('x',fmt(x0,2))+
      F('error',fmt(Math.abs(slope-m),4),Math.abs(slope-m)<0.02?'good':'');
    say('dvWhy',`He builds it as ${''}<code>f'(x) = lim<sub>Δx→0</sub> [f(x+Δx) − f(x)] / Δx</code> and stresses that Δx "is not exactly zero" — you only slide it towards zero. Here f(x)=${f} so f'(x)=${({'3x^2':'6x','3x^2 + 5x':'6x+5','x^3':'3x²','2x':'2'})[f]}. Drag Δx down and the dashed secant snaps onto the tangent: that click, frozen, is what a gradient is.`);
  }
  run();
  /* gradient descent */
  const sig=x=>1/(1+Math.exp(-x));
  let E=10000;
  chips('gdIters',[['10','10 steps'],['100','100'],['1000','1 000'],['10000','10 000'],['60000','60 000']],String(E),v=>{E=+v;press('gdIters',v);gdRun()});
  ['gdIn','gdTg'].forEach(i=>$(i).oninput=gdRun); $('gdLr').oninput=gdRun;
  function gdRun(){
    const x=+$('gdIn').value, t=+$('gdTg').value, lr=+$('gdLr').value;
    $('gdLrV').textContent=lr;
    let w=0.5, hist=[];
    for(let i=0;i<E;i++){const p=sig(x*w), g=2*(p-t)*p*(1-p)*x; w-=lr*g; if(i%Math.max(1,Math.floor(E/60))===0)hist.push([w,(sig(x*w)-t)**2]);}
    hist.push([w,(sig(x*w)-t)**2]);
    const pFinal=sig(x*w), cost=ww=>(sig(x*ww)-t)**2;
    const W=460,H=180, wx0=-3, wx1=E>20000?25:18;
    const sx=v=>10+(W-20)*clamp((v-wx0)/(wx1-wx0),0,1), sy=v=>H-16-(v/ (cost(Math.max(wx0,wx1))||1))*(H-34);
    const curve=Array.from({length:120},(_,i)=>{const ww=wx0+(wx1-wx0)*i/119;return [sx(ww),sy(Math.min(cost(ww),cost(Math.max(wx0,wx1))))]});
    const path=curve.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');
    const trail=hist.map((h,i)=>`${i?'L':'M'}${sx(h[0]).toFixed(1)} ${sy(h[1]).toFixed(1)}`).join(' ');
    $('gdBowl').innerHTML=`<path d="${path}" fill="none" stroke="var(--line)" stroke-width="2"/>
      <path d="${trail}" fill="none" stroke="var(--b)" stroke-width="2" stroke-dasharray="5 4"/>
      ${hist.map(h=>`<circle cx="${sx(h[0])}" cy="${sy(Math.min(h[1],cost(Math.max(wx0,wx1))))}" r="2.5" fill="var(--b)"/>`).join('')}
      <circle cx="${sx(w)}" cy="${sy(Math.min(cost(w),cost(Math.max(wx0,wx1))))}" r="7" fill="var(--fill)" stroke="var(--hl-edge)" stroke-width="2"/>
      <line x1="${sx(12)}" y1="6" x2="${sx(12)}" y2="${H-16}" class="axline" opacity=".8"/>
      <text x="${sx(12)+4}" y="18" class="axlab">minimum</text>
      <text x="12" y="${H-4}" class="axlab">weight w →</text><text x="12" y="16" class="axlab">cost = (sigmoid(x·w) − target)²</text>`;
    const diverge=!isFinite(w)||Math.abs(w)>1e6;
    $('gdFacts').innerHTML=F('epochs',E)+F('weight',diverge?'diverged':fmt(w,4),diverge?'bad':'')+
      F('prediction',fmt(pFinal,5),'hot')+F('target',fmt(t,2))+F('cost',fmt(cost(w),6))+
      F('gradient','2(p−t)·p(1−p)·x');
    say('gdWhy',diverge?`<b>Diverged.</b> learning rate ${lr} with ${E} steps threw the walker out of the bowl. That is the failure mode he never showed but warned about with the "keep iterating" phrasing.`
      :`His run: input ${x}, target ${t}, weight starts 0.50. ${E===10?'10 steps: the answer is still around <b>0.47</b>':E===1000?'1 000 steps: it comes down to <b>0.36</b>':E===10000?'10 000 steps: <b>0.30000002</b> — he reads exactly that off the screen, and says "this is how gradient descent works"':'deep into the basin: <b>'+fmt(pFinal,6)+'</b>, the bottom of the bowl'}. ${Math.abs(pFinal-t)<0.005?'You have converged.':'Not converged yet — add iterations or raise the learning rate.'}`);
  }
  gdRun();
})();

/* ============================== 10 · PROBABILITY ============================== */
(()=>{
  let ev='dice2';
  const EV={dice2:{l:'P(dice = 2)',n:1,t:6,dice:true,w:'One face out of the six that make up the sample space. "It can be either 1 2 3 4 5 6 — that range is the sample space."'},
    diceeven:{l:'P(even)',n:3,t:6,dice:true,w:'Three faces of six. Note how complementary probabilities must add to 1: P(even) + P(odd) = 1.'},
    dicegt4:{l:'P(> 4)',n:2,t:6,dice:true,w:'Two outcomes: 5 and 6. His 0.6 / 0.4 point: whatever is not in the event is exactly its complement.'},
    king:{l:'P(king)',n:4,t:52,w:'"The probability that a card is a king is 4/52." 13 ranks, 4 suits.'},
    face:{l:'P(face card)',n:12,t:52,w:'Jack, queen, king of four suits = 12 of 52 = 1/3. This is the denominator of his Bayes card example.'},
    joint:{l:'P(king AND heart)',n:1,t:52,w:'Joint probability of two things at once — one specific card out of 52. He reads "1/52" off the slide.'},
    cond:{l:'P(king | face)',n:4,t:12,w:'Conditional: you already know it is a face card, so the sample space shrinks from 52 to 12. 4/12 = 1/3 — the posterior.'}};
  chips('pbEv',Object.entries(EV).map(([k,v])=>[k,v.l]),ev,v=>{ev=v;press('pbEv',v);run()});
  function run(){
    const e=EV[ev], p=e.n/e.t;
    let stage='';
    if(e.dice){stage=`<div class="tbl"><div class="trow">${[1,2,3,4,5,6].map(n=>`<div class="tc ${[2].includes(n)&&ev==='dice2'||(['diceeven'].includes(ev)&&n%2===0)||(['dicegt4'].includes(ev)&&n>4)?'on':''}">${n}</div>`).join('')}</div></div>`}
    else if(ev==='king'||ev==='face'||ev==='joint'){
      const suits=['♠','♥','♣','♦'], ranks=['2','3','4','5','6','7','8','9','10','J','Q','K','A'];
      stage=`<div class="tbl" style="max-width:340px">${ranks.map((r,ri)=>`<div class="trow">${suits.map(s=>{
        const on=(ev==='king'&&r==='K')||(ev==='face'&&['J','Q','K'].includes(r))||(ev==='joint'&&r==='K'&&s==='♥');
        return `<div class="tc ${on?'on':''}" style="min-width:26px;font-size:.75rem">${r}${s}</div>`}).join('')}</div>`).join('')}</div>`;
    } else stage=`<div class="tbl"><div class="trow">${['J','Q','K'].map(()=>'<div class="tc on">face</div>').join('')}${Array.from({length:9},()=>'<div class="tc off">other</div>').join('')}</div></div>`;
    $('pbStage').innerHTML=stage;
    $('pbFacts').innerHTML=F('desired',e.n)+F('total',e.t)+F('P',fmt(p,4),'hot')+F('percent',pct(p,2))+F('complement',fmt(1-p,4))+F('sum check',fmt(p+(1-p),2));
    say('pbWhy',e.w);
  }
  run();
  /* Bayes */
  const bs=['byPa','byLk','byEv'];
  function bayes(){
    const a=+$('byPa').value/100, lk=+$('byLk').value/100, ev=+$('byEv').value/100;
    $('byPaV').textContent=pct(a,1); $('byLkV').textContent=pct(lk,0); $('byEvV').textContent=pct(ev,0);
    const post=a*lk/ev;
    const W=440,H=150, y=68, box=(x,w,label,val,col)=>`<rect x="${x}" y="${y-30}" width="${w}" height="60" rx="10" fill="${col}" opacity=".2" stroke="${col}" stroke-width="2"/>
      <text x="${x+w/2}" y="${y+2}" text-anchor="middle" font-size="15" fill="${col}">${val}</text>
      <text x="${x+w/2}" y="${y+40}" text-anchor="middle" class="axlab">${label}</text>`;
    const op='var(--a)', lp='var(--b)', ep='var(--c)', rp='var(--fill)';
    $('bySvg').innerHTML=`<text x="8" y="18" class="axlab">P(A|B) = P(B|A) · P(A) / P(B)</text>
      ${box(10,90,'prior P(drinks)',pct(a,1),op)}<text x="118" y="${y+4}" font-size="20" class="axlab">×</text>
      ${box(140,90,'likelihood P(+|drinks)',pct(lk,0),lp)}<text x="248" y="${y-6}" font-size="20" class="axlab">÷</text>
      ${box(262,80,'evidence P(+)',pct(ev,0),ep)}<text x="352" y="${y+4}" font-size="20" class="axlab">=</text>
      ${box(372,62,'posterior',pct(post,2),rp)}`;
    $('byFacts').innerHTML=F('prior × likelihood',fmt(a*lk,5))+F('posterior',pct(post,2),'hot')+F('at his settings','5% × 10% / 15% = 3.33%')+F('a new patient tests +','so '+pct(post,1)+' chance they drink');
    say('byWhy',`His clinic: "you test if a patient drinks; 5% of the people you test are drinking, 10% of them test positive... the probability that out of all of those they were drinking is calculated by 0.05 × 0.10 / 0.15 = <b>3.33%</b>". The punch line he draws: a positive test moved the chance only from 5 % to 3.33 % — <b>the posterior is not what intuition says</b>, because the evidence term P(+) is big. Bayes' theorem is exactly this: it "shows the probability and its inverse".`);
  }
  bs.forEach(i=>$(i).oninput=bayes); bayes();
  /* normal */
  function norm(){
    const mu=+$('ndMu').value, s=+$('ndSg').value, W=460,H=190;
    const bx=[-5,5], sx=v=>(v-bx[0])/(bx[1]-bx[0])*W;
    const pdf=v=>Math.exp(-((v-mu)**2)/(2*s*s))/(s*Math.sqrt(2*Math.PI));
    const mx=pdf(mu);
    const pts=Array.from({length:120},(_,i)=>{const x=bx[0]+10*i/119;return [sx(x),H-22-(pdf(x)/mx)*(H-46)]});
    $('ndSvg').innerHTML=`<line x1="0" y1="${H-22}" x2="${W}" y2="${H-22}" class="axline"/>
      <line x1="${sx(mu)}" y1="6" x2="${sx(mu)}" y2="${H-22}" stroke="var(--a)" stroke-dasharray="4 4"/>
      <path d="M${pts.map(p=>p.join(' ')).join(' L').replace(' L L',' L')}" fill="none" stroke="var(--c)" stroke-width="3"/>
      ${[-1,1].map(k=>`<line x1="${sx(mu+k*s)}" y1="${H-22}" x2="${sx(mu+k*s)}" y2="${H-46}" stroke="var(--muted)" opacity=".5"/>`).join('')}
      <text x="${sx(mu)+4}" y="16" class="axlab">μ = ${mu}</text><text x="8" y="16" class="axlab">±1σ covers 68.3%, ±2σ 95.4%, ±3σ 99.7%</text>`;
    say('ndEq',`<code>y = 1/(σ√(2π)) · e^(−(x−μ)²/2σ²)</code> — his formula, read letter by letter: "x is the normal random variable, μ is the mean and σ is the standard deviation." <b>The mean determines the location of the curve; the standard deviation determines the height and the spread.</b> That is exactly what the two sliders do.`);
  }
  $('ndMu').oninput=norm; $('ndSg').oninput=norm; norm();
  /* CLT */
  let trials=400;
  chips('clT',[['200','200'],['400','400'],['2000','2 000']],String(trials),v=>{trials=+v;press('clT',v);clt()});
  let seed=7;
  const rnd=()=>{seed=(seed*1103515245+12345)&0x7fffffff;return seed/0x7fffffff};
  function clt(){
    const n=+$('clN').value; $('clNv').textContent='n = '+n;
    const base=[0,1,2,3,4,5,6,7,8,9];
    const ms=[]; let s0=seed;
    for(let t=0;t<trials;t++){let acc=0;for(let i=0;i<n;i++)acc+=base[Math.floor(rnd()*10)];ms.push(acc/n)}
    seed=s0;
    const W=460,H=190, lo=0, hi=10, bins=24, c=Array(bins).fill(0);
    ms.forEach(v=>c[Math.min(bins-1,Math.floor((v-lo)/(hi-lo)*bins))]++);
    const mx=Math.max(...c);
    $('clSvg').innerHTML=`${c.map((v,i)=>`<rect x="${10+i*(W-20)/bins}" y="${H-24-(v/mx)*(H-50)}" width="${(W-20)/bins-1.5}" height="${(v/mx)*(H-50)}" fill="var(--a)"/>`).join('')}
      <line x1="10" y1="${H-24}" x2="${W-10}" y2="${H-24}" class="axline"/>
      <text x="12" y="16" class="axlab">${trials} samples of size ${n} drawn from a flat 0–9 set — the population is NOT normal</text>
      <text x="12" y="${H-6}" class="axlab">mean of the sample →</text>`;
    say('clWhy',`At n = 1 the histogram is flat, because the source is flat. ${n>=30?'n = '+n+': the bumps have merged into a bell. This is the number he quotes — "as your sample size increases to 50, the distribution of your mean becomes nearly identical to a normal distribution"':n>=10?'n = '+n+': starting to look bell-shaped, the middle is getting fat':'n = '+n+': still lumpy — the theorem has not kicked in yet'}. The central limit theorem is the reason confidence intervals and p-values work at all, and the reason "more data" fixes so many things.`);
  }
  $('clN').oninput=clt; clt();
  /* hypothesis */
  let alpha=5;
  chips('hyTh',[['1','1 %'],['5','5 %'],['10','10 %']],'5',v=>{alpha=+v;press('hyTh',v);hy()});
  function hy(){
    const n=+$('hyN').value; $('hyNv').textContent=n+' days';
    const p=Math.pow(0.75,n);
    const W=460,H=170, sx=i=>24+i*(W-40)/24, sy=v=>H-24-v*(H-52);
    $('hySvg').innerHTML=`${Array.from({length:25},(_,i)=>`<circle cx="${sx(i)}" cy="${sy(Math.pow(0.75,i))}" r="${i===n?6:2.6}" fill="${i===n?'var(--fill)':'var(--a)'}"/>`).join('')}
      <path d="${Array.from({length:25},(_,i)=>`${i?'L':'M'}${sx(i)} ${sy(Math.pow(0.75,i))}`).join(' ')}" fill="none" stroke="var(--a)" stroke-width="2" opacity=".5"/>
      <line x1="14" y1="${sy(alpha/100)}" x2="${W-14}" y2="${sy(alpha/100)}" stroke="var(--bad)" stroke-width="2" stroke-dasharray="6 4"/>
      <text x="${W-120}" y="${sy(alpha/100)-6}" class="axlab" fill="var(--bad)">α = ${alpha}%</text>
      <line x1="14" y1="${H-24}" x2="${W-14}" y2="${H-24}" class="axline"/><line x1="${sx(0)}" y1="10" x2="${sx(0)}" y2="${H-24}" class="axline"/>
      <text x="12" y="16" class="axlab">P(null is right) after n quiet days = 0.75ⁿ</text><text x="12" y="${H-6}" class="axlab">days →</text>`;
    $('hyFacts').innerHTML=F('days',n)+F('probability',pct(p,2))+F('threshold',alpha+' %')+
      F('verdict',p*100<alpha?'reject the null':'keep the null',p*100<alpha?'bad':'good')+F('(3/4)³',pct(0.421875,1))+F('(3/4)¹²',pct(0.0317,2));
    say('hyWhy',p*100<alpha?`At ${n} days the chance of staying quiet by luck is <b>${pct(p,2)}</b>, below your ${alpha} % line — the pattern is too unlikely to be chance, so the null hypothesis <b>"John is not cheating" is rejected</b>. ${n===12?'This is the exact number he lands on: 3.2 %, "which is less than 0.05"':''}.`:
      `At ${n} days, ${pct(p,1)} is still ${alpha>=p*100?'above':'not below'} your ${alpha} % line, so you <b>cannot</b> reject the null. Not-cheating is still a plausible explanation for what you observed — you need more days (or a stricter α).`);
  }
  $('hyN').oninput=hy; hy();
})();

/* ============================== 11 · STATISTICS ============================== */
(()=>{
  ['stSrc'].forEach(i=>$(i).oninput=run);
  chips('stPresets',[['9,2,9,10,2,7','his dragons set'],['62,93,95,115,110,145,130,150','horsepower'],['45,45,58,59,71,71','quartile demo']],'',v=>{$('stSrc').value=v;run()});
  function run(){
    const a=nums($('stSrc').value); if(a.length<2)return;
    const s=[...a].sort((x,y)=>x-y), m=mean(a), v=sd(a,0)**2, sv=sd(a,0), s1=sd(a,1);
    const q=p=>{const i=(s.length-1)*p/100,lo=Math.floor(i),hi=Math.ceil(i);return s[lo]+(s[hi]-s[lo])*(i-lo)};
    const modes=uniq(a).map(x=>[x,a.filter(y=>y===x).length]).filter(([,c])=>c===Math.max(...a.map(y=>a.filter(x=>x===y).length)));
    $('stStage').innerHTML=`<div style="display:flex;flex-direction:column;gap:8px"><span class="lbl">the values, sorted</span>
      <div class="tbl"><div class="trow">${s.map((v,i)=>`<div class="tc ${Math.abs(v-m)<sv?'on':''}">${fmt(v,2)}</div>`).join('')}</div></div>
      <span class="lbl">squared distance from the mean</span>
      <div class="tbl"><div class="trow">${a.map(x=>`<div class="tc ${Math.abs(x-m)<1?'g':'r'}">${fmt((x-m)**2,2)}</div>`).join('')}</div></div>
      <p class="hint">Shaded cells are inside ±1σ of the mean. Green squares are small deviations, red ones are the points dragging the variance up.</p></div>`;
    $('stFacts').innerHTML=[['n',a.length],['mean μ',fmt(m,4)],['median',fmt(q(50),4)],['mode',modes.map(x=>x[0]).join('/')],
      ['min',fmt(s[0],2)],['max',fmt(s[s.length-1],2)],['Q1',fmt(q(25),3)],['Q3',fmt(q(75),3)],['IQR',fmt(q(75)-q(25),3)],
      ['variance σ²',fmt(v,4)],['std σ',fmt(sv,4)],['variance (n−1)',fmt(s1**2,4)],['std (n−1)',fmt(s1,4)]].map(([k,val],i)=>F(k,val,i===10?'hot':'')).join('');
    say('stWhy',`His dragons run: μ = 7, squared deviations 4, 25, 4, 9, 25, 0 → <b>variance ≈ 8.99</b> and <b>standard deviation ≈ 2.983</b>, read out as "with a value of 2.983 the values are differing from the mean". Divide that sum by n−1 instead and you get the sample variance — the two formulas he writes side by side on the slide.`);
    $('bxDiag').innerHTML=(()=>{const W=460,H=150,lo=s[0],hi=s[s.length-1],X=v=>30+(W-60)*((v-lo)/((hi-lo)||1)),y=70;
      return `<line x1="${X(lo)}" y1="${y}" x2="${X(q(25))}" y2="${y}" stroke="var(--muted)" stroke-width="2"/>
      <line x1="${X(q(75))}" y1="${y}" x2="${X(hi)}" y2="${y}" stroke="var(--muted)" stroke-width="2"/>
      <rect x="${X(q(25))}" y="${y-26}" width="${Math.max(4,X(q(75))-X(q(25)))}" height="52" fill="var(--accent-soft)" stroke="var(--a)" stroke-width="2" rx="6"/>
      <line x1="${X(q(50))}" y1="${y-26}" x2="${X(q(50))}" y2="${y+26}" stroke="var(--b)" stroke-width="3"/>
      ${[[lo,'min'],[q(25),'Q1'],[q(50),'Q2'],[q(75),'Q3'],[hi,'max']].map(([v,l])=>`<circle cx="${X(v)}" cy="${y}" r="4" fill="var(--a)"/><text x="${X(v)}" y="${y+44}" class="axlab" text-anchor="middle">${l}=${fmt(v,1)}</text>`).join('')}`})() ;
  }
  run();
  /* entropy */
  let cls=2;
  chips('enCls',[['2','2 classes'],['3','3 classes'],['4','4 classes']],String(cls),v=>{cls=+v;press('enCls',v);en()});
  $('enYes').oninput=en;
  function en(){
    const yes=+$('enYes').value; $('enYesV').textContent=yes;
    const total=14, rest=total-yes;
    const counts=cls===2?[yes,rest]:cls===3?[yes,Math.floor(rest/2),Math.ceil(rest/2)]:[yes,Math.floor(rest/3),Math.floor(rest/3),rest-2*Math.floor(rest/3)];
    const H=entropy(counts), G=gini(counts);
    const W=460,Ht=180, X=p=>20+p*(W-40), Y=h=>Ht-24-(h/Math.log2(cls))*(Ht-50);
    const curve=Array.from({length:100},(_,i)=>{const p=i/99;return [X(p),Y(entropy(cls===2?[p,1-p]:[p,(1-p)/2,(1-p)/2]))]});
    $('enSvg').innerHTML=`<path d="${curve.map((pt,i)=>`${i?'L':'M'}${pt[0].toFixed(1)} ${pt[1].toFixed(1)}`).join(' ')}" fill="none" stroke="var(--a)" stroke-width="3"/>
      <line x1="20" y1="${Y(0)}" x2="${W-20}" y2="${Y(0)}" class="axline"/><line x1="20" y1="${Y(1)}" x2="${W-20}" y2="${Y(1)}" class="axline" opacity=".4"/>
      <line x1="${X(yes/total)}" y1="10" x2="${X(yes/total)}" y2="${Ht-24}" stroke="var(--b)" stroke-dasharray="4 4"/>
      <circle cx="${X(yes/total)}" cy="${Y(H)}" r="7" fill="var(--fill)" stroke="var(--hl-edge)" stroke-width="2"/>
      <text x="24" y="${Y(1)+14}" class="axlab">max impurity ${cls===2?'(50/50)':cls===3?'(33/33/33)':'(4 equal classes)'}</text>
      <text x="${X(yes/total)+8}" y="20" class="axlab">H = ${fmt(H,3)}</text><text x="20" y="${Ht-6}" class="axlab">P(yes) →</text>`;
    $('enFacts').innerHTML=F('counts',counts.join(' / '))+F('entropy H(S)',fmt(H,4),'hot')+F('gini',fmt(G,4))+
      F('max possible',fmt(Math.log2(cls),4))+F('purity',pct(1-H/Math.log2(cls),1))+F('his root node','0.940 for 9 / 5');
    say('enWhy',cls===2&&yes===9?`His exact arithmetic: <code>-(9/14)·log₂(9/14) - (5/14)·log₂(5/14) = 0.940</code>. Read as "the data has 0.940 of bad data — much more impurity". Push the slider to 7 and 7 (maximum confusion) or to 14 and 0 (pure, entropy 0, no split needed).`
      :`Entropy is highest when the classes are evenly mixed (${fmt(Math.log2(cls),3)} bits at 50/50 for two, his "51% / 49% means more entropy") and exactly 0 when one class owns the node. A tree split is judged purely by how far it drags this number down.`);
  }
  en();
})();

/* ============================== 12 · MODEL PICKER ============================== */
(()=>{
  const Q=[['target','What does the output column look like?',[['continuous','a number: price, age, expenditure'],['categorical','a label: yes/no, 0/1, class'],['none','there is no output column']]],
    ['linear','If there is a target: is the relation roughly a straight line?',[['yes','it moves in proportion'],['no','curved / messy'],['idk','no idea yet']]],
    ['size','How much data, and how many features?',[['small','a few hundred rows'],['large','lots of rows'],['highdim','very many features']]],
    ['explain','Do you have to explain the decision to somebody?',[['yes','a human must agree'],['no','the number is enough']]]];
  const ans={};
  function render(){
    $('msQs').innerHTML=Q.map(([id,q,opts],i)=>`<div class="ctl" style="margin-bottom:12px;${i>0&&!ans[Q[i-1][0]]?'opacity:.35;pointer-events:none':''}">
      <span class="lbl">${i+1} · ${q}</span><div class="chips" data-q="${id}">${opts.map(([v,l])=>`<button class="chip" data-v="${v}" aria-pressed="${ans[id]===v}">${l}</button>`).join('')}</div></div>`).join('');
    [...$('msQs').querySelectorAll('.chips')].forEach(c=>c.onclick=e=>{const b=e.target.closest('.chip');if(!b)return;
      ans[c.dataset.q]=b.dataset.v; render(); pick();});
  }
  function pick(){
    if(!ans.target){$('msOut').innerHTML='';return}
    let out=[],why=[];
    if(ans.target==='continuous'){out=['LinearRegression','Polynomial features + LinearRegression','DecisionTreeRegressor','RandomForestRegressor','SVR'];
      why.push('target is a continuous quantity → regression');
      if(ans.linear==='yes')why.push('linear relation → plain linear regression is the right first model, and it is the one you can explain');
      if(ans.linear==='no')why.push('not linear → polynomial features, or stop pretending and use a tree');
      if(ans.explain==='yes')why.push('needs explaining → linear regression or a shallow tree');}
    else if(ans.target==='categorical'){out=['LogisticRegression','KNeighborsClassifier','DecisionTreeClassifier','RandomForestClassifier','GaussianNB','SVC'];
      why.push('output is a category → classification');
      if(ans.size==='highdim')why.push('many features and text-like data → Naive Bayes or a linear SVM, they are built for it');
      if(ans.size==='small')why.push('only a few hundred rows → KNN or logistic regression; a deep tree will memorise them');
      if(ans.explain==='yes')why.push('must justify a decision → decision tree, or logistic regression with its coefficients');
      why.push('if the classes are unbalanced, ignore accuracy and watch precision / recall (station 24)');}
    else{out=['KMeans','AgglomerativeClustering','DBSCAN-like mean shift','Apriori','PCA'];
      why.push('no output column at all → unsupervised: you are inventing the target');
      if(ans.linear==='no')why.push('you cannot know the shape, so hierarchical clustering or the elbow method will show it to you');
      why.push('and his bonus move: cluster first, then classify on the clusters you made');}
    $('msOut').innerHTML=out.map((m,i)=>F(i?'also try':'→ your model',m,i?'': 'good')).join('');
    say('msWhy',why.map(w=>'• '+w).join('<br>')+'<br><span class="pill">his last instruction: compare a few models, do not marry the first one that trained.</span>');
  }
  render();
})();


/* ============================== 13 · LINEAR REGRESSION ============================== */
(()=>{
  let pts=[], running=false;
  const rndPts=()=>{const a=2+Math.random()*2, b=Math.random()*6;
    pts=Array.from({length:14},(_,i)=>{const x=1+i*0.9;return [x, +(a*x+b+(Math.random()-0.5)*8).toFixed(2)]})};
  rndPts();
  chips('lrFam',[['simple','Simple linear'],['poly','Polynomial'],['svr','Support vector regression'],['dtr','Decision tree regression'],['rfr','Random forest regression'],['log','Logistic']],
    'simple',v=>{
      const W={simple:'The one we focus on: one straight line, y = B₀ + B₁x, fitted by making the mean squared error as small as possible.',
        poly:'\"Transforms the features into a polynomial feature of a given degree and then performs linear regression on it\" — that is how a curve gets fitted by a straight-line machine.',
        svr:'\"Works with maximum margin such that it fits within those margins\" — basically the classification SVM with a tube instead of a line.',
        dtr:'A tree can regress. Here the ID3 algorithm (iterative dichotomiser 3) picks the splitting node \"by reducing the standard deviation\" instead of by entropy.',
        rfr:'\"An ensemble of predictions of several decision tree regressions\" — average many trees, get a smoother and steadier answer.',
        log:'Listed under regression but it predicts a probability for a category — station 15 is where it lives.'};
      say('lrFamWhy','<b>'+({'simple':'Simple linear regression','poly':'Polynomial regression','svr':'SVR','dtr':'Decision tree regression','rfr':'Random forest regression','log':'Logistic regression'})[v]+':</b> '+W[v]);
    });
  const b0=$('lrB0'), b1=$('lrB1');
  function mseOf(B0,B1){return mean(pts.map(([x,y])=>(B0+B1*x-y)**2))}
  function draw(){
    const B0=+b0.value, B1=+b1.value, W=460,H=260;
    const xs=pts.map(p=>p[0]), ys=pts.map(p=>p[1]);
    const bx=[Math.min(...xs)-1,Math.max(...xs)+1], by=[Math.min(...ys,-2)-2,Math.max(...ys,10)+2];
    const sx=v=>20+(W-40)*((v-bx[0])/(bx[1]-bx[0])), sy=v=>H-26-(H-50)*((v-by[0])/(by[1]-by[0]));
    let g=`<line x1="20" y1="${sy(0)}" x2="${W-20}" y2="${sy(0)}" class="axline"/><line x1="${sx(0)}" y1="14" x2="${sx(0)}" y2="${H-26}" class="axline"/>`;
    pts.forEach(([x,y])=>{const yh=B0+B1*x;
      g+=`<line x1="${sx(x)}" y1="${sy(y)}" x2="${sx(x)}" y2="${sy(yh)}" stroke="var(--bad)" stroke-width="1.5" opacity=".7"/>`;
      g+=`<rect x="${Math.min(sx(x),sx(x))-2}" y="${Math.min(sy(y),sy(yh))}" width="4" height="${Math.abs(sy(y)-sy(yh))}" fill="var(--bad)" opacity=".18"/>`;
      g+=`<circle cx="${sx(x)}" cy="${sy(y)}" r="5" fill="var(--a)"/>`});
    g+=`<line x1="${sx(bx[0])}" y1="${sy(B0+B1*bx[0])}" x2="${sx(bx[1])}" y2="${sy(B0+B1*bx[1])}" stroke="var(--fill)" stroke-width="3.5"/>`;
    $('lrSvg').innerHTML=g;
    const mse=mseOf(B0,B1), bb=best();
    $('lrFacts').innerHTML=F('B₀',fmt(B0,2))+F('B₁',fmt(B1,3))+F('MSE',fmt(mse,3),mse<bb.mse*1.05?'good':'bad')+
      F('best MSE',fmt(bb.mse,3))+F('R²',fmt(1-mse/mean(pts.map(([x,y])=>(y-mean(pts.map(p=>p[1])))**2)),3))+
      F('RMSE',fmt(Math.sqrt(mse),3));
    say('lrWhy',mse>bb.mse*1.3?`Your line misses with MSE ${fmt(mse,2)}. The best possible for these points is ${fmt(bb.mse,2)} at B₀=${fmt(bb.b0,2)}, B₁=${fmt(bb.b1,3)}. Drag, or press <b>Run gradient descent</b> and watch the two numbers walk themselves down — that is training.`
      :`You are essentially at the minimum (B₀ ${fmt(bb.b0,2)}, B₁ ${fmt(bb.b1,3)}). Every squared residual is now as small as the line can make them together. This is the point linear regression is trying to reach.`);
  }
  function best(){
    const n=pts.length, mx=mean(pts.map(p=>p[0])), my=mean(pts.map(p=>p[1]));
    let num=0,den=0; pts.forEach(([x,y])=>{num+=(x-mx)*(y-my);den+=(x-mx)**2});
    const b1=num/den, b0=my-b1*mx; return {b0,b1,mse:mseOf(b0,b1)};
  }
  b0.oninput=b1.oninput=draw;
  $('lrBest').onclick=()=>{const {b0,b1}=best(); b0v(); function b0v(){}
    $('lrB0').value=b0.toFixed(2); $('lrB1').value=b1.toFixed(3); draw()};
  $('lrData').onclick=()=>{rndPts();draw()};
  $('lrGo').onclick=()=>{
    if(running)return; running=true;
    let B0=+$('lrB0').value, B1=+$('lrB1').value, lr=0.006, i=0;
    const n=pts.length;
    const tick=()=>{
      let g0=0,g1=0;
      pts.forEach(([x,y])=>{const e=B0+B1*x-y; g0+=2*e/n; g1+=2*e*x/n});
      B0-=lr*g0; B1-=lr*g1; i++;
      $('lrB0').value=B0.toFixed(3); $('lrB1').value=B1.toFixed(4); draw();
      if(i<220)requestAnimationFrame(tick); else running=false;
    };
    requestAnimationFrame(tick);
  };
  $('lrPit').innerHTML=`<div class="tbl"><div class="trow">${['line fits','curve missed','outlier pulls'].map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>
    <div class="trow"><div class="tc g">✓</div><div class="tc r">✗</div><div class="tc r">✗</div></div></div>
    <p class="hint">Three pictures in one row: linear regression is the honest baseline, but it is the model that breaks loudest when the shape is wrong or one point is crazy — because the error it minimises is <em>squared</em>, a single far point outweighs ten honest ones.</p>`;
  draw();
})();

/* ============================== 14 · LEAST SQUARES ============================== */
(()=>{
  const D=[[1,1],[2,3],[3,4],[4,6],[5,8],[6,9],[7,11]];
  let view='squares';
  chips('lsView',[['squares','squared residuals'],['lines','residuals only'],['tot','show the totals']],view,v=>{view=v;press('lsView',v);run()});
  $('lsX').oninput=run;
  function run(){
    const mx=mean(D.map(p=>p[0])), my=mean(D.map(p=>p[1]));
    let num=0,den=0; D.forEach(([x,y])=>{num+=(x-mx)*(y-my);den+=(x-mx)**2});
    const m=num/den, c=my-m*mx;
    const xq=+$('lsX').value; $('lsXv').textContent='$'+xq;
    const W=470,H=270, bx=[0,12.5], by=[0,14];
    const sx=v=>30+(W-56)*(v/bx[1]), sy=v=>H-30-(H-56)*(v/by[1]);
    let g=`<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(12)}" y2="${sy(0)}" stroke="var(--ink)" opacity=".45"/>
      <line x1="${sx(0)}" y1="14" x2="${sx(0)}" y2="${sy(0)}" stroke="var(--ink)" opacity=".45"/>
      ${Array.from({length:13},(_,i)=>`<text x="${sx(i)}" y="${sy(0)+14}" class="axlab" text-anchor="middle">${i}</text>`).join('')}
      ${Array.from({length:8},(_,i)=>`<text x="${sx(0)-8}" y="${sy(i*2)+4}" class="axlab" text-anchor="end">${i*2}</text>`).join('')}`;
    D.forEach(([x,y])=>{const yh=m*x+c, side=Math.abs(x-yh);
      if(view!=='lines')g+=`<rect x="${Math.min(sx(x),sx(xh(x)))}" y="${Math.min(sy(y),sy(yh))}" width="${Math.abs(sx(x)-sx(yh))}" height="${Math.abs(sy(y)-sy(yh))}" fill="var(--b)" opacity=".${view==='tot'?'22':'3'}" stroke="var(--b)" stroke-width="1"/>`;
      else g+=`<line x1="${sx(x)}" y1="${sy(y)}" x2="${sx(x)}" y2="${sy(yh)}" stroke="var(--b)" stroke-width="2"/>`;
      g+=`<circle cx="${sx(x)}" cy="${sy(y)}" r="5.5" fill="var(--a)"/>`});
    function xh(v){return v}
    g+=`<line x1="${sx(0)}" y1="${sy(c)}" x2="${sx(12)}" y2="${sy(m*12+c)}" stroke="var(--c)" stroke-width="3.5"/>`;
    g+=`<circle cx="${sx(0)}" cy="${sy(c)}" r="6" fill="var(--fill)" stroke="var(--hl-edge)" stroke-width="2"/>`;
    g+=`<line x1="${sx(xq)}" y1="${sy(0)}" x2="${sx(xq)}" y2="${sy(m*xq+c)}" stroke="var(--fill)" stroke-dasharray="5 4" stroke-width="2"/>
      <circle cx="${sx(xq)}" cy="${sy(m*xq+c)}" r="7" fill="var(--fill)" stroke="var(--hl-edge)" stroke-width="2"/>
      <text x="${sx(xq)+8}" y="${sy(m*xq+c)-8}" class="axlab" fill="var(--b)" font-size="13">${fmt(m*xq+c,2)} t-shirts</text>
      <text x="${sx(1)}" y="20" class="axlab">price (x) → dollars</text><text x="10" y="${sy(13)}" class="axlab">units sold (y)</text>`;
    $('lsSvg').innerHTML=g;
    const sse=D.reduce((s,[x,y])=>s+(y-(m*x+c))**2,0), sst=D.reduce((s,[x,y])=>s+(y-my)**2,0);
    $('lsFacts').innerHTML=F('slope m',fmt(m,4),'hot')+F('intercept c',fmt(c,4),'hot')+F('equation',`y = ${fmt(m,2)}x + ${fmt(c,2)}`)+
      F('at $'+xq,fmt(m*xq+c,2)+' → '+Math.round(m*xq+c)+' t-shirts','good')+F('SSE',fmt(sse,3))+F('R²',fmt(1-sse/sst,4));
    say('lsWhy',`His shop example, one week of sales: substitute the values and \"you should get a slope of approximately 1.5\" and \"a y intercept value of around 0.3\". Then \"if you substitute x as 8, you should get an answer of around <b>12.45</b>, which is basically 13 t-shirts\". ${view==='squares'?'The squares you see are the residuals <em>squared</em> — literally where the name comes from. Slide to "residuals only" to see the signed errors.':'Residual = the error your line made on one point. Least squares minimises the sum of their squares.'}`);
    $('lsRecipe').innerHTML=[['1','calculate the slope m','m = Σ(x−x̄)(y−ȳ) / Σ(x−x̄)²',fmt(m,4)],
      ['2','compute the y-intercept','c = ȳ − m·x̄',fmt(c,4)],
      ['3','put them in the equation','y = mx + c',`at x=${xq}: ${fmt(m*xq+c,2)}`]]
      .map(([a,b,d,e])=>`<div class="trow"><div class="tc hd">${a}</div><div class="tc" style="min-width:180px">${b}</div><div class="tc" style="min-width:220px">${d}</div><div class="tc on">${e}</div></div>`).join('');
    $('lsFacts2').innerHTML=F('SSE (sum of squares)',fmt(sse,3))+F('SST (total wobble)',fmt(sst,3))+F('R²',fmt(1-sse/sst,4),'good')+
      F('his RMSE on the real set','72')+F('his R² note','0.6, "quite close to one"')+F('negative R²','model is worse than the mean','bad');
  }
  run();
})();

/* ============================== 15 · LOGISTIC REGRESSION ============================== */
(()=>{
  let z=8;
  $('lgZ').oninput=run; $('lgTh').oninput=run; $('lgP').oninput=run;
  function run(){
    z=+$('lgZ').value; const th=+$('lgTh').value/100; $('lgThV').textContent=th.toFixed(2);
    const W=460,H=250, bx=[-6,6], by=[-1.6,2.6];
    const sx=v=>34+(W-56)*((v-bx[0])/(bx[1]-bx[0])), sy=v=>H-28-(H-52)*((v-by[0])/(by[1]-by[0]));
    const lin=x=>0.5+ (x/6)*1.0, sig=x=>1/(1+Math.exp(-x*(z/6)));
    let g=`<line x1="${sx(0)}" y1="${sy(0)}" x2="${sx(0)}" y2="12" class="axline"/>
      <line x1="34" y1="${sy(0)}" x2="${W-22}" y2="${sy(0)}" class="axline"/>
      <line x1="34" y1="${sy(1)}" x2="${W-22}" y2="${sy(1)}" stroke="var(--muted)" stroke-dasharray="4 4"/>
      <text x="36" y="${sy(1)-4}" class="axlab">y = 1</text><text x="36" y="${sy(0)-4}" class="axlab">y = 0</text>
      <path d="${Array.from({length:100},(_,i)=>{const x=bx[0]+12*i/99;return `${i?'L':'M'}${sx(x)} ${sy(lin(x))}`}).join(' ')}" stroke="var(--bad)" stroke-width="2.5" fill="none" stroke-dasharray="7 5"/>
      <path d="${Array.from({length:140},(_,i)=>{const x=bx[0]+12*i/139;return `${i?'L':'M'}${sx(x)} ${sy(sig(x))}`}).join(' ')}" stroke="var(--a)" stroke-width="3.5" fill="none"/>
      <line x1="${sx(0)}" y1="${sy(th)}" x2="${W-22}" y2="${sy(th)}" stroke="var(--fill)" stroke-width="2"/>
      <text x="${sx(0)+6}" y="${sy(th)-6}" class="axlab" fill="var(--b)">threshold ${th.toFixed(2)}</text>
      <text x="36" y="18" class="axlab">dashed = the linear answer (goes past 1 and below 0)</text>
      <text x="36" y="32" class="axlab">solid = clipped and bent into the sigmoid</text>`;
    $('lgSvg').innerHTML=g;
    const p1=sig(2), p0=sig(-2);
    $('lgFacts').innerHTML=F('z scale',z)+F('P at x=+2',fmt(p1,4))+F('P at x=−2',fmt(p0,4))+
      F('predicted class at +2',p1>th?'1':'0',p1>th?'good':'bad')+F('at −2',p0>th?'1':'0',p0>th?'bad':'good')+
      F('range of y','only 0 and 1','hot');
    say('lgWhy',`In linear regression y can be anything, so the fitted line escapes the two allowed answers — \"the linear line has to be clipped\". Divide by (1−y) and the range becomes 0 to ∞ (he works both ends: y=0 gives 0/1=0, y=1 gives 1/0=∞); take the log of that and you have the logistic equation. Passing it through the log function is what produces the S curve on screen, and \"logistic regression predicts the probability of the event using the log function\".`);
    const p=+$('lgP').value/100; $('lgPv').textContent=p.toFixed(2);
    const yes=p>th;
    $('lgVerdict').innerHTML=`<div style="display:flex;gap:18px;align-items:center;flex-wrap:wrap;justify-content:center;width:100%">
      <div class="tc" style="font-size:1.4rem;min-width:80px">${p.toFixed(2)}</div>
      <div class="arrow">${yes?'>':'<'} ${th.toFixed(2)}</div>
      <div class="tc ${yes?'g':'r'}" style="font-size:1.2rem;min-width:130px">predict ${yes?'1 · survived':'0 · did not'}</div>
      <div class="tc off" style="min-width:150px">odds = ${fmt(p/(1-p||1e-9),3)} : 1</div></div>
      <p class="hint">Odds are the thing the model actually fits: log(p/(1−p)) is the straight-line part. ${yes?'Raise the threshold above '+p.toFixed(2)+' and this flips to 0 — that single dial is how you trade precision against recall.':'Below the cutoff, so class 0. Move the threshold slider down and watch it flip.'}</p>`;
  }
  run();
  /* Titanic pipeline */
  const ST=[
    ['load','Load','pd.read_csv("titanic.csv") → <b>891 rows</b>, 12 columns: PassengerId, Survived, Pclass, Name, Sex, Age, SibSp, Parch, Ticket, Fare, Cabin, Embarked. <code>head(10)</code> and the frame is on screen.'],
    ['look','Explore','<code>sns.countplot(x="Survived")</code>: about <b>550 did not survive, 342 did</b>. Pclass has values 1, 2, 3. Embarked is S / C / Q (Southampton, Cherbourg, Queenstown). SibSp and Parch are sibling/spouse and parent/child counts.'],
    ['corr','Correlate','A seaborn heatmap of <code>df.corr()</code>. Anything bright on the diagonal is the column with itself; anything else bright is a duplicate feature. Fare vs Pclass is strongly negative, which is expected.'],
    ['null','Find the holes','<code>data.isnull()</code> paints the frame black where values are missing. <code>data.isnull().sum()</code> gives <b>Age ≈ 177 (about 20 %)</b>, Cabin the worst by far, Embarked only 2.'],
    ['fix','Repair','Drop Cabin (<code>drop(["Cabin"], axis=1, inplace=True)</code>), fill Age with the mean <em>per Pclass</em> — he notes class 1 and 2 passengers were older than class 3.'],
    ['encode','Encode','<code>pd.get_dummies(col, drop_first=True)</code> for Sex, Pclass and Embarked, then <code>pd.concat</code> the new columns and drop the originals. Male = 1, female = 0 — one column, no dummy trap.'],
    ['split','Split','<code>train_test_split(X, y, test_size=0.3)</code> → \"your data set is divided in 0.3, that is in 70:30\".'],
    ['fit','Fit & predict','<code>LogisticRegression()</code> → <code>.fit(X_train, y_train)</code> → <code>.predict(X_test)</code>. Then classification_report, confusion_matrix, accuracy_score.'],
  ];
  let sti=0;
  chips('tfStages',ST.map(([id,l])=>[id,l]),'0',v=>{sti=+v;render()});
  function render(){
    $('tfStage').innerHTML=`<div style="width:100%">
      <div class="chips" style="margin-bottom:10px">${ST.map(([id,l],i)=>`<button class="chip" style="${i===sti?'border-color:var(--accent);background:var(--accent-soft)':'opacity:.55'}">${i+1}. ${l}</button>`).join('')}</div>
      <p class="note">${ST[sti][2]}</p></div>`;
    press('tfStages',String(sti));
    say('tfWhy',sti===7?'Everything after this point is reading the scorecard — the matrix and the accuracy are under this bench.':sti===3?'This is the step people skip, and it is the one he spends the most time on.':'Cleaning is \"wrangling basically means cleaning your data\" — his definition, and the largest block of work in the chapter.');
  }
  sti=0; render();
  /* confusion matrix */
  let cm={tn:105,fp:21,fn:25,tp:63};
  function drawCm(){
    const tot=cm.tn+cm.fp+cm.fn+cm.tp, acc=(cm.tn+cm.tp)/tot;
    $('tfCm').innerHTML=`<div class="tbl">
      <div class="trow"><div class="tc hd"></div><div class="tc hd">predicted 0</div><div class="tc hd">predicted 1</div></div>
      <div class="trow"><div class="tc hd">actual 0</div><div class="tc g" style="font-size:1.1rem">${cm.tn}</div><div class="tc r" style="font-size:1.1rem">${cm.fp}</div></div>
      <div class="trow"><div class="tc hd">actual 1</div><div class="tc r" style="font-size:1.1rem">${cm.fn}</div><div class="tc g" style="font-size:1.1rem">${cm.tp}</div></div></div>`;
    $('tfFacts').innerHTML=F('accuracy',pct(acc,2),'hot')+F('his arithmetic','(105 + 63) / 214 = 78')+F('precision 0',fmt(cm.tn/(cm.tn+cm.fn),3))+
      F('precision 1',fmt(cm.tp/(cm.tp+cm.fp),3))+F('recall 1',fmt(cm.tp/(cm.tp+cm.fn),3))+F('total',tot);
  }
  drawCm();
  /* null bars */
  (()=>{
    const N=[['Age',177],['Cabin',687],['Embarked',2],['Pclass',0],['Survived',0],['Fare',0]];
    const W=460,H=220, mx=700;
    $('tfNull').innerHTML=`${N.map(([l,v],i)=>`<rect x="${40}" y="${18+i*32}" width="${(W-90)*v/mx}" height="20" fill="var(--bad)" opacity="${v?'.85':'.2'}"/>
      <text x="36" y="${32+i*32}" class="axlab" text-anchor="end">${l}</text><text x="${46+(W-90)*v/mx}" y="${32+i*32}" class="axlab">${v}</text>`).join('')}
      <line x1="40" y1="8" x2="40" y2="${H-14}" class="axline"/><text x="44" y="${H-4}" class="axlab">missing values out of 891 rows</text>`;
  })();
})();

/* ============================== 16 · DECISION TREE ============================== */
(()=>{
  const F_={
    outlook:{sunny:[[2,3]],overcast:[[4,0]],rainy:[[3,2]]},
    humidity:{high:[[3,4]],normal:[[6,1]]},
    windy:{weak:[[6,3]],strong:[[3,2]]},
    temperature:{cool:[[1,1]],mild:[[4,5]],hot:[[4,3]]}};
  let crit='entropy', rootYes=9;
  chips('dtCrit',[['entropy','entropy (information gain)'],['gini','gini impurity']],crit,v=>{crit=v;press('dtCrit',v);run()});
  $('dtYes').oninput=e=>{rootYes=+e.target.value;run()};
  const measure=counts=>crit==='entropy'?entropy(counts):gini(counts);
  function gain(f){
    const groups=Object.values(F_[f]).flat(), tot=sum(groups.map(sum));
    const weighted=sum(groups.map(c=>(sum(c)/tot)*measure(c)));
    return measure([rootYes,tot-rootYes])-weighted;
  }
  let chosen=[];
  function run(){
    const tot=14;
    const rows=Object.keys(F_).map(f=>[f,gain(f)]).sort((a,b)=>b[1]-a[1]);
    const H0=measure([rootYes,tot-rootYes]);
    $('dtGainTable').innerHTML=`<div class="tbl"><div class="trow">${['feature','counts','weighted impurity','information gain','pick?'].map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>
      ${rows.map(([f,g],i)=>{const c=Object.values(F_[f]).flat();
        return `<div class="trow"><div class="tc">${f}</div><div class="tc" style="min-width:150px">${c.map(x=>x.join(':')).join('  ')}</div>
        <div class="tc">${fmt(H0-g,4)}</div><div class="tc ${i===0&&!chosen.includes(f)?'tot':''}" style="font-size:1.05rem">${fmt(g,4)}</div>
        <div class="tc ${i===0?'g':''}">${i===0?'highest → best split':''}</div></div>`}).join('')}</div>
      <p class="hint">${crit==='entropy'?'H(S) = −Σ p log₂ p. With 9 yes and 5 no the root is <b>0.940</b> — his number exactly.':'Gini = 1 − Σ p². Same job, no logarithm; scikit-learn uses it as the default for a reason (speed).'} At the root you currently hold <b>${rootYes} yes / ${tot-rootYes} no</b> → impurity ${fmt(H0,4)}.</p>`;
    $('dtTree').innerHTML=renderTree();
    $('dtFacts').innerHTML=F('root impurity',fmt(H0,4))+F('best gain',fmt(rows[0][1],4),'good')+
      F('feature',rows[0][0])+F('splits made',chosen.length)+F('leaves',chosen.length?2**chosen.length:1)+
      F('his four gains','0.247 / 0.151 / 0.048 / 0.029');
    say('dtWhy',chosen.length<2?`Click the row with the biggest gain to spend a split. ${rootYes===9?'With his exact numbers outlook wins with 0.247, then humidity 0.151, then windy 0.048, then temperature 0.029.':'You changed the class mix, so the gains moved — that is the whole point: the tree is a function of the data, not a fixed shape.'}`
      :`Depth ${chosen.length}: the tree has made its calls. Notice overcast went straight to a leaf with entropy 0 — \"if you get a pure subset then no need to split\". Add more splits and training accuracy climbs while test accuracy turns around: that is the next panel.`);
    return rows;
  }
  $('dtGainTable').onclick=e=>{const r=e.target.closest('.trow'); if(!r||!r.children[1])return;
    const f=r.children[0].textContent; if(!chosen.includes(f)&&chosen.length<3)chosen.push(f); run();};
  function renderTree(){
    const lvl=[['root'],chosen[0]?[chosen[0]]:[],chosen[1]?[chosen[1]]:[],chosen[2]?[chosen[2]]:[]];
    const W=460,H=190;
    let g='';
    g+=`<rect x="170" y="12" width="120" height="34" rx="9" fill="var(--accent-soft)" stroke="var(--a)" stroke-width="2"/>
        <text x="230" y="33" text-anchor="middle" class="axlab" font-size="12">root ${fmt(measure([rootYes,14-rootYes]),3)}</text>`;
    chosen.forEach((f,i)=>{const y=60+i*44;
      g+=`<line x1="230" y1="46" x2="${80+i*120}" y2="${y}" stroke="var(--line)"/>
        <rect x="${40+i*120}" y="${y}" width="150" height="34" rx="9" fill="var(--card)" stroke="var(--b)" stroke-width="2"/>
        <text x="${115+i*120}" y="${y+21}" text-anchor="middle" class="axlab" font-size="12">split: ${f} (gain ${fmt(gain(f),3)})</text>`;
      if(i===chosen.length-1){[0,1].forEach(k=>{const yy=y+44;
        g+=`<rect x="${30+i*120+k*70}" y="${yy}" width="62" height="26" rx="7" fill="${k?'color-mix(in srgb,var(--bad) 25%,var(--card))':'color-mix(in srgb,var(--good) 25%,var(--card))'}" stroke="var(--muted)"/>
          <text x="${61+i*120+k*70}" y="${yy+17}" text-anchor="middle" class="axlab" font-size="11">${k?'no':'yes'}</text>`})}});
    return `<svg viewBox="0 0 ${W} ${H+60}" role="img" aria-label="a growing decision tree">${g}</svg>`;
  }
  /* overfit curve */
  function over(){
    const d=+$('dtDepth').value, leaf=+$('dtLeaf').value;
    $('dtDepthV').textContent=d; $('dtLeafV').textContent=leaf;
    const tr=a=>a.map(k=>Math.max(0.32,1-0.07*k-Math.log(1+k)*0.06+ (leaf>18?0.02:0)));
    const te=[...Array(12)].map((_,k)=>{const base=0.42+0.26*Math.log(1+k)-0.012*k*k; return clamp(0.985-Math.max(0,(k-d)*(k>d?0.035:0))- (leaf<3?0.05:0) - (k<1?0.25:0),0.3,0.99)});
    const W=460,H=210, X=k=>30+k*(W-52)/11, Y=v=>H-26-v*(H-50);
    $('dtOver').innerHTML=`<line x1="30" y1="${Y(0)}" x2="${W-16}" y2="${Y(0)}" class="axline"/>
      <path d="${tr.map((v,k)=>`${k?'L':'M'}${X(k)} ${Y(v)}`).join(' ')}" fill="none" stroke="var(--a)" stroke-width="3"/>
      <path d="${te.map((v,k)=>`${k?'L':'M'}${X(k)} ${Y(v)}`).join(' ')}" fill="none" stroke="var(--bad)" stroke-width="3" stroke-dasharray="6 4"/>
      <line x1="${X(d)}" y1="8" x2="${X(d)}" y2="${Y(0)}" stroke="var(--fill)" stroke-width="2"/>
      <circle cx="${X(d)}" cy="${Y(tr[d])}" r="5" fill="var(--a)"/><circle cx="${X(d)}" cy="${Y(te[d])}" r="5" fill="var(--bad)"/>
      <text x="34" y="16" class="axlab">solid = training accuracy · dashed = test accuracy · x = max_depth</text>
      <text x="${X(d)+6}" y="${Y(Math.min(tr[d],te[d]))-10}" class="axlab" fill="var(--b)">depth ${d}: train ${pct(tr[d],0)} / test ${pct(te[d],0)}</text>`;
    say('dtOverWhy',d<=2?`At depth ${d} the tree is a rule a person can actually repeat — and training and test accuracy sit together. His job-offer example is exactly this shape: salary ≥ 50,000 → consider; commute ≤ 1 hour → accept; otherwise decline.`
      :d<=6?`Depth ${d}: training keeps improving while test has stopped caring. The gap is where memorising starts.`
      :`Depth ${d} with a minimum of ${leaf} samples per leaf — the tree now splits until every training row is alone, which is \"the case of overfitting\" he warns about, and the reason <b>pruning</b> exists. Cut max_depth down or raise min_samples_leaf and the dashed line comes back up.`);
  }
  $('dtDepth').oninput=over; $('dtLeaf').oninput=over; over();
  run();
})();

/* ============================== 17 · RANDOM FOREST ============================== */
(()=>{
  let n=12, nf=2, crit='entropy';
  $('rfN').oninput=run; $('rfF').oninput=run;
  chips('rfCrit',[['entropy','entropy'],['gini','gini']],crit,v=>{crit=v;press('rfCrit',v);run()});
  function run(){
    n=+$('rfN').value; nf=+$('rfF').value;
    $('rfNv').textContent=n+' trees'; $('rfFv').textContent=nf+' of 4 features';
    const acc=0.845+0.145*(1-Math.exp(-n/6))*(crit==='gini'?1.008:1);
    const trees=Array.from({length:Math.min(n,12)},(_,i)=>{
      const yes=Math.round(9+ (Math.sin(i*2.3)*2.2));
      return {i,rows:Array.from({length:14},(_,k)=>((k*7+i*13)%14)),yes,no:14-yes,call:Math.sin(i*1.7+0.4)>-0.25?'play':'no'}});
    const plays=trees.filter(t=>t.call==='play').length;
    $('rfStage').innerHTML=`<div style="width:100%">
      <span class="lbl">bootstrap samples — the same row can appear twice (${n} trees drawn)</span>
      <div class="tbl" style="margin:6px 0">${trees.slice(0,Math.min(n,10)).map(t=>`<div class="trow">${t.rows.map(r=>`<div class="tc ${r<4?'on':''}" style="min-width:26px;font-size:.72rem">${r}</div>`).join('')}</div>`).join('')}</div>
      <span class="lbl">each tree looks at only ${nf} of the 4 features (${nf===2?'√4 = 2 — his classification default':'not the default, but you can force it'})</span>
      <div class="chips" style="margin-top:8px">${trees.map(t=>`<button class="chip ${t.call==='play'?'':'alt'}" style="pointer-events:none">${t.i+1}: ${t.call}</button>`).join('')}</div>
      <p class="hint" style="margin-top:10px">Vote: <b>${plays} say play</b>, <b>${trees.length-plays} say no</b> → the forest answers <b>${plays>trees.length/2?'play':'no'}</b>.
      ${n>1?'One tree would have guessed on its own noise; the majority is the ensemble.':'; with one tree this is just a decision tree.'}</p></div>`;
    $('rfFacts').innerHTML=F('n_estimators',n)+F('criterion',crit)+F('majority vote','classification')+F('mean vote','regression')+
      F('simulated accuracy',pct(clamp(acc,0.8,0.995),1),'hot')+F('his entropy run','98 %')+F('his gini run','99 %')+F('his 7-tree run','99 %')+F('his 12-tree run','98 %','bad');
    say('rfWhy',`He runs exactly this experiment on the penguin data (344 rows, 7 features, split 233 / 100): entropy → <b>98 %</b> with precision 96 %, recall 100 %, F1 98 % and only two wrong cases; switch the criterion to gini → <b>99 %</b>; then set n_estimators to 7 and back to 12 and watch it go <b>down</b> to 98 %. \"With seven we were getting 99, so let's see… the accuracy reduced.\" More trees is not a promise, it is a hypothesis you have to measure.`);
  }
  run();
})();

/* ============================== 18 · KNN ============================== */
(()=>{
  let K=5, dist='euclid', seed=3;
  const pts=()=>{let s=seed; const r=()=>{s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff};
    const P=[]; for(let i=0;i<40;i++){const cl=i<24?0:1;
      P.push({x:cl?18+r()*26:30+r()*44, y:cl?70-r()*22:24+r()*46, cl})} return P};
  ['knK','knX','knY'].forEach(i=>$(i).oninput=run);
  chips('knDist',[['euclid','Euclidean'],['manhattan','Manhattan'],['cheb','Chebyshev']],dist,v=>{dist=v;press('knDist',v);run()});
  function d(a,b){const dx=Math.abs(a.x-b.q),dy=Math.abs(a.y-b.p);
    return dist==='euclid'?Math.hypot(dx,dy):dist==='manhattan'?dx+dy:Math.max(dx,dy)}
  function run(){
    K=+$('knK').value; const q={x:+$('knX').value,y:+$('knY').value};
    $('knKv').textContent=K+(K%2?'':' (even → ties possible)');
    const P=pts(), W=470,H=300, X=v=>20+v/100*(W-40), Y=v=>H-24-v/100*(H-52);
    const ranked=P.map(p=>({...p,d:d(q,p)})).sort((a,b)=>a.d-b.d);
    const near=ranked.slice(0,K), votes=near.filter(n=>n.cl).length;
    const cls=votes>K/2?1:0;
    let g='';
    for(let i=1;i<=9;i+=2){g+=`<line x1="${X(i*10)}" y1="12" x2="${X(i*10)}" y2="${H-24}" class="axline" opacity=".4"/><line x1="20" y1="${Y(i*10)}" x2="${W-20}" y2="${Y(i*10)}" class="axline" opacity=".4"/>`}
    near.slice(-1).forEach(n=>{g+=`<circle cx="${X(n.x)}" cy="${Y(n.y)}" r="${Math.hypot(X(n.x)-X(q.x/1),0)*0+ (dist==='euclid'?Math.hypot(n.x-q.x,n.y-q.y):dist==='manhattan'?n.x-q.x+n.y-q.y:Math.max(Math.abs(n.x-q.x),Math.abs(n.y-q.y)))/100*Math.hypot(W-40,H-52)/1.4}" fill="none" stroke="var(--fill)" stroke-width="1.5" opacity=".35"/>`});
    P.forEach(p=>{const isN=near.includes(p);
      g+=`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="${isN?7:5}" fill="${p.cl?'var(--b)':'var(--a)'}" opacity="${isN?1:.45}" stroke="${isN?'var(--ink)':'none'}" stroke-width="1.5"/>`});
    g+=`<rect x="10" y="10" width="150" height="20" fill="none"/><text x="14" y="24" class="axlab" font-size="11">● blue = class 0 &nbsp; ● orange = class 1</text>`;
    g+=`<path d="M${X(q.x)} ${Y(q.y)} m-9 0 l9 -9 l9 9 l-9 9 z" fill="var(--fill)" stroke="var(--hl-edge)" stroke-width="2"/>
      <text x="${X(q.x)+12}" y="${Y(q.y)-8}" class="axlab" fill="var(--b)">query</text>`;
    $('knSvg').innerHTML=g;
    $('knFacts').innerHTML=F('K',K)+F('votes for class 1',votes)+F('votes for class 0',K-votes)+
      F('prediction',cls?'class 1 (malignant-ish)':'class 0 (benign)','hot')+F('farthest neighbour',fmt(near[near.length-1].d,1))+
      F('distance',({euclid:'√(Δx²+Δy²)',manhattan:'Σ|Δ|',cheb:'max|Δ|'})[dist]);
    say('knWhy',`There is no model here — nothing was fitted. Press nothing, and the answer changes only because ${K} closest neighbours changed their minds. ${K===1?'K = 1 is his \"least bias, most flexible\" case: the boundary hugs every single point, which memorises noise.':'K = '+K+' averages over '+K+' opinions, so one weird point can no longer decide the answer.'} ${dist==='manhattan'?'Manhattan distance moves along the axes only — it is the right metric when features are independent steps, and it makes the boundary a staircase.':'Euclidean is the straight-line distance he draws between p1 and p2.'}`);
    sweep();
  }
  function sweep(){
    const W=460,H=220;
    const err=k=>{const base=0.05+0.06*Math.exp(-k/2)+0.11/(1+Math.exp(-(k-14)/3.2)); return clamp(base+(k===Math.round(21*0.95)?-0.02:0),0.02,0.3)};
    const X=k=>26+(k-1)*(W-50)/39, Y=v=>H-28-v*(H-58)/0.32;
    $('knSweep').innerHTML=`<line x1="26" y1="${Y(0)}" x2="${W-16}" y2="${Y(0)}" class="axline"/>
      <path d="${Array.from({length:40},(_,i)=>{const k=i+1;return `${i?'L':'M'}${X(k)} ${Y(err(k))}`}).join(' ')}" fill="none" stroke="var(--a)" stroke-width="3"/>
      <line x1="${X(21)}" y1="10" x2="${X(21)}" y2="${Y(0)}" stroke="var(--fill)" stroke-width="2"/>
      <circle cx="${X(21)}" cy="${Y(err(21))}" r="6" fill="var(--fill)" stroke="var(--hl-edge)" stroke-width="2"/>
      <text x="${X(21)-30}" y="20" class="axlab" fill="var(--b)">best K = 21</text>
      <text x="28" y="16" class="axlab">test error as K goes 1 → 40 (his loop)</text>
      ${[1,10,20,30,40].map(k=>`<text x="${X(k)}" y="${H-10}" class="axlab" text-anchor="middle">${k}</text>`).join('')}`;
    say('knSweepWhy','He runs K from 1 to 40 and reads the error curve: on breast cancer the dip lands at <b>K = 21</b>, and accuracy goes from 94–95 % at K = 1 to <b>about 99 %</b>. On iris the same sweep takes 96 % to <b>100 %</b>. Low K = high variance (every noisy point rules); high K = high bias (the boundary turns into a straight line and stops caring where the classes actually are). The U-shape between them is the bias–variance trade-off drawn for you.');
  }
  /* scaling */
  let sa=100, sb=100, sc=false;
  $('knSa').oninput=run2; $('knSb').oninput=run2;
  chips('knSc',[['off','raw values'],['on','StandardScaler']],String(sc),v=>{sc=v==='on';press('knSc',v);run2()});
  function run2(){
    sa=+$('knSa').value; sb=+$('knSb').value;
    const W=460,H=200, mx=Math.max(sa,sb);
    const A=(v)=>v*sa/mx, B=v=>v*sb/mx;
    const X=v=>30+v/mx*(W-60), Y=v=>H-26-v/mx*(H-52);
    const pts=[[10,60],[20,55],[15,65],[70,20],[80,25],[75,10]].map(([a,b])=>({a:sc?a/50:b*0+ a/50, b:sc?b/50:b/50, ra:A(a), rb:B(b)}));
    const scale=sc?(v)=>v/50:(v)=>v;
    const P=pts.map(p=>({...p,x:sc?p.a/2:p.a,y:sc?p.b/2:p.b}));
    const grid=P.map((p,i)=>{const vx=sc? p.a : p.ra, vy=sc? p.b : p.rb;
      return {x:30+vx/(sc?2:mx)*(W-60), y:H-26-vy/(sc?2:mx)*(H-52), cl:i<3?0:1}});
    $('knScale').innerHTML=`${[0,1,2,3].map(i=>`<line x1="30" y1="${Y(i/3*(sc?2:mx))}" x2="${W-20}" y2="${Y(i/3*(sc?2:mx))}" class="axline" opacity=".4"/>`).join('')}
      ${grid.map(p=>`<circle cx="${p.x}" cy="${p.y}" r="7" fill="${p.cl?'var(--b)':'var(--a)'}"/>`).join('')}
      <line x1="30" y1="${H-26}" x2="${W-20}" y2="${H-26}" class="axline"/><line x1="30" y1="12" x2="30" y2="${H-26}" class="axline"/>
      <text x="34" y="22" class="axlab">feature B (0–${sb}) vertical · feature A (0–${sa}) horizontal ${sc?'— both rescaled to mean 0, σ 1':''}</text>`;
    say('knWhy',`The distance panel above is unaffected, but <b>this</b> is the trap: with A running 0–${sa} and B 0–${sb}, ${sa===sb?'the two features are equally weighted — the vote is fair.':(sa>sb*10?`the bigger range owns the distance, and feature B might as well not exist`:`feature ${sa>sb?'A':'B'} now dominates`)} ${sc?'StandardScaler has put both on the same footing, which is why he scales before every KNN run.':''}`);
  }
  run(); run2();
})();

/* ============================== 19 · NAIVE BAYES ============================== */
(()=>{
  const DAYS=[
    {outlook:'sunny',temp:'hot',humidity:'high',windy:'weak',play:'no'},
    {outlook:'sunny',temp:'hot',humidity:'high',windy:'strong',play:'no'},
    {outlook:'overcast',temp:'hot',humidity:'high',windy:'weak',play:'yes'},
    {outlook:'rainy',temp:'mild',humidity:'high',windy:'weak',play:'yes'},
    {outlook:'rainy',temp:'cool',humidity:'normal',windy:'weak',play:'yes'},
    {outlook:'rainy',temp:'cool',humidity:'normal',windy:'strong',play:'no'},
    {outlook:'overcast',temp:'cool',humidity:'normal',windy:'strong',play:'yes'},
    {outlook:'sunny',temp:'mild',humidity:'high',windy:'weak',play:'no'},
    {outlook:'sunny',temp:'cool',humidity:'normal',windy:'weak',play:'yes'},
    {outlook:'rainy',temp:'mild',humidity:'normal',windy:'weak',play:'yes'},
    {outlook:'sunny',temp:'mild',humidity:'normal',windy:'strong',play:'yes'},
    {outlook:'overcast',temp:'mild',humidity:'high',windy:'strong',play:'yes'},
    {outlook:'overcast',temp:'hot',humidity:'normal',windy:'weak',play:'yes'},
    {outlook:'rainy',temp:'mild',humidity:'high',windy:'strong',play:'no'}];
  const trainN=10;
  let dayIdx=4, alpha=0;
  chips('nbDay',DAYS.slice(trainN).map((d,i)=>[String(trainN+i),`day ${trainN+i+1}`,`${d.outlook}/${d.temp}/${d.humidity}/${d.windy}`]),String(dayIdx),v=>{dayIdx=+v;run()});
  $('nbA').oninput=e=>{alpha=+e.target.value/100;run()};
  function run(){
    const tr=DAYS.slice(0,trainN), q=DAYS[dayIdx];
    const classes=uniq(tr.map(d=>d.play)), feats=['outlook','temp','humidity','windy'];
    const pc=c=>(tr.filter(d=>d.play===c).length+alpha)/(tr.length+alpha*classes.length);
    const pl=(f,v,c)=>{const sub=tr.filter(d=>d.play===c);
      return (sub.filter(d=>d[f]===v).length+alpha)/(sub.length+alpha*uniq(tr.map(d=>d[f])).length)};
    const raw=classes.map(c=>{let p=pc(c); feats.forEach(f=>p*=pl(f,q[f],c)); return {c,p}});
    const tot=sum(raw.map(r=>r.p)), post=raw.map(r=>({...r,p:r.p/tot}));
    const bestP=post.reduce((a,b)=>b.p>a.p?b:a);
    $('nbTables').innerHTML=`<div class="tbl">${['feature','value',...classes.map(c=>'P('+q.outlook+'…|'+c+')')].map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>`.replace('<div class="tbl">','<div class="tbl" style="margin-bottom:6px">')+
      `<div class="tbl"><div class="trow">${['prior P(class)','',...classes.map(c=>fmt(pc(c),3))].map(x=>`<div class="tc ${x===''?'hd':''}">${x}</div>`).join('')}</div>
      ${feats.map(f=>`<div class="trow">${[f,q[f],'',...classes.map(c=>fmt(pl(f,q[f],c),3))].map((x,i)=>`<div class="tc ${i===2?'hd':''}">${x}</div>`).join('')}</div>`).join('')}
      <div class="trow">${['× all of them →','',...classes.map(c=>fmt(raw.find(r=>r.c===c).p,6))].map((x,i)=>`<div class="tc ${i===2?'hd':''}">${x}</div>`).join('')}</div>
      <div class="trow">${['÷ their sum = posterior','',...classes.map(c=>pct(post.find(r=>r.c===c).p,1))].map((x,i)=>`<div class="tc ${i===2?'hd':''} ${i>2&&post.find(r=>r.c===classes[i-1])===bestP?'tot':''}">${x}</div>`).join('')}</div></div>`;
    $('nbFacts').innerHTML=F('day',dayIdx+1)+F('evidence',`${q.outlook}, ${q.temp}, ${q.humidity}, ${q.windy}`)+
      F('P(yes)',pct(post.find(r=>r.c==='yes').p,2))+F('P(no)',pct(post.find(r=>r.c==='no').p,2))+
      F('prediction',bestP.c==='yes'?'play ✓':'stay home','hot')+F('smoothing α',fmt(alpha,2))+
      F('his train acc','80 %')+F('his test acc','75 %');
    say('nbWhy',`Every feature is <b>assumed independent</b>, so the joint likelihood is a plain product — that is the "naive" part, and it is why this classifier is absurdly fast on text with thousands of features. ${alpha>0?`With α = ${fmt(alpha,2)} you have added Laplace smoothing: no probability can become 0 and wipe out the whole product. On ${trainN} training rows that matters the moment one combination is unseen.`:'With α = 0 a category never seen in a class gives a product of exactly 0 — the classic Naive Bayes blow-up. Drag the smoothing knob and watch the zero disappear.'} His own run on this file: 10 training rows, 4 test rows, training accuracy 80 %, test accuracy 75 %.`);
    $('nbCard').innerHTML=[['P(king)','4/52',fmt(4/52,4)],['P(face)','12/52 = 1/3',fmt(12/52,4)],['P(face | king)','1','1.000'],
      ['P(king | face)','1 × (4/52) / (12/52)',fmt((4/52)/(12/52),4)]].map(([a,b,c])=>
      `<div class="trow"><div class="tc hd" style="min-width:130px">${a}</div><div class="tc" style="min-width:150px">${b}</div><div class="tc ${a.includes('king |')?'tot':''}">${c}</div></div>`).join('');
    $('nbTree').innerHTML=`<div class="tbl"><div class="trow">${['','P(disease)','P(no disease)'].map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>
      <div class="trow">${['prior','0.10','0.90'].map((v,i)=>`<div class="tc ${i===0?'hd':''}">${v}</div>`).join('')}</div>
      <div class="trow">${['P(+|class)','0.95','0.05'].map((v,i)=>`<div class="tc ${i===0?'hd':''}">${v}</div>`).join('')}</div>
      <div class="trow">${['numerator','0.095','0.045'].map((v,i)=>`<div class="tc ${i===0?'hd':''}">${v}</div>`).join('')}</div>
      <div class="trow">${['posterior','68 %','32 %'].map((v,i)=>`<div class="tc ${i===0?'hd':''} ${i===1?'tot':''}">${v}</div>`).join('')}</div></div>
      <p class="hint">His set-up: "the probability of having a disease is 0.10 and the probability of not having a disease is 0.90", then the test's accuracy comes in and you multiply and normalise. Same arithmetic as the cards, same arithmetic as the tennis table — that is all Naive Bayes is.</p>`;
  }
  dayIdx=10; run();
})();


/* ============================== 20 · SVM ============================== */
(()=>{
  let kernel='rbf';
  chips('svmK',[['linear','linear'],['poly','polynomial'],['rbf','RBF']],kernel,v=>{kernel=v;press('svmK',v);run()});
  ['svmAng','svmOff','svmC'].forEach(i=>$(i).oninput=run);
  const P=[]; {let s=11; const r=()=>{s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff};
    for(let i=0;i<30;i++)P.push({x:22+r()*26,y:20+r()*60,cl:0});
    for(let i=0;i<30;i++)P.push({x:56+r()*26,y:24+r()*58,cl:1});
    P.push({x:48,y:52,cl:0},{x:50,y:48,cl:1});}
  function run(){
    const ang=+$('svmAng').value, off=+$('svmOff').value, C=+$('svmC').value;
    $('svmAngV').textContent=ang+'°'; $('svmOffV').textContent=off; $('svmCv').textContent=C;
    const W=470,H=290, X=v=>16+v/100*(W-32), Y=v=>H-20-v/100*(H-40);
    const th=ang*Math.PI/180, nx=Math.sin(th), ny=-Math.cos(th), c=off/100*220;
    let g='';
    const side=p=>nx*X(p.x)+ny*Y(p.y)-c;
    let sv=[];
    P.forEach(p=>{const s=side(p);
      const ok=(p.cl&&s<0)||(!p.cl&&s>0);
      if(Math.abs(s)<26)sv.push(p);
      g+=`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="6" fill="${p.cl?'var(--b)':'var(--a)'}" opacity="${ok?.95:.35}" stroke="${ok&&Math.abs(s)<26?'var(--ink)':'none'}" stroke-width="2"/>`});
    const x1=(c-ny*10)/nx||0;
    const p1={x:16,y:(c-nx*16)/ny}, p2={x:W-16,y:(c-nx*(W-16))/ny};
    g+=`<line x1="${p1.x}" y1="${clamp(p1.y,0,H)}" x2="${p2.x}" y2="${clamp(p2.y,0,H)}" stroke="var(--ink)" stroke-width="3"/>`;
    [-1,1].forEach(k=>g+=`<line x1="${p1.x}" y1="${clamp(p1.y+k*26,0,H)}" x2="${p2.x}" y2="${clamp(p2.y+k*26,0,H)}" stroke="var(--ink)" stroke-width="1.5" stroke-dasharray="5 5" opacity=".7"/>`);
    if(kernel!=='linear'){
      const rad=kernel==='poly'?70:44;
      g+=`<circle cx="${X(50)}" cy="${Y(50)}" r="${rad}" fill="none" stroke="var(--c)" stroke-width="3" ${kernel==='rbf'?'stroke-dasharray="8 6"':''}/>`;
      g+=`<text x="18" y="20" class="axlab" fill="var(--c)">${kernel==='poly'?'polynomial: a curved boundary of degree d':'RBF: each support vector is a bump; together they wrap one class in a circle'}</text>`;
    } else g+=`<text x="18" y="20" class="axlab">linear: a dot product between the two vectors, no bending</text>`;
    g+=`<text x="18" y="${H-6}" class="axlab">the widest street between the two clouds is the maximum-margin hyperplane · ${sv.length} points are inside the street</text>`;
    $('svmSvg').innerHTML=g;
    const wrong=P.filter(p=>{const s=side(p);return !((p.cl&&s<0)||(!p.cl&&s>0))}).length;
    const marginGuess=clamp(26-wrong*2.2,4,26);
    $('svmFacts').innerHTML=F('misclassified',wrong,wrong?'bad':'good')+F('margin width',fmt(marginGuess,1))+
      F('support vectors',sv.length)+F('C',C)+F('penalty',C>150?'every miss punished → hard margin':'some misses tolerated → soft margin')+
      F('his accuracy','0.92')+F('his precision / recall','93 % / 94 %');
    say('svmWhy',`The hyperplane is not chosen to separate — many lines do that. It is chosen to <b>maximise the margin</b>, the gap to the closest points, and those closest points are the <em>support vectors</em> that give the method its name. ${wrong?`${wrong} points are on the wrong side. With C = ${C} ${C>150?'you are punishing that hard, so the street will squeeze thin and start memorising.':'you tolerate the miss and keep a wide, more robust street.'}`:'Nothing on the wrong side — this is a clean hard-margin separation.'} ${kernel==='linear'?'When the classes really are separable by a flat line, the linear kernel is enough and it is the fastest.':'When no flat line will do, the "kernel trick" maps the input into more dimensions — polynomial bends it, RBF maps it into infinite dimensions — and a flat hyperplane works again up there.'}`);
  }
  run();
})();

/* ============================== 21 · K-MEANS ============================== */
(()=>{
  let pts=[], cents=[], assign=[], iter=0, K=3;
  const gen=n=>{let s=5;const r=()=>{s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff};
    const out=[], blobs=3+Math.floor(r()*3);
    for(let i=0;i<n;i++){const b=Math.floor(r()*blobs);
      out.push({x:clamp(15+ (b%3)*30 + (r()-0.5)*22,1,99), y:clamp(20+Math.floor(b/3)*40+(r()-0.5)*26,1,99)})}
    return out};
  function reset(){pts=gen(+$('kmN').value); K=+$('kmK').value;
    cents=Array.from({length:K},(_,i)=>{const p=pts[Math.floor(i*pts.length/K)];return {x:p.x+(Math.random()-.5)*6,y:p.y+(Math.random()-.5)*6}});
    iter=0; stepAssign()};
  function dist(a,b,p){return Math.hypot(b.x-p.x,b.y-p.y)}
  function stepAssign(){assign=pts.map(p=>cents.reduce((bi,c,i)=>dist(0,c,p)<dist(0,cents[bi],p)?i:bi,0))}
  function stepUpdate(){
    let moved=0;
    cents=cents.map((c,i)=>{const mem=pts.filter((_,j)=>assign[j]===i);
      if(!mem.length)return c;
      const nx=mean(mem.map(p=>p.x)), ny=mean(mem.map(p=>p.y));
      moved=Math.max(moved,Math.hypot(nx-c.x,ny-c.y)); return {x:nx,y:ny}});
    iter++; return moved;
  }
  function inertia(){return sum(pts.map((p,j)=>dist(0,cents[assign[j]],p)**2))}
  const C=['--a','--b','--c','--d','--e','--fill','--good'];
  function draw(){
    const W=470,H=300, X=v=>16+v/100*(W-32), Y=v=>H-20-v/100*(H-40);
    let g='';
    cents.forEach((c,i)=>{g+=`<circle cx="${X(c.x)}" cy="${Y(c.y)}" r="26" fill="none" stroke="${C[i]}" opacity=".25"/>`});
    pts.forEach((p,i)=>g+=`<circle cx="${X(p.x)}" cy="${Y(p.y)}" r="5" fill="${C[assign[i]]}" opacity=".9"/>`);
    cents.forEach((c,i)=>{g+=`<g class="pt" data-c="${i}"><circle cx="${X(c.x)}" cy="${Y(c.y)}" r="12" fill="${C[i]}" stroke="var(--ink)" stroke-width="2.5"/>
      <text x="${X(c.x)}" y="${Y(c.y)+4}" text-anchor="middle" font-size="12" fill="#fff" font-weight="bold">${i}</text></g>`});
    $('kmSvg').innerHTML=g;
    [...$('kmSvg').querySelectorAll('.pt')].forEach(el=>{
      let dragging=false;
      el.addEventListener('pointerdown',e=>{dragging=true;el.setPointerCapture(e.pointerId)});
      el.addEventListener('pointermove',e=>{if(!dragging)return;
        const r=$('kmSvg').getBoundingClientRect(), i=+el.dataset.c;
        cents[i]={x:clamp((e.clientX-r.left-16)/(r.width-32)*100,0,100), y:clamp((1-(e.clientY-r.top-20)/(r.height-40))*100,0,100)};
        stepAssign(); draw()});
      el.addEventListener('pointerup',()=>dragging=false);
    });
    const cnt=Array.from({length:K},(_,i)=>assign.filter(a=>a===i).length);
    $('kmFacts').innerHTML=F('K',K)+F('iteration',iter)+F('inertia (WCSS)',fmt(inertia(),1),'hot')+
      F('cluster sizes',cnt.join(' / '))+F('largest cluster',Math.max(...cnt)+' points')+F('empty clusters',cnt.filter(c=>!c).length,cnt.some(c=>!c)?'bad':'');
    say('kmWhy',iter===0?'Centroids are random guesses. <b>Step</b> assigns every point to its nearest centroid (that colours the dots), then re-centroid each group — and the centroids walk. Press <b>Run to convergence</b> to see the loop finish, or drag a centroid anywhere and the assignment follows it instantly.':
      `Inertia = Σ distance² from each point to its own centroid. Every step of the loop can only lower it, which is why the algorithm is called "mean shift to convergence". His movie run put <b>~4 700 of 5 000 titles into cluster 0</b> and scattered the rest as 4, 11, 87 and 67 — a warning: a huge lopsided split usually means K is wrong or one feature dominates.`);
    elbow();
  }
  function elbow(){
    const W=460,H=220, xs=[];
    const inv=Array.from({length:10},(_,i)=>{const k=i+1; return 1/(0.35+k*0.6)});
    const mx=Math.max(...inv);
    const X=k=>30+k*(W-56)/10, Y=v=>H-30-v/mx*(H-60);
    $('kmElbow').innerHTML=`<line x1="30" y1="${Y(0)}" x2="${W-18}" y2="${Y(0)}" class="axline"/>
      <path d="${inv.map((v,i)=>`${i?'L':'M'}${X(i+1)} ${Y(v)}`).join(' ')}" fill="none" stroke="var(--a)" stroke-width="3"/>
      ${inv.map((v,i)=>`<circle cx="${X(i+1)}" cy="${Y(v)}" r="4" fill="var(--a)"/>`).join('')}
      <line x1="${X(3)}" y1="14" x2="${X(3)}" y2="${Y(0)}" stroke="var(--fill)" stroke-dasharray="5 4"/>
      <text x="${X(3)+6}" y="22" class="axlab" fill="var(--b)">the elbow — after this K, dropping further costs you almost nothing</text>
      <text x="30" y="${H-8}" class="axlab">K = number of clusters →</text><text x="32" y="18" class="axlab">inertia / WCSS (lower is tighter)</text>`;
    say('kmElbowWhy','K-means cannot tell you K — <b>you</b> must. The elbow method is his answer: plot inertia against K, find where the curve stops falling steeply, and take that K. Too low and you merge different groups; too high and you are just partitioning noise.');
  }
  chips('kmFam',[['k','K-means'],['fuzzy','Fuzzy C-means'],['seam','SEAM / distance based'],['hier','Agglomerative'],['div','Divisive'],['ms','Mean-shift']],
    'k',v=>{
      const W={k:'Hard assignment, one cluster per point, you choose K, sensitive to outliers.',
        fuzzy:'A point can belong to <b>two or more clusters</b> with a membership weight — "in SEAM/fuzzy clustering a point can belong to one or two clusters".',
        seam:'Distance-driven partitioning where a point on a border is allowed to sit in both groups.',
        hier:'Bottom-up merging into a dendrogram, no K needed in advance (station 22).',
        div:'Top-down: "one cluster splits the root into sub-clusters, and every cluster has its own sub-cluster." The mirror of agglomerative.',
        ms:'Finds the density peaks, so the number of clusters falls out of the data instead of being declared.'};
      $('kmFam').innerHTML=`<div class="trow"><div class="tc hd">family</div><div class="tc hd">how it decides</div></div><div class="trow"><div class="tc">${v}</div><div class="tc" style="min-width:300px;text-align:left">${W[v]}</div></div>`;
    });
  $('kmK').oninput=()=>{reset();draw()}; $('kmN').oninput=()=>{reset();draw()};
  $('kmStep').onclick=()=>{stepAssign(); stepUpdate(); stepAssign(); draw()};
  $('kmRun').onclick=()=>{let guard=0; const go=()=>{stepAssign(); const m=stepUpdate(); stepAssign(); draw(); if(m>0.4&&guard++<40)requestAnimationFrame(go)}; go()};
  $('kmNew').onclick=()=>{reset();draw()};
  reset(); draw();
})();

/* ============================== 22 · HIERARCHICAL ============================== */
(()=>{
  let pts=[], clusters=[], merges=[], link='ward';
  const gen=n=>{let s=9;const r=()=>{s=(s*1103515245+12345)&0x7fffffff;return s/0x7fffffff};
    return Array.from({length:n},(_,i)=>({id:i,name:'ABCDEFGHJKLM'[i],x:6+r()*88,y:6+r()*88}))};
  chips('hcLink',[['ward','ward'],['single','single'],['complete','complete'],['average','average']],link,v=>{link=v;press('hcLink',v);reset()});
  $('hcN').oninput=e=>{$('hcNv').textContent=e.target.value;reset()};
  function reset(){pts=gen(+$('hcN').value); clusters=pts.map(p=>({members:[p]})); merges=[]; draw()}
  function cd(A,B){
    const d=A.members.flatMap(a=>B.members.map(b=>Math.hypot(a.x-b.x,a.y-b.y)));
    return link==='single'?Math.min(...d):link==='complete'?Math.max(...d):link==='average'?mean(d):
      (()=>{const ca=A.members.map(a=>[a.x,a.y]),cb=B.members.map(b=>[b.x,b.y]);
        const m=g=>[mean(g.map(p=>p[0])),mean(g.map(p=>p[1]))];
        const ma=m(ca),mb=m(cb),na=ca.length,nb=cb.length;
        return Math.sqrt((na*nb/(na+nb))*((ma[0]-mb[0])**2+(ma[1]-mb[1])**2))})();
  }
  function mergeClosest(){
    if(clusters.length<2)return false;
    let best=null;
    for(let i=0;i<clusters.length;i++)for(let j=i+1;j<clusters.length;j++){
      const d=cd(clusters[i],clusters[j]); if(!best||d<best.d)best={i,j,d}}
    const A=clusters[best.i],B=clusters[best.j];
    merges.push({a:A,b:B,d:best.d,id:'m'+merges.length});
    clusters=clusters.filter((_,k)=>k!==best.i&&k!==best.j)
      .concat([{members:[...A.members,...B.members],node:merges.length-1}]);
    return true;
  }
  $('hcMerge').onclick=()=>{if(mergeClosest())draw()};
  $('hcAll').onclick=()=>{let g=0; while(clusters.length>1&&g++<40)mergeClosest(); draw()};
  $('hcNew').onclick=reset;
  $('hcCut').oninput=e=>{$('hcCutV').textContent=e.target.value+'%';draw()};
  function label(i){ // which merge-group does this point fall into at the cut
    let g=merges.length-1, cut=+$('hcCut').value/100*maxD();
    const groups=pts.map(p=>({p,set:new Set([p.id])}));
    merges.forEach((m,k)=>{ if(m.d>cut)return;
      const s=new Set([...(find(m.a)?.set||[]),...(find(m.b)?.set||[])]) });
    return null;
  }
  function find(){return null}
  function maxD(){return Math.max(...merges.map(m=>m.d),1)}
  function draw(){
    const cutP=+$('hcCut').value/100, cut=cutP*maxD();
    const parent=new Map(pts.map(p=>[p.id,p.id]));
    const findk=x=>{while(parent.get(x)!==x)x=parent.get(x);return x};
    const uni=(a,b)=>{const ka=findk(a),kb=findk(b); if(ka!==kb)parent.set(kb,ka)};
    merges.forEach(m=>{ if(m.d<=cut){uni(m.a.members[0].id, m.b.members[0].id)} });
    const roots=uniq(pts.map(p=>findk(p.id)));
    const W=470,H=250;
    let g='';
    const order=pts.slice();
    const X=i=>28+i*(W-56)/Math.max(1,order.length-1);
    const Y=d=>H-24-(d/maxD())*(H-44);
    const nodePos=new Map();
    order.forEach((p,i)=>nodePos.set(p.id,[X(i),Y(0)]));
    merges.forEach((m,k)=>{
      const pa=nodePos.get(m.a.members[0].id), pb=nodePos.get(m.b.members[0].id);
      const y=Y(m.d), x=(pa[0]+pb[0])/2;
      g+=`<path d="M${pa[0]} ${pa[1]} L${pa[0]} ${y} L${pb[0]} ${y} L${pb[0]} ${pb[1]}" fill="none" stroke="${m.d>cut?'var(--bad)':'var(--a)'}" stroke-width="2"/>`;
      nodePos.set(m.a.members[0].id,[x,y]);
      g+=`<circle cx="${x}" cy="${y}" r="3" fill="var(--muted)"/>`;
    });
    order.forEach((p,i)=>{const root=findk(p.id), col=roots.indexOf(root);
      g+=`<circle cx="${X(i)}" cy="${H-24}" r="7" fill="${C2(col)}"/><text x="${X(i)}" y="${H-8}" text-anchor="middle" class="axlab">${p.name}</text>`});
    g+=`<line x1="12" y1="${Y(cut)}" x2="${W-12}" y2="${Y(cut)}" stroke="var(--fill)" stroke-width="2" stroke-dasharray="7 5"/>
      <text x="14" y="${Y(cut)-6}" class="axlab" fill="var(--b)">your cut → ${roots.length} clusters</text>
      <text x="14" y="16" class="axlab">${link} linkage · distance grows upward · ${merges.length} merges done of ${pts.length-1}</text>`;
    $('hcDendro').innerHTML=g;
    const W2=470,H2=200, X2=v=>20+v/100*(W2-40), Y2=v=>H2-22-v/100*(H2-40);
    $('hcPts').innerHTML=uniq(pts.map(p=>findk(p.id))).map((r,i)=>{
      const mem=pts.filter(p=>findk(p.id)===r);
      return mem.map(p=>`<circle cx="${X2(p.x)}" cy="${Y2(p.y)}" r="8" fill="${C2(i)}"/>`).join('')+
        `<text x="${X2(mean(mem.map(p=>p.x)))}" y="${Y2(Math.max(...mem.map(p=>p.y)))-12}" class="axlab" text-anchor="middle" fill="${C2(i)}">${mem.length}</text>`}).join('')+
      `<text x="14" y="16" class="axlab">the same points on the plane, grouped by where you cut</text>`;
    $('hcFacts').innerHTML=F('points',pts.length)+F('merges so far',merges.length)+F('clusters at this cut',roots.length,'hot')+
      F('linkage',link)+F('largest group',Math.max(...uniq(pts.map(p=>findk(p.id))).map(r=>pts.filter(p=>findk(p.id)===r).length)))+
      F('next merge distance',fmt(clusters.length>1?Math.min(...(()=>{let m=Infinity;for(let i=0;i<clusters.length;i++)for(let j=i+1;j<clusters.length;j++)m=Math.min(m,cd(clusters[i],clusters[j]));return m})()):0,2));
    say('hcWhy',merges.length===0?`Nothing merged yet — every point is its own cluster, which is what agglomerative clustering starts from. Press <b>Merge closest</b>: the two nearest points join first. ${link==='ward'?'Ward merges the pair whose joining increases the within-group variance the least — round, even clusters.':'Single linkage chains, complete linkage keeps clusters tight, average is the compromise.'}`
      :clusters.length===1?'One cluster left — that is the end state he describes: "the clustering continues until we obtain a single cluster". Drag the cut line down to recover the groups you want.'
      :`The tree is the answer to the question K-means makes you guess. ${merges.length===pts.length-1?'Full tree: now drag the <b>cut height</b> — where it crosses the vertical lines decides the number of clusters.':`Keep pressing merge, ${clusters.length-1} more merges will finish the tree.`} The red segments are the merges your cut rejects. His employment example is exactly this reading: public+private join into one "employment" branch, unemployed stays its own branch, and the level of the join is the information.`);
  }
  const C2=i=>['var(--a)','var(--b)','var(--c)','var(--d)','var(--e)','var(--bad)','var(--warn)','var(--accent)'][i%8];
  $('hcLinkTbl').innerHTML=[['ward','least extra variance per merge — the default choice'],
    ['single','closest pair only; makes long chains'],['complete','furthest pair; makes tight balls'],
    ['average','mean of all pairs; the middle ground']]
    .map(([a,b])=>`<div class="trow"><div class="tc hd">${a}</div><div class="tc" style="min-width:300px;text-align:left">${b}</div></div>`).join('');
  reset();
})();

/* ============================== 23 · APRIORI ============================== */
(()=>{
  const TX=[[1,3,4],[2,3,5],[1,2,3,5],[2],[1,3,5]];
  let msup=2, mconf=60, level='F2';
  $('apMinSup').oninput=e=>{msup=+e.target.value;run()};
  $('apMinConf').oninput=e=>{mconf=+e.target.value;run()};
  chips('apLevel',[['C1','C1'],['F1','F1'],['C2','C2'],['F2','F2'],['C3','C3'],['F3','F3'],['rules','rules']],level,v=>{level=v;press('apLevel',v);run()});
  const sup=set=>TX.filter(t=>[...set].every(i=>t.includes(i))).length;
  const subsets=k=>{const out=[]; const s=[...Array(k).keys()].filter(i=>i>0&&i<k);
    for(let m=1;m<(1<<k)-1;m++){const a=[...s].filter(i=>m&(1<<(i-1))); if(a.length)out.push(a)} return out};
  function cands(k){
    const prev=all(k-1); const out=[];
    for(let i=0;i<prev.length;i++)for(let j=i+1;j<prev.length;j++){
      const A=prev[i],B=prev[j];
      if(A.slice(0,k-1).join()===B.slice(0,k-1).join()&&A[k-1]!==B[k-1]){
        const c=[...A,B[k-1]]; out.push(c);}}
    return out;
  }
  const all=k=>k===1?[...uniq(TX.flat())].sort((a,b)=>a-b).map(v=>[v])
    :cands(k).filter(s=>{const pr=s.map((_,i)=>[...s.slice(0,i),...s.slice(i+1)]);return pr.every(p=>frequent(p)&&all(k-1).some(q=>q.join()===p.join()))});
  const frequent=s=>sup(s)>=msup;
  function run(){
    const steps={C1:[1,2,3,4,5].map(v=>[v]),F1:[1,2,3,4,5].map(v=>[v]).filter(frequent),
      C2:cands(2),F2:cands(2).filter(frequent),C3:cands(3),F3:cands(3).filter(frequent)};
    let html='';
    if(level==='rules'){
      const rules=[];
      steps.F3.forEach(item=>{ subsets(item.length).forEach(si=>{
        const ante=si.map(i=>item[i]), cons=item.filter(x=>!ante.includes(x));
        const sa=sup(ante), sc=sup(item);
        if(!sa)return;
        const conf=sc/sa, lift=conf/(sup(cons)/TX.length);
        rules.push({ante,cons,sup:sc,conf,lift,ok:conf*100>=mconf})})});
      html=`<div class="tbl"><div class="trow">${['rule','support','confidence','lift','≥ min conf?'].map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>
        ${rules.map(r=>`<div class="trow"><div class="tc" style="min-width:160px">{${r.ante}} → {${r.cons}}</div>
        <div class="tc">${r.sup}</div><div class="tc ${r.ok?'g':'r'}">${pct(r.conf,0)}</div><div class="tc">${fmt(r.lift,2)}</div>
        <div class="tc ${r.ok?'g':'r'}">${r.ok?'kept':'dropped'}</div></div>`).join('')||'<div class="trow"><div class="tc off">no frequent 3-sets at this support</div></div>'}</div>`;
      const t=rules.filter(r=>r.ok);
      $('apRules').innerHTML=`<p class="hint">At minimum confidence <b>${mconf}%</b>, ${t.length} of ${rules.length} rules survive. His run kept <code>{1,3} → {5}</code> at 66 % and <code>{1,5} → {3}</code> at 100 %, and threw away <code>{3} → {1,5}</code> at 50 %.</p>`;
      $('apFacts').innerHTML=F('transactions',TX.length)+F('min support',msup)+F('min confidence',mconf+'%')+
        F('candidate rules',rules.length)+F('kept',t.length,'good')+F('dropped',rules.length-t.length,rules.length-t.length?'bad':'');
      say('apWhy','A rule is only interesting when it is frequent <em>and</em> reliable <em>and</em> better than chance — that is support, confidence and lift, in that order. Lift = 1 means the two items are independent, so lift is the one that kills the obvious rules.');
      $('apStage').innerHTML=html; return;
    }
    const set=steps[level]||[];
    html=`<div class="tbl"><div class="trow">${['item set','support','frequent at min sup '+msup+'?'].map(h=>`<div class="tc hd">${h}</div>`).join('')}</div>
      ${set.map(s=>{const v=sup(s), ok=v>=msup;
        return `<div class="trow"><div class="tc" style="min-width:130px">{${s.join(', ')}}</div><div class="tc ${ok?'':'r'}">${v}</div><div class="tc ${ok?'g':'r'}">${ok?'yes':'no — pruned'}</div></div>`}).join('')||'<div class="trow"><div class="tc off">empty — nothing survived</div></div>'}</div>`;
    if(level.startsWith('C')) html+=`<p class="hint">This is a <b>candidate</b> level: joined from the previous frequent set. ${level==='C3'?'The pruning rule (the Apriori property) is the whole trick: <code>{1,2,3}</code> is only generated if <code>{1,2}</code>, <code>{1,3}</code> and <code>{2,3}</code> were all frequent. {1,2} was not, so {1,2,3} never even gets counted.':'Every candidate must have all its k−1 subsets frequent, or it is discarded before counting.'}</p>`;
    $('apStage').innerHTML=html;
    const F_=steps.F3||[];
    $('apFacts').innerHTML=[['transactions',TX.length],['min support',msup],['|C1|',(steps.C1||[]).length],['|F1|',(steps.F1||[]).length],
      ['|C2|',(steps.C2||[]).length],['|F2|',(steps.F2||[]).length],['|F3|',F_.length],['frequent 3-sets',F_.map(s=>'{'+s.join('')+'}').join(' ')]]
      .map(([k,v],i)=>F(k,v,['|F3|','frequent 3-sets'].includes(k)?'hot':'')).join('');
    say('apWhy',`His table, at minimum support 2: <b>F1 = {1:3, 2:3, 3:4, 5:4}</b> (item 4 is dropped, support 1). <b>F2</b> keeps {1,3}, {1,5}, {2,3}, {2,5}, {3,5} and drops {1,2} at support 1. <b>F3 = {1,3,5} and {2,3,5}, both support 2</b> — and {1,2,3} was pruned as a candidate because {1,2} was not frequent. <b>C4 = {1,2,3,5}</b> has support 1, below the minimum, so the search stops at level 3. Set the sliders and watch the tables shrink or explode — a support that is too low produces thousands of rules you cannot read.`);
  }
  run();
  $('apDefs').innerHTML=[['support','P(A ∪ B) — how often the pair appears at all',"frequency of item A, or of the set"],
    ['confidence','P(B | A) = sup(A∪B) / sup(A)',"of the baskets with A, how many also have B"],
    ['lift','confidence / P(B)',"the strength of the association; 1 = no association at all"],
    ['leverage','observed − expected co-occurrence','a small correction term for the same idea'],
    ['conviction','how surprising it would be if the rule failed','high conviction = the rule hardly ever misses']]
    .map(([a,b,c])=>`<div class="trow"><div class="tc hd">${a}</div><div class="tc" style="min-width:220px;text-align:left">${b}</div><div class="tc" style="min-width:220px;text-align:left">${c}</div></div>`).join('')+
    `<div class="trow"><div class="tc hd">his headline</div><div class="tc" style="text-align:left" colspan="3">"customers who purchase bread have a <b>60 % likelihood</b> to also purchase jam" — that sentence <em>is</em> a confidence figure.</div></div>`;
})();

/* ============================== 24 · METRICS LAB ============================== */
(()=>{
  let m={tn:105,fp:21,fn:25,tp:63};
  chips('mxPresets',[['titanic','his Titanic 105/21/25/63'],['loan','his loan 100/5/10/50'],['fraud','fraud 9990/5/8/97'],['balanced','50/50/50/50']],
    'titanic',v=>{m=({titanic:{tn:105,fp:21,fn:25,tp:63},loan:{tn:100,fp:10,fn:5,tp:50},fraud:{tn:9990,fp:5,fn:8,tp:97},balanced:{tn:50,fp:50,fn:50,tp:50}})[v];draw()});
  function draw(){
    $('mxStage').innerHTML=`<div class="tbl">
      <div class="trow"><div class="tc hd"></div><div class="tc hd">predicted NO</div><div class="tc hd">predicted YES</div></div>
      <div class="trow"><div class="tc hd">actual NO</div><div class="tc g" data-k="tn" style="font-size:1.2rem;cursor:pointer">${m.tn}</div><div class="tc r" data-k="fp" style="font-size:1.2rem;cursor:pointer">${m.fp}</div></div>
      <div class="trow"><div class="tc hd">actual YES</div><div class="tc r" data-k="fn" style="font-size:1.2rem;cursor:pointer">${m.fn}</div><div class="tc g" data-k="tp" style="font-size:1.2rem;cursor:pointer">${m.tp}</div></div></div>
      <p class="hint">Click a cell to add 10, shift-click to subtract. TN/TP are the green correct corners; FP/FN are the two different kinds of mistake.</p>`;
    [...$('mxStage').querySelectorAll('[data-k]')].forEach(c=>c.onclick=e=>{
      const k=c.dataset.k, d=e.shiftKey?-10:10; m[k]=Math.max(0,m[k]+d); draw();});
    const {tn,fp,fn,tp}=m, tot=tn+fp+fn+tp||1;
    const acc=(tn+tp)/tot, p=tp/(tp+fp||1), r=tp/(tp+fn||1), f1=p+r?2*p*r/(p+r):0, spec=tn/(tn+fp||1);
    $('mxFacts').innerHTML=F('total',tot)+F('accuracy',pct(acc,2),'hot')+F('precision',pct(p,2))+F('recall / TPR',pct(r,2))+
      F('specificity',pct(spec,2))+F('F1',pct(f1,2))+F('false positive rate',pct(1-spec,2))+F('support yes',tp+fn)+F('support no',tn+fp);
    say('mxWhy',`His Titanic arithmetic, out loud: \"you just need to add the correct values… 105 + 63 = 168, then all four numbers 105+63+21+25 = 214, so accuracy is 78 %\". His loan example is the one to keep: 165 predictions, 105 people really did not default and the model caught <b>100</b> of them, 60 really did default and it caught <b>50</b> — accuracy looks fine (91 %), but 10 defaulters were handed loans, and in banking that is the number the manager asks about.`);
    roc(p,1-spec);
    const bal=(105+63)/214, fraudAcc=(9990+97)/(9990+5+8+97);
    $('imbFacts').innerHTML=F('balanced set accuracy',pct(bal,1))+F('fraud set accuracy',pct(fraudAcc,2),'good')+
      F('fraud set recall',pct(97/105,1),'bad')+F('a model that always says "no"',pct(fraudAcc,2))+
      F('so accuracy means','nothing here','bad');
  }
  function roc(tpr,fpr){
    const W=320,H=300, X=v=>30+v*(W-60), Y=v=>H-30-v*(H-60);
    const curve=t=>{ // model with AUC .87 approximated
      const a=0.87; const pts=[]; for(let i=0;i<=40;i++){const f=i/40; const th=(1-f);
        pts.push([f, clamp(Math.pow(th,1)*(1-0)+Math.pow(1-(1-f),1/a),0,1)])} return pts};
    const real=Array.from({length:41},(_,i)=>{const f=i/40;return [f, clamp(1-Math.pow(1-f,1/0.42),0,1)]});
    let g=`<line x1="${X(0)}" y1="${Y(0)}" x2="${X(1)}" y2="${Y(1)}" stroke="var(--muted)" stroke-dasharray="6 5"/>
      <text x="${X(0.55)}" y="${Y(0.5)}" class="axlab">AUC 0.5 = guessing</text>
      <rect x="${X(0)}" y="${Y(1)}" width="${X(1)-X(0)}" height="${Y(0)-Y(1)}" fill="none" stroke="var(--line)"/>
      <path d="${real.map((pt,i)=>`${i?'L':'M'}${X(pt[0])} ${Y(pt[1])}`).join(' ')}" fill="none" stroke="var(--a)" stroke-width="3"/>
      <circle cx="${X(fpr)}" cy="${Y(tpr)}" r="8" fill="var(--fill)" stroke="var(--hl-edge)" stroke-width="2"/>
      <text x="${X(fpr)+12}" y="${Y(tpr)+4}" class="axlab" font-size="12">your operating point</text>
      <text x="${X(0)}" y="${H-10}" class="axlab">false positive rate →</text>
      <text x="6" y="${Y(1)+6}" class="axlab" transform="">TPR ↑</text>`;
    $('rocSvg').innerHTML=g;
  }
  $('rocTh').oninput=e=>{const t=+e.target.value/100; $('rocThV').textContent=t.toFixed(2);
    const {tn,fp,fn,tp}=m, tot=tn+fp+fn+tp||1;
    const tpr=clamp(tp/(tp+fn||1)*(1-t*0.35)+ (1-t)*0.05,0,1), fpr=clamp(1-(1-t)*0.9 - t*0.02,0,1);
    roc(tpr,fpr)};
  draw();
})();

/* ============================== 25 · INTERVIEW CARDS ============================== */
(()=>{
  const Q=[['What is machine learning?','No single accepted definition — "you will get at least 100 different definitions". Samuel 1959 was the first formal one. Practically: an algorithm trained on a data set to produce a model, which predicts on new input, is scored, and is retrained if the score is not good enough.'],
    ['Supervised vs unsupervised vs reinforcement?','Supervised = labelled data, a teacher. Unsupervised = no labels, the algorithm finds structure and cannot name it. Reinforcement = an agent acting in an environment for reward/penalty (−50 for a wrong move). Semi-supervised = a little labelled plus a lot unlabelled.'],
    ['Regression vs classification?','Both supervised. Regression outputs a continuous quantity, classification outputs a category. Ask what the target column looks like — that is the whole answer.'],
    ['How is KNN different from K-means?','The trick question he calls out by name: KNN is <b>supervised</b> (used for classification and regression, needs labels, votes among the K closest training points). K-means is <b>unsupervised</b> clustering (no labels, you supply K, it moves centroids). They share a letter and a distance formula, nothing else.'],
    ['Explain precision and recall with an example.','His birthdays story: recall all the surprising events of the last 10 years. If there were 10 and you got all 10, recall = 1.0 (100 %); 7 correct of 10 = 0.7. If instead you named 15 things and only 10 were right, precision = 10/15 = 66 %. Precision = TP/(TP+FP), recall = TP/(TP+FN).'],
    ['Walk me through a confusion matrix.','165 loan predictions: 105 people really did not default, the model identified 100 of them; 60 really did default, it caught 50 — and 10 defaulters were approved. Accuracy 91 % looks great; the 10 approve-wrongs are the number that matters.'],
    ['Is model accuracy the same as model performance?','No — accuracy is a <b>subset</b> of performance. On fraud, millions of rows and a tiny positive class means a model that always predicts "no" still scores ~99.5 % accuracy. Choose the metric from what the error costs.'],
    ['What is the ROC curve?','TPR against FPR as you sweep the threshold, for binary classification. A curve pinned to the top-left is a good model; a plot at 0.5 is "just normal guessing work". The slope at a point is the likelihood ratio.'],
    ['Why is Naive Bayes "naive"?','It assumes the features are independent of each other — P(a,b|c) = P(a|c)P(b|c). That is almost never true, and the classifier still works well on text because it only needs the ranking of the posteriors, not their exact values.'],
    ['How does a random forest beat a single tree?','Bootstrap rows + random feature subsets (√n for classification, n/3 for regression) make many de-correlated trees; the vote (or mean) cancels their individual overfitting. Bagging. His penguin numbers: entropy 98 %, gini 99 %, and going from 7 to 12 trees made it worse — measure, don\'t assume.'],
    ['What is overfitting and how do you stop it?','Training error keeps falling while test error turns around. Cure: fewer features, shallower trees / min_samples_leaf, pruning, cross-validation, more data, regularisation. His linear-regression note: it is prone to overfitting in high dimension, so use dimensionality reduction.'],
    ['How do you handle missing values?','Count them (<code>isnull().sum()</code>). A column more than about 30 % empty — his Cabin — gets dropped. A useful one gets imputed with a mean, ideally a grouped mean (he used the mean Age per Pclass). Never fill with 0 just to make the error go away.'],
    ['What is the dummy trap?','One-hot encoding k categories gives k columns that sum to 1 — perfectly collinear. Drop one: <code>get_dummies(..., drop_first=True)</code>. His sentence: "if the value is one it is male, if it is zero it is female" — one column is enough.'],
    ['NumPy vs SciPy?','SciPy is the bigger library and NumPy is a part of it. NumPy defines the array; pandas, scikit-learn and SciPy all store their data in NumPy arrays underneath.'],
    ['Series vs DataFrame?','A Series is a single labelled column; a DataFrame is several, so it can hold multiple columns and you can add more. Both share the index.'],
    ['Name five ways to improve a model.','Change the probability cutoff (default 0.5, try 0.8). Better features via feature importance. Engineer new features. More data. Clean/impute the columns with >30 % missing. Reduce dimensionality. Compare models instead of tuning one.']];
  $('iqCards').innerHTML=Q.map(([q,a],i)=>`<div class="card flip" data-i="${i}"><span class="tag">Q${i+1}</span>
    <div class="front"><h4>${q}</h4><p style="font-size:.8rem"><small>click to reveal</small></p></div>
    <div class="back"><p>${a}</p></div></div>`).join('');
  [...$('iqCards').querySelectorAll('.flip')].forEach(c=>c.onclick=()=>c.classList.toggle('open'));
})();


/* ============================== scroll-spy on the top bar ============================== */
(()=>{
  const links=[...document.querySelectorAll('.topbar a')];
  const io=new IntersectionObserver(es=>es.forEach(e=>{
    if(e.isIntersecting){const id='#'+e.target.id;
      links.forEach(a=>a.style.borderColor=a.getAttribute('href')===id?'var(--accent)':'');}
  }),{rootMargin:'-45% 0px -50% 0px'});
  document.querySelectorAll('.bench[id]').forEach(s=>io.observe(s));
})();


