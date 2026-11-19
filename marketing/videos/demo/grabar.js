const { chromium } = require('playwright'); const route = require('./serve.js'); const D = __dirname;
const W = 1280, H = 720;
const CAP = `
#cap{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:9999;max-width:980px;width:max-content;
  background:rgba(20,32,43,.92);color:#fff;font:600 22px/1.35 Figtree,sans-serif;padding:14px 22px;border-radius:14px;
  box-shadow:0 10px 30px rgba(0,0,0,.25);transition:opacity .35s;text-align:center}
#cap b{color:#FFD666}
#cur{position:fixed;z-index:10000;width:22px;height:22px;margin:-11px 0 0 -11px;border-radius:50%;background:rgba(36,70,214,.35);
  border:2px solid #2446D6;pointer-events:none;transition:left .6s ease,top .6s ease,transform .15s}`;
(async () => {
  const b = await chromium.launch();
  const ctx = await b.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: D + '/raw', size: { width: W, height: H } } });
  await route(ctx, D);
  const p = await ctx.newPage();
  const wait = ms => p.waitForTimeout(ms);
  const setup = async () => p.evaluate(css => {
    if (document.getElementById('cap')) return;
    const st = document.createElement('style'); st.textContent = css; document.head.appendChild(st);
    const c = document.createElement('div'); c.id = 'cap'; c.style.opacity = 0; document.body.appendChild(c);
    const k = document.createElement('div'); k.id = 'cur'; k.style.left = '640px'; k.style.top = '360px'; document.body.appendChild(k);
  }, CAP);
  const cap = async (html, ms) => { await p.evaluate(h => { const c = document.getElementById('cap'); c.style.opacity = 0;
    setTimeout(() => { c.innerHTML = h; c.style.opacity = 1; }, 250); }, html); await wait(ms || 3800); };
  const point = async (loc) => { const bb = await loc.boundingBox(); if (!bb) return;
    await p.evaluate(([x, y]) => { const k = document.getElementById('cur'); k.style.left = x + 'px'; k.style.top = y + 'px'; }, [bb.x + bb.width / 2, bb.y + bb.height / 2]);
    await wait(700); };
  const click = async (loc) => { await loc.scrollIntoViewIfNeeded(); await point(loc);
    await p.evaluate(() => { const k = document.getElementById('cur'); k.style.transform = 'scale(.7)'; setTimeout(() => k.style.transform = '', 160); });
    await loc.click(); await wait(500); };
  const scrollTo = async (sel, off = 90) => { await p.evaluate(([s, o]) => { const e = document.querySelector(s); if (e) window.scrollTo({ top: e.getBoundingClientRect().top + scrollY - o, behavior: 'smooth' }); }, [sel, off]); await wait(1300); };
  const tab = name => p.locator('.nav button', { hasText: name }).first();

  // Presentación
  await p.goto('http://lumo.test/card#inicio'); await wait(4200);

  // Principal
  await p.goto('http://lumo.test/panel'); await p.waitForSelector('.kpi'); await setup(); await wait(600);
  await cap('Lo primero que ves: <b>cómo viene tu publicidad</b>, en una frase.', 4300);
  await cap('Cada campaña se compara con <b>su propio ROAS objetivo</b>: por debajo no es estar mal, es una oportunidad.', 4300);
  await scrollTo('.kpis');
  await cap('Tus métricas clave del período, <b>contra el período anterior</b>.', 4000);
  await click(p.locator('.seg button', { hasText: '30 días' }));
  await cap('Cambiás el período con un toque: 7, 14, 30 días o <b>el rango que quieras</b>.', 3800);
  await scrollTo('.mchips', 150);
  await click(p.locator('.mchip', { hasText: 'Inversión' }).first());
  await cap('El gráfico cruza <b>ventas, ingresos e inversión</b> día a día.', 4000);
  await scrollTo('.rbar', 220);
  await cap('<b>ROAS de cada campaña contra su objetivo</b>: ves enseguida cuál rinde y cuál no llega.', 4500);
  await scrollTo('table.ct', 160);
  await cap('Todas tus campañas en una tabla que <b>ordenás y filtrás</b>.', 3200);
  await click(p.locator('table.ct .link').first());
  await cap('Y abrís cada campaña para ver <b>qué publicaciones venden y cuáles solo gastan</b>.', 4300);

  // Tareas
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await wait(900);
  await click(tab('Tareas'));
  await cap('<b>Tareas</b>: lo que conviene hacer hoy, ordenado por importancia.', 4300);
  await click(p.locator('.task input').first());
  await cap('Marcás lo que hiciste y Lumo <b>mide el antes y el después</b>.', 3800);

  // Alertas
  await click(tab('Alertas'));
  await cap('<b>Alertas</b>: publicaciones que gastan sin vender y las que venden solas y merecen publicidad.', 4600);
  await p.mouse.wheel(0, 520); await wait(1600);

  // Recomendaciones
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await wait(800);
  await click(tab('Recomendaciones'));
  await cap('<b>Recomendaciones con números</b>: cuánto subir o bajar cada presupuesto y por qué.', 4800);
  await p.mouse.wheel(0, 420); await wait(1800);

  // Seguimiento y tendencias
  await p.evaluate(() => window.scrollTo({ top: 0, behavior: 'smooth' })); await wait(800);
  await click(tab('Seguimiento'));
  await cap('<b>Seguimiento</b>: comprobás si lo que cambiaste funcionó.', 3800);
  await click(tab('Tendencias'));
  await cap('<b>Tendencias</b>: qué categorías y marcas crecen y cuánta publicidad tienen.', 4300);

  // Glosario
  await click(tab('Glosario'));
  await click(p.locator('input.search').first());
  await p.keyboard.type('ACOS', { delay: 140 }); await wait(700);
  await cap('Y un <b>glosario en palabras simples</b>, para entender cada métrica.', 4000);

  // Cierre
  await p.goto('http://lumo.test/card#fin'); await wait(5200);
  await ctx.close(); await b.close();
})();
