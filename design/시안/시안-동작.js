(() => {
  const root = document.getElementById('hk-studio');
  const concepts = [
    { id: 1, title: '싱그러운 주방', desc: '자연스러운 초록 · 재료에서 시작하는 추천', colors: ['#23704f','#e2edd8','#f9fbf6'] },
    { id: 2, title: '따뜻한 식탁', desc: '크림과 테라코타 · 정성스러운 집밥', colors: ['#a64c30','#e9c5a4','#fff8ee'] },
    { id: 3, title: '한끼 매거진', desc: '편집 디자인 · 발견하는 즐거움', colors: ['#252822','#b4432e','#f8f5ef'] },
    { id: 4, title: '알뜰 냉장고', desc: '정돈된 블루 · 재료와 유통기한 중심', colors: ['#275fc6','#dce9ff','#f5f8fd'] },
    { id: 5, title: '나이트 키친', desc: '딥그린과 라임 · 음식에 집중하는 화면', colors: ['#15251f','#c8e993','#526851'] },
    { id: 6, title: '즐거운 한끼', desc: '버터옐로와 코랄 · 가볍고 경쾌한 요리', colors: ['#e85c45','#ffe07a','#b8d6f1'] },
  ];
  const grid = root.querySelector('.studio-grid');
  concepts.forEach((c) => {
    const template = document.getElementById(`concept-${c.id}`);
    const item = document.createElement('figure');
    item.className = 'studio-item';
    item.dataset.concept = String(c.id);
    item.innerHTML = `<figcaption class="studio-caption"><div><h2><span class="number">0${c.id}</span>${c.title}</h2><p>${c.desc}</p></div><span class="swatches" aria-hidden="true">${c.colors.map(color=>`<span style="background:${color}"></span>`).join('')}</span></figcaption><div class="screen-mount"></div>`;
    item.querySelector('.screen-mount').append(template.content.cloneNode(true));
    grid.append(item);
  });
  function icons() { if (globalThis.lucide) globalThis.lucide.createIcons({attrs:{width:20,height:20,'stroke-width':1.65}}); }
  function save() {
    if (window.openai?.setWidgetState) window.openai.setWidgetState({modelContent:{선택한시안:root.dataset.focus==='all'?'전체 비교':concepts.find(c=>String(c.id)===root.dataset.focus)?.title},privateContent:{focus:root.dataset.focus}}).catch(()=>{});
  }
  function setFocus(focus) {
    if (!['all','1','2','3','4','5','6'].includes(focus)) focus='all';
    root.dataset.focus=focus;
    root.querySelectorAll('.studio-item').forEach(el=>el.hidden=focus!=='all'&&el.dataset.concept!==focus);
    root.querySelectorAll('.studio-switch button').forEach(el=>el.setAttribute('aria-pressed',String(el.dataset.focus===focus)));
  }
  function chip(name) { return `<button type="button" data-ingredient aria-pressed="true">${name}</button>`; }
  function recipe(photo=1,name='냉장고 채소 비빔밥') { return `<button class="proto-recipe" type="button" data-view="detail"><div class="hk-food food-${photo}" role="img" aria-label="${name}"></div><span class="proto-badge">내 재료 4개 활용</span><strong>${name}</strong><small>지금 바로 만들 수 있어요</small></button>`; }
  function openView(screen,view) {
    screen.querySelector('.prototype')?.remove();
    if(view==='home') return;
    const titles={recommend:'맞춤추천',detail:'레시피',brag:'우리의 한 끼',my:'마이',pantry:'내 냉장고',search:'레시피 검색'};
    if(!titles[view]) view='recommend';
    const layer=document.createElement('section');layer.className='prototype';layer.setAttribute('aria-label',`${titles[view]} 미리보기`);
    let body='';
    if(view==='recommend') body=`<h3 class="proto-heading">오늘은 이 재료로<br>맛있는 한 끼.</h3><div class="proto-chips">${['달걀','당근','시금치','애호박'].map(chip).join('')}</div><p class="subtext">이번 추천에 사용할 재료예요.<br>여기서 고쳐도 저장된 냉장고는 그대로예요.</p><button type="button" class="proto-primary" data-recommend>이 재료로 추천받기</button><div class="proto-result" aria-live="polite">${recipe()}</div>`;
    if(view==='detail') body=`<div class="hk-food food-1 proto-picture" role="img" aria-label="냉장고 채소 비빔밥"></div><span class="proto-badge">내 재료 4개 활용</span><h3 class="proto-heading" style="margin-top:12px">냉장고 채소 비빔밥</h3><p class="subtext">밥 · 420 kcal · 시안용 예시</p><ul class="proto-list"><li><strong>내가 가진 재료</strong><span>달걀 · 당근 · 시금치 · 애호박</span></li><li><strong>기본 재료</strong><span>밥 · 간장 · 참기름</span></li></ul><button class="proto-primary" type="button" data-save-recipe aria-pressed="false">즐겨찾기 담기</button>`;
    if(view==='brag') body=`<h3 class="proto-heading">평범한 한 끼도,<br>함께라서 특별하게.</h3><p class="subtext">직접 만든 요리와 이야기를 나눠요.</p><div class="proto-grid"><div class="hk-food food-1" role="img" aria-label="비빔밥 요리 자랑"></div><div class="hk-food food-3" role="img" aria-label="샐러드 요리 자랑"></div><div class="hk-food food-2" role="img" aria-label="된장국 요리 자랑"></div><div class="hk-food food-4" role="img" aria-label="볶음밥 요리 자랑"></div></div><p class="subtext">사진 카드에 실제 사용자의 요리와 좋아요가 표시되는 자리예요.</p>`;
    if(view==='my') body=`<h3 class="proto-heading">나의 한 끼 이야기</h3><p class="subtext">냉장고와 나에게 맞는 식단을 관리해요.</p><div class="proto-list"><button type="button" data-view="pantry"><strong>내 냉장고</strong><span>재료 8개 →</span></button><button type="button" data-view="recommend"><strong>맞춤추천</strong><span>내 재료로 찾아보기 →</span></button><button type="button" data-view="detail"><strong>즐겨찾기</strong><span>담아둔 레시피 →</span></button><li><strong>식단 정보</strong><span>알레르기 · 건강목표</span></li><li><strong>내 레시피</strong><span>직접 만든 요리</span></li></div>`;
    if(view==='pantry') body=`<h3 class="proto-heading">내 냉장고에<br>8가지 재료가 있어요.</h3><p class="subtext">먼저 먹으면 좋은 재료부터 꺼내봐요.</p><ul class="proto-list"><li><strong>두부</strong><span>유통기한 2일 남음</span></li><li><strong>시금치</strong><span>유통기한 3일 남음</span></li><li><strong>달걀</strong><span>유통기한 7일 남음</span></li><li><strong>당근 · 애호박 · 대파</strong><span>날짜 미등록</span></li><li><strong>양파 · 김치</strong><span>날짜 미등록</span></li></ul><button class="proto-primary" type="button" data-view="recommend">이 재료로 추천받기</button>`;
    if(view==='search') body=`<label class="subtext" for="search-${screen.closest('figure').dataset.concept}">레시피 이름으로 찾기</label><input class="proto-search" id="search-${screen.closest('figure').dataset.concept}" placeholder="비빔밥, 된장국, 샐러드" type="search"><div class="search-results" aria-live="polite">${recipe()}</div>`;
    layer.innerHTML=`<header><button type="button" class="back" data-view="home" aria-label="홈 시안으로 돌아가기"><i data-lucide="arrow-left" aria-hidden="true"></i></button><h2>${titles[view]}</h2></header>${body}<p class="proto-note">시안용 예시 화면</p>`;
    screen.append(layer);icons();
  }
  root.addEventListener('click',event=>{
    const btn=event.target.closest('button');if(!btn)return;
    if(btn.dataset.focus){setFocus(btn.dataset.focus);save();return;}
    const screen=btn.closest('.hk-screen');if(!screen)return;
    if(btn.dataset.view){openView(screen,btn.dataset.view);return;}
    if(btn.hasAttribute('data-ingredient'))btn.setAttribute('aria-pressed',String(btn.getAttribute('aria-pressed')!=='true'));
    if(btn.hasAttribute('data-recommend')){const n=screen.querySelectorAll('[data-ingredient][aria-pressed=true]').length;screen.querySelector('.proto-result').innerHTML=n?recipe().replace('4개 활용',`${n}개 활용`):'<p class="subtext" style="margin-top:20px">재료를 하나 이상 선택해주세요.</p>';}
    if(btn.hasAttribute('data-save-recipe')){const saved=btn.getAttribute('aria-pressed')!=='true';btn.setAttribute('aria-pressed',String(saved));btn.textContent=saved?'즐겨찾기에 담았어요':'즐겨찾기 담기';}
  });
  root.addEventListener('input',event=>{
    if(!event.target.matches('.proto-search'))return;
    const keyword=event.target.value.trim();const out=event.target.closest('.prototype').querySelector('.search-results');
    if(!keyword||'비빔밥 채소 달걀'.includes(keyword))out.innerHTML=recipe();
    else if('된장국 두부 애호박'.includes(keyword))out.innerHTML=recipe(2,'두부 애호박 된장국');
    else if('샐러드 두부'.includes(keyword))out.innerHTML=recipe(3,'구운 두부 샐러드');
    else out.innerHTML='<p class="subtext" style="margin-top:20px">예시 레시피는 비빔밥, 된장국, 샐러드예요.</p>';
  });
  setFocus(window.openai?.widgetState?.privateContent?.focus || 'all');
  window.addEventListener('openai:set_globals',event=>{const state=event.detail?.globals?.widgetState;if(state)setFocus(state.privateContent?.focus||'all');});
  const tweakState={radius:22};
  if(globalThis.Tweak){const tweak=new Tweak({container:root,onChange:()=>root.querySelectorAll('.screen-mount').forEach(el=>el.style.borderRadius=`${tweakState.radius}px`)});tweak.addSlider(tweakState,'radius',{label:'시안 프레임 모서리',min:0,max:32,unit:'px'});}
  icons();
})();
