(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const fmt = (n) => new Intl.NumberFormat('ru-RU').format(Number(n || 0)) + ' ₽';
  const imageMap = {
    aurora:'/assets/card-football.svg', dragon:'/assets/card-dragon.svg', frontier:'/assets/card-scifi.svg', flora:'/assets/card-flora.svg', rookie:'/assets/card-basket.svg'
  };
  const categories = [
    ['all','Все лоты'], ['Футбол','Спорт'], ['Фэнтези','TCG и фэнтези'], ['Научная фантастика','Кино и sci‑fi'], ['Винтаж','Винтаж'], ['Баскетбол','Баскетбол']
  ];
  const quotes = [
    ['АС','«Потрясающий сервис! Карта пришла идеально упакованной и полностью соответствует описанию. Уровень доверия к CardVault на высоте.»','Алексей С.','Коллекционер с 2012 года'],
    ['МК','«Покупка прошла спокойно: проверка, оплата, трекинг и упаковка — всё выглядит как премиальный сервис.»','Марина К.','TCG-коллекционер'],
    ['ДП','«Нравится, что цены, рейтинг продавца и состояние карты показаны прозрачно. Вернусь за следующими лотами.»','Дмитрий П.','Покупатель из Санкт‑Петербурга']
  ];
  let csrfToken = '';
  let products = [];
  let currentUser = null;
  let cart = { items: [], total: 0, count: 0 };
  let favorites = new Set();
  let activeCategory = 'all';
  let activeQuery = '';
  let quoteIndex = 0;

  async function initCsrf(){
    const r = await fetch('/api/csrf', { credentials:'same-origin' }).catch(() => null);
    if (!r) return;
    const d = await r.json().catch(() => ({}));
    csrfToken = d.csrf_token || '';
  }
  async function api(path, options = {}){
    const method = (options.method || 'GET').toUpperCase();
    const headers = { 'Content-Type':'application/json', ...(options.headers || {}) };
    if (!['GET','HEAD'].includes(method) && csrfToken) headers['X-CSRF-Token'] = csrfToken;
    const res = await fetch(path, { ...options, headers, credentials:'same-origin' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) throw new Error(data.error || data.message || 'Ошибка сервера');
    return data;
  }
  function toast(text){
    const t = $('#toast'); if (!t) return;
    t.textContent = text; t.classList.add('show');
    clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.remove('show'), 3000);
  }
  function productImage(p){
    return p?.images?.[0]?.url || imageMap[p?.id] || '/assets/card-abstract.svg';
  }
  function scrollToId(id){ document.getElementById(id)?.scrollIntoView({ behavior:'smooth', block:'start' }); }
  function openDrawer(id){ closeDrawer(); const d = document.getElementById(id); if (!d) return; $('#drawerBackdrop')?.classList.add('show'); d.classList.add('show'); d.setAttribute('aria-hidden','false'); }
  function closeDrawer(){ $$('.drawer').forEach(d => { d.classList.remove('show'); d.setAttribute('aria-hidden','true'); }); $('#drawerBackdrop')?.classList.remove('show'); }
  function openModal(id){
    const m = document.getElementById(id); if (!m) return;
    if (id === 'loginModal') updateAccountPanel();
    $('#modalBackdrop')?.classList.add('show'); if (!m.open) m.showModal();
  }
  function closeModal(){ $$('.modal').forEach(m => { if (m.open) m.close(); }); $('#modalBackdrop')?.classList.remove('show'); }
  function ensureAuth(next){ if (currentUser) return true; openModal('loginModal'); toast('Войдите или создайте аккаунт'); if (next) ensureAuth.next = next; return false; }

  function setUser(user){
    currentUser = user || null;
    const loginLabel = $('.login span');
    if (loginLabel) loginLabel.textContent = currentUser ? (currentUser.name || currentUser.email).split(' ')[0].slice(0, 12) : 'Войти';
    $('#adminLink')?.classList.toggle('show', !!currentUser && currentUser.role === 'admin');
    $('#accountAdmin')?.classList.toggle('hidden', !currentUser || currentUser.role !== 'admin');
  }
  async function loadMe(){
    try { const d = await api('/api/me'); setUser(d.user); }
    catch { setUser(null); }
  }
  async function loadProducts(){
    const d = await api('/api/products').catch(() => ({ products: [] }));
    products = d.products || [];
    renderProducts(); renderCategories();
  }
  async function loadStats(){
    const d = await api('/api/stats').catch(() => null);
    const s = d?.stats || { sold_cards:129487, verified_sellers:8742, positive_reviews:25318, countries:96 };
    const data = [
      [s.sold_cards, 'Карт продано'], [s.verified_sellers, 'Проверенных продавцов'], [s.positive_reviews, 'Положительных отзывов'], [s.countries, 'Стран доставки']
    ];
    $('#statsGrid').innerHTML = data.map(([n,l]) => `<div class="stat"><strong>${new Intl.NumberFormat('ru-RU').format(n)}</strong><span>${l}</span></div>`).join('');
  }
  function drawChart(){
    const svg = $('#priceChart'); if (!svg) return;
    svg.innerHTML = `
      <path d="M35 130H285M35 95H285M35 60H285M35 25H285" stroke="#eee4d7"/>
      <path d="M35 140V20M35 140H288" stroke="#ddcfbc"/>
      <path d="M40 118 C64 82, 79 104, 99 92 S138 88, 156 71 183 66, 208 38 235 47 278 21" fill="none" stroke="#b8872e" stroke-width="4" stroke-linecap="round"/>
      <circle cx="278" cy="21" r="5" fill="#b8872e" stroke="#fff" stroke-width="3"/>
      <text x="38" y="154" fill="#8b8074" font-size="11">Дек</text><text x="96" y="154" fill="#8b8074" font-size="11">Янв</text><text x="155" y="154" fill="#8b8074" font-size="11">Мар</text><text x="230" y="154" fill="#8b8074" font-size="11">Май</text>`;
  }
  function renderCategories(){
    const root = $('#categoryList'); if (!root) return;
    const counts = Object.fromEntries(categories.map(c => [c[0], 0]));
    products.forEach(p => { counts[p.category] = (counts[p.category] || 0) + 1; counts.all = (counts.all || 0) + 1; });
    root.innerHTML = categories.map(([key, title]) => `<button class="section-link" style="display:flex;justify-content:space-between;width:100%;padding:8px 0" data-category="${key}"><span>${title}</span><b>${counts[key] || 0}</b></button>`).join('');
  }
  function filteredProducts(){
    const q = activeQuery.trim().toLowerCase();
    return products.filter(p => {
      const okCat = activeCategory === 'all' || p.category === activeCategory;
      const okQ = !q || [p.title,p.category,p.grade,p.description,p.seller_name].join(' ').toLowerCase().includes(q);
      return okCat && okQ;
    });
  }
  function renderProducts(){
    const root = $('#productGrid'); if (!root) return;
    const list = filteredProducts();
    if (!list.length) { root.innerHTML = '<div class="empty" style="grid-column:1/-1">Ничего не найдено. Попробуйте изменить поиск.</div>'; return; }
    root.innerHTML = list.map(p => `
      <article class="product-card" data-product="${p.id}">
        <button class="fav ${favorites.has(p.id) ? 'active' : ''}" data-fav="${p.id}" aria-label="Избранное">♡</button>
        <button class="product-image-wrap" data-detail="${p.id}" aria-label="Открыть лот"><img class="product-image" src="${productImage(p)}" alt="${escapeHtml(p.title)}"></button>
        <h3>${escapeHtml(p.title)}</h3>
        <p class="meta"><span class="condition">${escapeHtml(p.grade)}</span><br>${escapeHtml(p.category)} · ${escapeHtml(p.seller_name || 'CardVault')}</p>
        <div class="price-row"><strong>${fmt(p.price)}</strong><button class="buy" data-add="${p.id}" ${Number(p.stock) <= 0 ? 'disabled' : ''}>${Number(p.stock) <= 0 ? 'Нет' : 'Купить'}</button></div>
      </article>`).join('');
  }
  function escapeHtml(s=''){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

  async function loadCart(){
    if (!currentUser) { cart = { items:[], total:0, count:0 }; updateCart(); return; }
    const d = await api('/api/cart').catch(() => ({ cart:{ items:[], total:0, count:0 } }));
    cart = d.cart; updateCart();
  }
  async function loadFavorites(){
    if (!currentUser) { favorites = new Set(); updateFavorites(); return; }
    const d = await api('/api/favorites').catch(() => ({ favorites: [] }));
    favorites = new Set(d.favorites || []); updateFavorites(); renderProducts();
  }
  function updateCart(){
    const badge = $('#cartBadge'); if (badge) badge.textContent = cart.count || 0;
    const total = $('#cartTotal'); if (total) total.textContent = fmt(cart.total || 0);
    const root = $('#cartItems'); if (!root) return;
    if (!currentUser) { root.innerHTML = '<div class="empty">Войдите, чтобы корзина сохранялась в backend.</div>'; return; }
    if (!cart.items?.length) { root.innerHTML = '<div class="empty">Корзина пока пуста.</div>'; return; }
    root.innerHTML = cart.items.map(item => {
      const p = item.product;
      return `<div class="cart-item"><img src="${productImage(p)}" alt=""><div><h4>${escapeHtml(p.title)}</h4><p>${fmt(p.price)} · ${escapeHtml(p.grade)}</p><div class="qty"><button data-qty="${p.id}" data-delta="-1">−</button><b>${item.qty}</b><button data-qty="${p.id}" data-delta="1">+</button></div></div><button data-remove-cart="${p.id}">✕</button></div>`;
    }).join('');
  }
  function updateFavorites(){
    const badge = $('#favBadge'); if (badge) badge.textContent = favorites.size || 0;
    const root = $('#favoriteItems'); if (!root) return;
    if (!currentUser) { root.innerHTML = '<div class="empty">Войдите, чтобы сохранять избранное.</div>'; return; }
    if (!favorites.size) { root.innerHTML = '<div class="empty">В избранном пока ничего нет.</div>'; return; }
    const favProducts = products.filter(p => favorites.has(p.id));
    root.innerHTML = favProducts.map(p => `<div class="cart-item"><img src="${productImage(p)}" alt=""><div><h4>${escapeHtml(p.title)}</h4><p>${fmt(p.price)} · ${escapeHtml(p.grade)}</p></div><button data-fav="${p.id}">✕</button></div>`).join('');
  }
  async function addToCart(id){ if (!ensureAuth(() => addToCart(id))) return; const d = await api('/api/cart/items', { method:'POST', body:JSON.stringify({ product_id:id, qty:1 }) }); cart = d.cart; updateCart(); toast('Карта добавлена в корзину'); }
  async function updateQty(id, delta){ const item = cart.items.find(x => x.product_id === id); if (!item) return; const qty = Math.max(0, Number(item.qty) + delta); const d = await api('/api/cart/items/' + encodeURIComponent(id), { method:'PATCH', body:JSON.stringify({ qty }) }); cart = d.cart; updateCart(); }
  async function removeCart(id){ const d = await api('/api/cart/items/' + encodeURIComponent(id), { method:'DELETE' }); cart = d.cart; updateCart(); }
  async function toggleFav(id){ if (!ensureAuth(() => toggleFav(id))) return; const method = favorites.has(id) ? 'DELETE' : 'POST'; const d = await api('/api/favorites/' + encodeURIComponent(id), { method }); favorites = new Set(d.favorites || []); updateFavorites(); renderProducts(); }

  function openProduct(id){
    const p = products.find(x => x.id === id); if (!p) return;
    $('#productModalTitle').textContent = p.title;
    $('#productModalBody').innerHTML = `<div class="product-detail"><img src="${productImage(p)}" alt="${escapeHtml(p.title)}"><div><h3 style="margin-top:0">${fmt(p.price)}</h3><p><b>${escapeHtml(p.grade)}</b> · ${escapeHtml(p.category)}</p><p class="muted">${escapeHtml(p.description || '')}</p><p class="muted">Продавец: ${escapeHtml(p.seller_name || 'CardVault')} · рейтинг ${Number(p.seller_rating || 4.9).toFixed(1)}</p><button class="btn btn-primary" data-add="${p.id}">Добавить в корзину</button><button class="btn btn-secondary" data-fav="${p.id}" style="margin-left:8px">${favorites.has(p.id) ? 'Убрать из избранного' : 'В избранное'}</button></div></div>`;
    openModal('productModal');
  }

  async function login(e){
    e.preventDefault(); const body = Object.fromEntries(new FormData(e.target).entries());
    const d = await api('/api/auth/login', { method:'POST', body:JSON.stringify(body) });
    setUser(d.user); await Promise.all([loadCart(), loadFavorites()]); updateAccountPanel(); toast('Вы вошли в аккаунт');
    if (ensureAuth.next) { const fn = ensureAuth.next; ensureAuth.next = null; setTimeout(fn, 150); }
  }
  async function register(e){
    e.preventDefault(); const body = Object.fromEntries(new FormData(e.target).entries());
    const d = await api('/api/auth/register', { method:'POST', body:JSON.stringify(body) });
    setUser(d.user); await Promise.all([loadCart(), loadFavorites()]); updateAccountPanel(); toast('Аккаунт создан. Подтвердите email.');
  }
  async function logout(){ await api('/api/auth/logout', { method:'POST', body:'{}' }).catch(()=>{}); setUser(null); cart={items:[],total:0,count:0}; favorites=new Set(); updateCart(); updateFavorites(); renderProducts(); closeModal(); toast('Вы вышли из аккаунта'); }
  async function forgot(){ const email = $('#loginForm input[name="email"]')?.value; if (!email) return toast('Введите email в форме входа'); await api('/api/password-reset/request', { method:'POST', body:JSON.stringify({ email }) }); toast('Если аккаунт существует, письмо для сброса отправлено'); }
  async function updateAccountPanel(){
    $('#loginForm')?.classList.toggle('hidden', !!currentUser);
    $('#registerForm')?.classList.add('hidden');
    $('#accountPanel')?.classList.toggle('hidden', !currentUser);
    if (!currentUser) return;
    $('#accountInfo').innerHTML = `<b>${escapeHtml(currentUser.name || currentUser.email)}</b><br>${escapeHtml(currentUser.email)} · ${currentUser.email_verified ? 'email подтверждён' : 'email не подтверждён'}`;
    const d = await api('/api/orders').catch(() => ({ orders: [] }));
    $('#accountOrders').innerHTML = (d.orders || []).slice(0,5).map(o => `<div class="cart-item" style="grid-template-columns:1fr auto"><div><h4>${o.order_no}</h4><p>${fmt(o.total)} · ${o.status} · ${o.payment_status}</p></div><span>${new Date(o.created_at).toLocaleDateString('ru-RU')}</span></div>`).join('') || '<p class="muted">Заказов пока нет.</p>';
  }

  function readFile(file){
    return new Promise((resolve, reject) => {
      if (!file) return resolve(null);
      if (!/^image\/(png|jpeg|webp)$/i.test(file.type)) return reject(new Error('Разрешены PNG, JPG или WEBP'));
      if (file.size > 5 * 1024 * 1024) return reject(new Error('Фото должно быть до 5 МБ'));
      const r = new FileReader(); r.onload = () => resolve({ name:file.name, data_url:String(r.result || '') }); r.onerror = () => reject(new Error('Не удалось прочитать файл')); r.readAsDataURL(file);
    });
  }
  async function uploadImages(files, purpose){
    const list = await Promise.all([...files].slice(0,8).map(readFile));
    if (!list.length) return [];
    const d = await api('/api/uploads', { method:'POST', body:JSON.stringify({ purpose, files:list.filter(Boolean) }) });
    return d.uploads || [];
  }
  async function sell(e){
    e.preventDefault(); if (!ensureAuth()) return;
    const f = e.target; const raw = Object.fromEntries(new FormData(f).entries());
    const uploads = await uploadImages(f.elements.images.files, 'sell_request');
    const payload = { card:raw.card_title, category:raw.category, grade:raw.grade, price:raw.expected_price, message:raw.message, photos:uploads };
    await api('/api/sell-requests', { method:'POST', body:JSON.stringify(payload) });
    f.reset(); closeModal(); toast('Заявка с фото отправлена на модерацию');
  }
  async function checkout(e){
    e.preventDefault(); if (!ensureAuth()) return;
    const shipping = Object.fromEntries(new FormData(e.target).entries());
    const d = await api('/api/orders/checkout', { method:'POST', body:JSON.stringify({ shipping, payment_method:'manual' }) });
    cart = { items:[], total:0, count:0 }; updateCart(); closeModal();
    toast(`Заказ ${d.order.order_no} создан`);
    setTimeout(() => { location.href = d.payment_url || '/payment-result.html?order=' + encodeURIComponent(d.order.order_no); }, 600);
  }
  function updateQuote(i){
    quoteIndex = (i + quotes.length) % quotes.length;
    const q = quotes[quoteIndex]; $('#quoteAvatar').textContent = q[0]; $('#quoteText').textContent = q[1]; $('#quoteAuthor').textContent = q[2]; $('#quoteMeta').textContent = q[3];
    $('#quoteDots').innerHTML = quotes.map((_, idx) => `<button class="${idx===quoteIndex?'active':''}" data-quote="${idx}"></button>`).join('');
  }
  async function processQuery(){
    const params = new URLSearchParams(location.search);
    if (params.get('verify_email')) {
      await api('/api/auth/verify-email', { method:'POST', body:JSON.stringify({ token:params.get('verify_email') }) }).then(()=>toast('Email подтверждён')).catch(e=>toast(e.message));
      history.replaceState({}, '', location.pathname);
    }
    if (params.get('reset_password')) {
      const password = prompt('Введите новый пароль (минимум 8 символов)');
      if (password) await api('/api/password-reset/confirm', { method:'POST', body:JSON.stringify({ token:params.get('reset_password'), password }) }).then(()=>toast('Пароль обновлён')).catch(e=>toast(e.message));
      history.replaceState({}, '', location.pathname);
    }
  }
  function bind(){
    document.addEventListener('click', async (e) => {
      const open = e.target.closest('[data-open]'); if (open) { openModal(open.dataset.open); return; }
      const drawer = e.target.closest('[data-drawer]'); if (drawer) { openDrawer(drawer.dataset.drawer); return; }
      if (e.target.closest('[data-close]') || e.target === $('#drawerBackdrop')) { closeDrawer(); return; }
      if (e.target.closest('[data-modal-close]') || e.target === $('#modalBackdrop')) { closeModal(); return; }
      const scroll = e.target.closest('[data-scroll]'); if (scroll) { closeDrawer(); scrollToId(scroll.dataset.scroll); return; }
      const add = e.target.closest('[data-add]'); if (add) { await addToCart(add.dataset.add).catch(err => toast(err.message)); return; }
      const fav = e.target.closest('[data-fav]'); if (fav) { await toggleFav(fav.dataset.fav).catch(err => toast(err.message)); return; }
      const detail = e.target.closest('[data-detail]'); if (detail) { openProduct(detail.dataset.detail); return; }
      const rem = e.target.closest('[data-remove-cart]'); if (rem) { await removeCart(rem.dataset.removeCart).catch(err => toast(err.message)); return; }
      const qty = e.target.closest('[data-qty]'); if (qty) { await updateQty(qty.dataset.qty, Number(qty.dataset.delta)).catch(err => toast(err.message)); return; }
      const cat = e.target.closest('[data-category]'); if (cat) { activeCategory = cat.dataset.category; renderProducts(); scrollToId('catalog'); return; }
      const clear = e.target.closest('[data-clear-filter]'); if (clear) { activeCategory='all'; activeQuery=''; $('#searchInput').value=''; renderProducts(); return; }
      const tab = e.target.closest('[data-auth-tab]'); if (tab) { $$('.auth-tabs button').forEach(b=>b.classList.toggle('active', b===tab)); $('#loginForm').classList.toggle('hidden', tab.dataset.authTab !== 'login'); $('#registerForm').classList.toggle('hidden', tab.dataset.authTab !== 'register'); $('#accountPanel').classList.add('hidden'); return; }
      const q = e.target.closest('[data-quote]'); if (q) updateQuote(Number(q.dataset.quote));
    });
    $('#searchForm')?.addEventListener('submit', e => { e.preventDefault(); activeQuery = $('#searchInput').value; renderProducts(); scrollToId('catalog'); });
    $('#searchInput')?.addEventListener('input', e => { activeQuery = e.target.value; renderProducts(); });
    $('#loginForm')?.addEventListener('submit', e => login(e).catch(err => toast(err.message)));
    $('#registerForm')?.addEventListener('submit', e => register(e).catch(err => toast(err.message)));
    $('#forgotBtn')?.addEventListener('click', () => forgot().catch(err => toast(err.message)));
    $('#logoutBtn')?.addEventListener('click', () => logout().catch(err => toast(err.message)));
    $('#sellForm')?.addEventListener('submit', e => sell(e).catch(err => toast(err.message)));
    $('#checkoutBtn')?.addEventListener('click', () => { if (!cart.items?.length) return toast('Корзина пуста'); openModal('checkoutModal'); });
    $('#checkoutForm')?.addEventListener('submit', e => checkout(e).catch(err => toast(err.message)));
    $('#heroNext')?.addEventListener('click', () => { const row = $('#heroCards'); row.appendChild(row.firstElementChild); });
    document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeDrawer(); closeModal(); } });
  }
  async function boot(){
    await initCsrf(); bind(); updateQuote(0); drawChart(); await processQuery(); await loadProducts(); await loadStats(); await loadMe(); await Promise.all([loadCart(), loadFavorites()]);
  }
  boot().catch(err => { console.error(err); toast(err.message || 'Ошибка запуска'); });
})();
