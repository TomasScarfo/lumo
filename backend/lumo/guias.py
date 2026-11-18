"""Guías de la portada: páginas para quien busca en Google cómo entender su publicidad en Mercado Libre.

Cada guía tiene su plantilla en templates/guias/<slug>.html. Esta lista arma el índice, los enlaces entre guías,
el mapa del sitio y la portada estática (build_site.py). Al agregar una guía: sumarla acá, crear su plantilla y
regenerar la portada (cd backend && python build_site.py).
"""

GUIAS = (
    {
        "slug": "roas-mercado-libre",
        "titulo": "Qué es el ROAS en Mercado Libre y cómo calcularlo",
        "corto": "Qué es el ROAS y cómo calcularlo",
        "descripcion": "Qué es el ROAS en Product Ads de Mercado Libre, cómo se calcula con un ejemplo y cuál es el ROAS mínimo para que tu publicidad no te haga perder plata.",
        "resumen": "Cuánto vendés por cada peso de publicidad, y el número que no tenés que perforar.",
        "publicada": "2026-11-18",
    },
    {
        "slug": "acos-mercado-libre",
        "titulo": "Qué es el ACOS en Product Ads y cómo bajarlo",
        "corto": "Qué es el ACOS y cómo bajarlo",
        "descripcion": "Qué es el ACOS en Product Ads de Mercado Libre, cómo se relaciona con el ROAS y cinco formas concretas de bajarlo sin dejar de vender.",
        "resumen": "Qué parte de cada venta se va en publicidad y cómo achicarla.",
        "publicada": "2026-11-18",
    },
    {
        "slug": "product-ads-mercado-libre",
        "titulo": "Cómo funciona Product Ads de Mercado Libre",
        "corto": "Cómo funciona Product Ads",
        "descripcion": "Guía simple de Product Ads de Mercado Libre: dónde aparecen tus anuncios, cuánto pagás, qué es el ROAS objetivo y qué métricas mirar para saber si te conviene.",
        "resumen": "Dónde aparecen tus anuncios, cuánto pagás y qué mirar.",
        "publicada": "2026-11-18",
    },
    {
        "slug": "presupuesto-publicidad-mercado-libre",
        "titulo": "Cuánto invertir en publicidad en Mercado Libre",
        "corto": "Cuánto invertir en publicidad",
        "descripcion": "Cómo definir el presupuesto de Product Ads en Mercado Libre: desde tu margen, con un ejemplo paso a paso, y cuándo conviene subirlo o bajarlo.",
        "resumen": "Cómo armar el presupuesto desde tu margen, paso a paso.",
        "publicada": "2026-11-18",
    },
)

POR_SLUG = {g["slug"]: g for g in GUIAS}


def ruta(slug: str = "") -> str:
    """Dirección de una guía (o del índice), con barra final: así la sirve igual la portada estática y la app."""
    return "/guias/%s/" % slug if slug else "/guias/"
