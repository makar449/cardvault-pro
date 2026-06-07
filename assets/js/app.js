(function(){
  const DATA = window.CardVaultData || {products:[], sellers:[], reviews:[], auctions:[]};
  const money = n => new Intl.NumberFormat('ru-RU').format(Number(n||0)) + ' ₽';
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));
  const get = (key, fallback) => { try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; } };
  const set = (key, val) => localStorage.setItem(key, JSON.stringify(val));
  const cart = () => get('cv_cart', {});
  const favs = () => get('cv_favs', []);
  const orders = () => get('cv_orders', []);
  const sellRequests = () => get('cv_sell_requests', []);
  const overrides = () => get('cv_product_overrides', {});
  const products = () => DATA.products.map(p => ({...p, ...(overrides()[p.id] || {})}));
  const productById = id => products().find(p => p.id === id) || products()[0];

  const icons = {
    shield:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l7 3v5c0 5-3.2 8.4-7 10-3.8-1.6-7-5-7-10V6l7-3z"/><path d="M8.5 12l2.2 2.2 4.8-5"/></svg>',
    lock:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><rect x="5" y="10" width="14" height="10" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3"/></svg>',
    globe:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.7 2.5 4 5.5 4 9s-1.3 6.5-4 9c-2.7-2.5-4-5.5-4-9s1.3-6.5 4-9z"/></svg>',
    badge:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M12 3l2.2 2.3 3.2-.2.7 3.1 2.6 1.8-1.3 2.9 1.3 2.9-2.6 1.8-.7 3.1-3.2-.2L12 21l-2.2-2.3-3.2.2-.7-3.1-2.6-1.8 1.3-2.9-1.3-2.9 2.6-1.8.7-3.1 3.2.2L12 3z"/><path d="M8.5 12l2.1 2.1 4.9-5"/></svg>',
    percent:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M19 5L5 19"/><circle cx="7" cy="7" r="2.2"/><circle cx="17" cy="17" r="2.2"/></svg>',
    box:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 8l-9-5-9 5 9 5 9-5z"/><path d="M3 8v8l9 5 9-5V8"/><path d="M12 13v8"/></svg>',
    search:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>',
    cart:'<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M6 6h15l-2 8H8L6 3H3"/><circle cx="9" cy="20" r="1.5"/><circle cx="18" cy="20" r="1.5"/></svg>'
  };

  function cardArtClass(art){ return {sport:'art-sport', dragon:'art-dragon', sci:'art-sci', botanical:'art-botanical', relic:'art-relic'}[art] || 'art-relic'; }
  function slabHTML(p, size='mini'){
    const cls = size === 'large' ? 'slab large-slab' : 'mini-slab';
    return `<div class="${cls}">
      <div class="slab-label"><span>CardVault<br>${p.subtitle || p.title}<br>${p.year || ''}</span><b class="grade">${String(p.grade||'9').match(/\d+/)?.[0] || '9'}</b></div>
      <div class="card-art ${cardArtClass(p.art)}"></div>
      ${size === 'hero' ? '<div class="pedestal"></div>' : ''}
    </div>`;
  }
  function productCard(p){
    const active = favs().includes(p.id) ? 'active' : '';
    return `<article class="product-card reveal" data-product-card="${p.id}">
      <button class="heart ${active}" data-fav="${p.id}" aria-label="Добавить в избранное">♡</button>
      <a class="product-visual" href="product.html?id=${encodeURIComponent(p.id)}" aria-label="Открыть ${p.title}">${slabHTML(p)}</a>
      <div class="tagline"><span class="tag gold">${p.grade}</span><span class="tag ${p.rarity==='Verified'?'green':'violet'}">${p.rarity}</span></div>
      <a class="product-title" href="product.html?id=${encodeURIComponent(p.id)}">${p.title}</a>
      <div class="product-meta">${p.subtitle}<br>${p.category}</div>
      <div class="price">${money(p.price)}</div>
      <button class="buy" data-cart="${p.id}">${icons.cart} Купить</button>
    </article>`;
  }
  function updateCounts(){
    const c = cart(); const total = Object.values(c).reduce((a,b)=>a+Number(b||0),0); const f = favs().length;
    $$('[data-cart-count]').forEach(el => el.textContent = total);
    $$('[data-fav-count]').forEach(el => el.textContent = f);
  }
  function toast(msg){
    let box = $('.toast');
    if(!box){ box = document.createElement('div'); box.className='toast'; document.body.appendChild(box); }
    const el = document.createElement('div'); el.className='toast-msg'; el.textContent = msg; box.appendChild(el);
    setTimeout(()=>{ el.style.opacity='0'; el.style.transform='translateY(8px)'; setTimeout(()=>el.remove(),250); },2400);
  }
  function addToCart(id, qty=1){ const c = cart(); c[id] = Math.max(1, Number(c[id] || 0) + qty); set('cv_cart', c); updateCounts(); toast('Добавлено в корзину'); }
  function toggleFav(id){ let f = favs(); f = f.includes(id) ? f.filter(x=>x!==id) : [...f,id]; set('cv_favs', f); updateCounts(); $$(`[data-fav="${id}"]`).forEach(btn => btn.classList.toggle('active', f.includes(id))); toast(f.includes(id) ? 'Добавлено в избранное' : 'Удалено из избранного'); }
  function removeCart(id){ const c = cart(); delete c[id]; set('cv_cart', c); updateCounts(); renderCart(); }
  function setQty(id, qty){ const c = cart(); if(qty <= 0) delete c[id]; else c[id] = qty; set('cv_cart', c); updateCounts(); renderCart(); }

  function initHeader(){
    const nav = $('.nav'); const toggle = $('[data-menu-toggle]');
    if(toggle) toggle.addEventListener('click',()=> nav.classList.toggle('open'));
    $$('form[data-search-form]').forEach(form => form.addEventListener('submit', e => {
      e.preventDefault(); const q = form.querySelector('input')?.value.trim(); location.href = 'catalog.html' + (q ? `?q=${encodeURIComponent(q)}` : '');
    }));
    const path = location.pathname.split('/').pop() || 'index.html';
    $$('[data-nav]').forEach(a => { if(a.getAttribute('href') === path) a.classList.add('active'); });
  }
  function initGlobalActions(){
    document.addEventListener('click', e => {
      const cartBtn = e.target.closest('[data-cart]'); if(cartBtn){ e.preventDefault(); addToCart(cartBtn.dataset.cart); }
      const favBtn = e.target.closest('[data-fav]'); if(favBtn){ e.preventDefault(); toggleFav(favBtn.dataset.fav); }
      const modalOpen = e.target.closest('[data-open-modal]'); if(modalOpen){ e.preventDefault(); openModal(modalOpen.dataset.openModal); }
      const close = e.target.closest('[data-close-modal]'); if(close || e.target.classList.contains('modal-backdrop')) closeModal();
    });
  }
  function openModal(id){ const el = document.getElementById(id); if(el) el.classList.add('open'); }
  function closeModal(){ $$('.modal-backdrop.open').forEach(el=>el.classList.remove('open')); }
  function reveal(){
    const items = $$('.reveal'); if(!('IntersectionObserver' in window)){ items.forEach(x=>x.classList.add('visible')); return; }
    const io = new IntersectionObserver(entries => entries.forEach(en=>{ if(en.isIntersecting){ en.target.classList.add('visible'); io.unobserve(en.target); } }), {threshold:.12});
    items.forEach(el=>io.observe(el));
  }

  function renderHome(){
    const popular = $('#popular-products'); if(popular) popular.innerHTML = products().slice(0,5).map(productCard).join('');
    const sellers = $('#seller-list'); if(sellers) sellers.innerHTML = DATA.sellers.map((s,i)=>`<div class="seller"><div class="avatar">${i+1}</div><div><div class="seller-name">${s.name}<span class="tier">${s.tier}</span></div><small>${s.deals} сделок</small></div><div class="stars">★★★★★ ${s.rating}</div></div>`).join('');
    const reviews = $('#home-reviews'); if(reviews) reviews.innerHTML = DATA.reviews.slice(0,3).map(r=>reviewHTML(r)).join('');
  }
  function reviewHTML(r){return `<article class="review reveal"><div class="review-head"><div class="avatar">${r.name[0]}</div><div><b>${r.name}</b><br><small class="muted">${r.city}</small></div></div><div class="stars">★★★★★</div><p>${r.text}</p></article>`;}

  function renderCatalog(){
    const grid = $('#catalog-products'); if(!grid) return;
    const params = new URLSearchParams(location.search);
    const initialQ = params.get('q') || '';
    const qInput = $('#catalog-query'); if(qInput) qInput.value = initialQ;
    const state = {q: initialQ.toLowerCase(), category:'Все', sort:'popular'};
    function apply(){
      let list = products().filter(p => state.category === 'Все' || p.category === state.category);
      if(state.q) list = list.filter(p => (p.title+' '+p.subtitle+' '+p.category+' '+p.universe).toLowerCase().includes(state.q));
      if(state.sort === 'priceAsc') list.sort((a,b)=>a.price-b.price);
      if(state.sort === 'priceDesc') list.sort((a,b)=>b.price-a.price);
      if(state.sort === 'grade') list.sort((a,b)=>(b.grade.match(/\d+/)?.[0]||0)-(a.grade.match(/\d+/)?.[0]||0));
      grid.innerHTML = list.length ? list.map(productCard).join('') : '<div class="panel pad empty">Ничего не найдено. Попробуйте изменить фильтры.</div>';
      reveal();
    }
    $$('#category-chips .chip').forEach(chip => chip.addEventListener('click',()=>{ $$('#category-chips .chip').forEach(c=>c.classList.remove('active')); chip.classList.add('active'); state.category=chip.dataset.category; apply(); }));
    if(qInput) qInput.addEventListener('input',()=>{state.q=qInput.value.trim().toLowerCase(); apply();});
    const sort = $('#catalog-sort'); if(sort) sort.addEventListener('change',()=>{state.sort=sort.value; apply();});
    apply();
  }
  function renderProduct(){
    const root = $('#product-root'); if(!root) return;
    const id = new URLSearchParams(location.search).get('id'); const p = productById(id);
    document.title = `${p.title} — CardVault`;
    root.innerHTML = `<div class="product-layout">
      <section class="panel product-large shine reveal">${slabHTML(p,'large')}</section>
      <section class="panel pad reveal">
        <div class="tagline"><span class="tag gold">${p.grade}</span><span class="tag green">Проверено</span><span class="tag violet">${p.category}</span></div>
        <h1 class="page-title">${p.title}</h1>
        <p class="page-lead">${p.subtitle}</p>
        <div class="price" style="font-size:34px">${money(p.price)}</div>
        <p class="muted" style="line-height:1.7">${p.description}</p>
        <div class="details-list">
          <div class="detail"><span>Состояние</span><b>${p.grade}</b></div>
          <div class="detail"><span>Продавец</span><b>${p.seller} · ${p.sellerRating}</b></div>
          <div class="detail"><span>Год</span><b>${p.year}</b></div>
          <div class="detail"><span>Наличие</span><b>${p.stock} шт.</b></div>
        </div>
        <div class="hero-actions"><button class="btn btn-primary" data-cart="${p.id}">Добавить в корзину</button><button class="btn btn-secondary" data-fav="${p.id}">В избранное</button><a class="btn btn-ghost" href="catalog.html">Назад в каталог</a></div>
      </section>
    </div>`;
  }
  function renderCart(){
    const root = $('#cart-root'); if(!root) return;
    const c = cart(); const ids = Object.keys(c); const list = ids.map(id => ({...productById(id), qty:c[id]}));
    if(!list.length){ root.innerHTML='<div class="panel pad empty"><h2>Корзина пуста</h2><p>Добавьте лоты из каталога, чтобы оформить заявку.</p><a class="btn btn-primary" href="catalog.html">Открыть каталог</a></div>'; return; }
    const total = list.reduce((sum,p)=>sum+p.price*p.qty,0);
    root.innerHTML = `<section class="panel pad"><div class="cart-table">${list.map(p=>`<div class="cart-item"><div>${slabHTML(p)}</div><div><b>${p.title}</b><br><span class="muted">${p.subtitle}</span><br><small class="muted">${p.grade}</small></div><div class="qty"><button data-qty-minus="${p.id}">−</button><span>${p.qty}</span><button data-qty-plus="${p.id}">+</button></div><div><b>${money(p.price*p.qty)}</b><br><button class="chip" data-remove-cart="${p.id}">Удалить</button></div></div>`).join('')}</div><div class="cart-total"><span>Итого</span><span>${money(total)}</span></div><div class="hero-actions" style="margin-top:18px"><button class="btn btn-primary" data-open-modal="checkout-modal">Оформить заказ</button><a class="btn btn-ghost" href="catalog.html">Продолжить покупки</a></div></section>`;
    $$('[data-qty-minus]').forEach(b=>b.addEventListener('click',()=>setQty(b.dataset.qtyMinus, Number(cart()[b.dataset.qtyMinus]||1)-1)));
    $$('[data-qty-plus]').forEach(b=>b.addEventListener('click',()=>setQty(b.dataset.qtyPlus, Number(cart()[b.dataset.qtyPlus]||0)+1)));
    $$('[data-remove-cart]').forEach(b=>b.addEventListener('click',()=>removeCart(b.dataset.removeCart)));
  }
  function renderFavorites(){
    const root = $('#favorites-root'); if(!root) return;
    const list = products().filter(p=>favs().includes(p.id));
    root.innerHTML = list.length ? `<div class="products-grid">${list.map(productCard).join('')}</div>` : '<div class="panel pad empty"><h2>Избранное пустое</h2><p>Нажимайте сердечко на карточках, чтобы сохранить лоты.</p><a class="btn btn-primary" href="catalog.html">Открыть каталог</a></div>';
  }
  function renderAuctions(){
    const root = $('#auctions-root'); if(!root) return;
    root.innerHTML = `<div class="auction-grid">${DATA.auctions.map(a=>{ const p=productById(a.id); return `<article class="panel pad auction-card reveal"><div class="panel-head"><span class="timer">⏱ ${a.ends}</span><span class="tag gold">${a.bids} ставок</span></div><div class="product-visual">${slabHTML(p)}</div><h3>${p.title}</h3><p class="muted">Текущая ставка</p><div class="price">${money(a.bid)}</div><button class="btn btn-primary" style="width:100%" data-open-modal="bid-modal">Сделать ставку</button></article>`; }).join('')}</div>`;
  }
  function renderReviewsPage(){ const root = $('#reviews-root'); if(root) root.innerHTML = `<div class="reviews-grid">${DATA.reviews.map(reviewHTML).join('')}</div>`; }
  function renderAdmin(){
    const root = $('#admin-root'); if(!root) return;
    function draw(){
      root.innerHTML = `<div class="grid-main"><section class="panel pad"><div class="panel-head"><h2>Товары</h2><button class="btn btn-small btn-secondary" id="reset-admin">Сбросить изменения</button></div><div class="cart-table">${products().map(p=>`<div class="cart-item"><div>${slabHTML(p)}</div><div><b>${p.title}</b><br><span class="muted">${p.subtitle}</span></div><input class="field" style="width:130px" data-admin-price="${p.id}" value="${p.price}"><input class="field" style="width:70px" data-admin-stock="${p.id}" value="${p.stock}"></div>`).join('')}</div><button class="btn btn-primary" id="save-admin" style="margin-top:16px">Сохранить товары</button></section><aside class="panel pad"><h2>Заявки</h2><p class="muted">Заказы: ${orders().length}</p><p class="muted">Заявки на продажу: ${sellRequests().length}</p><a class="btn btn-ghost" href="catalog.html">Посмотреть каталог</a></aside></div>`;
      $('#save-admin').addEventListener('click',()=>{ const o = overrides(); $$('[data-admin-price]').forEach(inp=>{ const id=inp.dataset.adminPrice; o[id] = {...(o[id]||{}), price: Number(inp.value||0)}; }); $$('[data-admin-stock]').forEach(inp=>{ const id=inp.dataset.adminStock; o[id] = {...(o[id]||{}), stock: Number(inp.value||0)}; }); set('cv_product_overrides', o); toast('Изменения сохранены локально'); draw(); });
      $('#reset-admin').addEventListener('click',()=>{ localStorage.removeItem('cv_product_overrides'); toast('Сброшено'); draw(); });
    }
    draw();
  }
  function initForms(){
    const checkout = $('#checkout-form');
    if(checkout) checkout.addEventListener('submit', e=>{ e.preventDefault(); const data = Object.fromEntries(new FormData(checkout).entries()); const c=cart(); if(!Object.keys(c).length){toast('Корзина пуста');return;} set('cv_orders',[...orders(),{date:new Date().toISOString(), cart:c, customer:data}]); set('cv_cart',{}); updateCounts(); closeModal(); renderCart(); toast('Заявка оформлена. Мы свяжемся с вами.'); });
    const sell = $('#sell-form');
    if(sell) sell.addEventListener('submit', e=>{ e.preventDefault(); const data = Object.fromEntries(new FormData(sell).entries()); set('cv_sell_requests',[...sellRequests(),{date:new Date().toISOString(), data}]); sell.reset(); const prev=$('#upload-preview'); if(prev) prev.innerHTML='Фото появится здесь'; toast('Заявка на продажу отправлена'); });
    const contact = $('#contact-form');
    if(contact) contact.addEventListener('submit', e=>{ e.preventDefault(); contact.reset(); toast('Сообщение отправлено'); });
    const upload = $('#card-photo');
    if(upload) upload.addEventListener('change',()=>{ const file=upload.files?.[0]; const prev=$('#upload-preview'); if(!file||!prev)return; const reader=new FileReader(); reader.onload=()=>{prev.innerHTML=`<img src="${reader.result}" alt="Превью карты">`;}; reader.readAsDataURL(file); });
  }

  function init(){
    initHeader(); initGlobalActions(); updateCounts();
    const page = document.body.dataset.page;
    if(page === 'home') renderHome();
    if(page === 'catalog') renderCatalog();
    if(page === 'product') renderProduct();
    if(page === 'cart') renderCart();
    if(page === 'favorites') renderFavorites();
    if(page === 'auctions') renderAuctions();
    if(page === 'reviews') renderReviewsPage();
    if(page === 'admin') renderAdmin();
    initForms(); reveal();
  }
  document.addEventListener('DOMContentLoaded', init);
})();
