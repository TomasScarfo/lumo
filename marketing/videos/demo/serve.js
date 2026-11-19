// Sirve el panel real con los datos ficticios, sin backend.
const fs = require('fs');
const ROOT = '/home/user/lumo/backend/lumo';
module.exports = async function route(ctx, D) {
  const panel = fs.readFileSync(ROOT + '/panel.html', 'utf8').replace('</head>', '<script>window.LUMO_CONTACT={};</script></head>');
  await ctx.route('**/*', r => {
    const u = r.request().url();
    if (u.includes('/api/datos')) return r.fulfill({ contentType: 'application/json', body: fs.readFileSync(D + '/datos.json') });
    if (u.includes('/card')) return r.fulfill({ contentType: 'text/html', body: fs.readFileSync(D + '/card.html') });
    if (u.endsWith('/panel')) return r.fulfill({ contentType: 'text/html', body: panel });
    const m = u.match(/\/static\/(.+)$/);
    if (m) return r.fulfill({ path: ROOT + '/static/' + m[1] });
    if (u.includes('fonts.g')) return r.continue().catch(() => r.fulfill({ status: 404, body: '' }));
    if (u.includes('/api/')) return r.fulfill({ contentType: 'application/json', body: '{"ok":true}' });
    return r.fulfill({ status: 404, body: '' });
  });
};
